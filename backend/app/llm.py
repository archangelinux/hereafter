"""The only things the LLM is allowed to do: extract structure from messy input (pages,
the person's own words, their options and what-ifs), pick what to look up (Elastic queries,
research questions), narrate a life that the simulator already decided, and (Jev) classify and
score proposed events against the person's own record.
It never sees a request to invent, choose, or weigh a future, and never supplies a probability. Every function here returns
None on any failure (or when HEREAFTER_LLM=off) and callers carry on without it.
"""

from __future__ import annotations

import logging
from typing import Literal, Optional

from pydantic import BaseModel

from . import config

log = logging.getLogger("hereafter.llm")
_client = None


def enabled() -> bool:
    return config.LLM_ENABLED


def _parse(system: str, user: str, schema: type[BaseModel], max_tokens: int = 16000, fast: bool = False):
    """One structured-output call. Returns the parsed model, or None on any failure."""
    if not enabled():
        return None
    model = config.LLM_FAST_MODEL if fast else config.LLM_MODEL
    try:
        if config.LLM_PROVIDER == "openai":
            return _parse_openai(system, user, schema, max_tokens, model, config.LLM_FAST_EFFORT if fast else "")
        return _parse_anthropic(system, user, schema, max_tokens, model)
    except Exception as exc:
        log.warning("LLM unavailable (%s: %s); continuing without it", type(exc).__name__, str(exc)[:200])
    return None


def _parse_openai(system: str, user: str, schema: type[BaseModel], max_tokens: int, model: str, effort: str = ""):
    import openai

    global _client
    if _client is None:
        _client = openai.OpenAI()
    extra = {"reasoning": {"effort": effort}} if effort else {}
    response = _client.responses.parse(
        model=model, instructions=system, input=user, text_format=schema, max_output_tokens=max_tokens, **extra,
    )
    if response.status != "completed":
        log.warning("LLM stopped with %s; continuing without it", response.status)
        return None
    return response.output_parsed


def _parse_anthropic(system: str, user: str, schema: type[BaseModel], max_tokens: int, model: str):
    import anthropic

    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    response = _client.messages.parse(
        model=model, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": user}], output_format=schema,
    )
    if response.stop_reason in ("refusal", "max_tokens"):
        log.warning("LLM stopped with %s; continuing without it", response.stop_reason)
        return None
    return response.parsed_output


# --- (a) extraction: one schema for every kind of input ---


class ExtractedEvent(BaseModel):
    date: Optional[str] = None
    domain: str
    event_type: str
    text: str
    confidence: float
    city: Optional[str] = None
    education: Optional[str] = None
    field: Optional[str] = None
    employment: Optional[Literal["employed", "unemployed", "student", "retired"]] = None
    income_band: Optional[Literal["low", "lower_middle", "middle", "upper_middle", "high"]] = None
    relationship_status: Optional[Literal["single", "married", "divorced", "widowed"]] = None
    housing: Optional[Literal["renting", "owning", "with_family"]] = None


class StateFacts(BaseModel):
    as_of: Optional[str] = None
    confidence: float
    city: Optional[str] = None
    education: Optional[str] = None
    field: Optional[str] = None
    employment: Optional[Literal["employed", "unemployed", "student", "retired"]] = None
    income_band: Optional[Literal["low", "lower_middle", "middle", "upper_middle", "high"]] = None
    relationship_status: Optional[Literal["single", "married", "divorced", "widowed"]] = None
    housing: Optional[Literal["renting", "owning", "with_family"]] = None
    birth_year: Optional[int] = None


class PersonalityEstimate(BaseModel):
    O: float
    C: float
    E: float
    A: float
    N: float
    confidence: float


class Extraction(BaseModel):
    events: list[ExtractedEvent]
    facts: Optional[StateFacts] = None
    personality: Optional[PersonalityEstimate] = None


EXTRACT_SYSTEM = """You turn one thing a person has offered about their own life into \
structured data. The input may be a public profile page, a resume, their own freeform words, \
part of a chat export, or something unclassifiable. Whatever it is, the output is the same:

1. `events`: dated things that happened to this person. ISO dates (YYYY-01-01 when only the \
year is known, YYYY-MM-01 for a month); leave `date` null when no date can be supported. A \
`domain` (a lowercase life-area tag: use career, housing, relationship, money or health when \
the event establishes where they work, live, who they are with, what they earn or their \
health; otherwise whatever fits — family, friends, learning, growth, body, mind, play, food), \
a snake_case event_type (education, graduation, job_start, job_change, job_end, \
city_move, marriage, divorce, birth, home_purchase, project, social_activity, \
decision_pending, goal_set, goal_kept, goal_dropped, note), a short factual `text`, and a confidence between 0 and 1 for how \
directly the input supports it. Fill an event's state fields only when that event \
establishes them. `birth` always means a child born to this person; their own birth is \
not an event (put the year in `facts.birth_year`).
2. `facts`: what the input says about their situation as of the time it was written \
(`as_of`, null if unknown). Null when it says nothing of the kind.
3. `personality`: Big Five z-scores, only when the input contains actual personality results \
or substantial first-person writing to estimate from; confidence at most 0.4 when estimated \
from writing. Null otherwise.

`field` must be one of: education, arts, humanities, social_sciences_law, business, sciences, \
math_cs, engineering, agriculture, health, services.

Record only what the input states or directly shows about this one person. In chat exports, \
other people appear: never record their names, their words, or events about them, and never \
quote a message. Never infer private facts that are not there. Never record anything about \
the future except a decision the person says they are facing (event_type decision_pending). \
A thought that is not an event still belongs: keep it as a `note` so it is not lost. Return \
empty events rather than guessing."""


def extract(kind: str, name: str, text: str, today: str, owner: str = "") -> Optional[Extraction]:
    header = f"Input kind: {kind}\nInput name: {name}\nToday: {today}"
    if owner:
        header += f"\nThe person this is about: {owner}"
    return _parse(EXTRACT_SYSTEM, f"{header}\n\n<input>\n{text}\n</input>", Extraction)


# --- retrieval planning ---


class PlannedQuery(BaseModel):
    tool: Literal["latest_in_domain", "domain_histogram", "hybrid_search"]
    domain: Optional[Literal["career", "housing", "relationship", "health", "money"]] = None
    text: Optional[str] = None
    reason: str


class QueryPlan(BaseModel):
    queries: list[PlannedQuery]


PLAN_SYSTEM = """You are the retrieval planner for a store of one person's dated life events \
in Elasticsearch. The goal is to fill the empty slots of their present-day state vector with \
as few queries as possible. Tools:
- latest_in_domain(domain): the most recent events in one domain.
- domain_histogram(domain): per-year counts by event type in one domain (date-histogram + \
terms aggregation). Good for activity level and for seeing what kinds of events exist.
- hybrid_search(text): BM25 + dense-vector retrieval over event text, for slots that a domain \
listing is unlikely to surface.
Return an ordered list of at most five queries, each with a one-sentence reason. Skip slots \
that are already filled. You are choosing what to look up — never what the answer is."""


def plan_queries(empty_slots: list[str], filled: dict, already_ran: list[dict]) -> Optional[list[PlannedQuery]]:
    user = f"Empty slots: {empty_slots}\nAlready filled: {filled}\nQueries already run: {already_ran}"
    result = _parse(PLAN_SYSTEM, user, QueryPlan, max_tokens=4000)
    return result.queries[:5] if result else None


# --- (b) narration ---


class NarratedLine(BaseModel):
    event_id: str
    line: str


class Narration(BaseModel):
    lines: list[NarratedLine]


NARRATE_SYSTEM = """You narrate a simulated life, one line per event, in second person. The \
events were decided by a statistical simulation and are fixed: do not add events, remove \
events, change their year, soften them, or hint at what comes next. You may add one small \
concrete detail to a line so it feels lived rather than logged, as long as it changes nothing \
about what happened.

Voice: dry, specific, tender. Short declarative sentences. No exclamation marks, no advice, \
no consolation, and never a probability, likelihood, or statistic. Begin each line with the year and a colon.
Example: "2033: You attend the wedding. Table 9."

Return exactly one line for every event_id you are given."""


def narrate(events: list[dict]) -> Optional[dict[str, str]]:
    result = _parse(NARRATE_SYSTEM, f"Events, in order:\n{events}", Narration)
    if not result:
        return None
    wanted = {e["event_id"] for e in events}
    return {l.event_id: l.line for l in result.lines if l.event_id in wanted}


# --- (a) extraction, continued: options and what-ifs the person wrote themselves ---

FIELD = Literal["education", "arts", "humanities", "social_sciences_law", "business", "sciences",
                "math_cs", "engineering", "agriculture", "health", "services"]


class OptionAssumption(BaseModel):
    city: Optional[str] = None
    country: Optional[str] = None
    employment: Optional[Literal["employed", "unemployed", "student", "retired"]] = None
    field: Optional[FIELD] = None
    occupation: Optional[str] = None
    employer: Optional[str] = None
    salary: Optional[float] = None
    currency: Optional[Literal["CAD", "USD"]] = None
    program: Optional[str] = None
    institution: Optional[str] = None
    graduates_in: Optional[int] = None
    relationship_status: Optional[Literal["single", "married", "divorced", "widowed"]] = None
    housing: Optional[Literal["renting", "owning", "with_family"]] = None
    deadline: Optional[str] = None


ASSUMPTION_SYSTEM = """A person is weighing a decision and has described one option they could \
take. Turn what they wrote into structured fields. This is transcription, not judgement: fill a \
field only when their words (the situation or this option) state or plainly imply it, and leave \
everything else null. `salary` is annual; `graduates_in` is whole years of study remaining under \
this option; `deadline` is an ISO date only if they gave one for deciding. Never add anything \
they did not say, and never assess whether the option is a good idea."""


def extract_assumption(situation: str, title: str, details: str, today: str) -> Optional[OptionAssumption]:
    user = f"Today: {today}\n\nThe situation, in their words:\n{situation}\n\nThis option: {title}\n{details}"
    return _parse(ASSUMPTION_SYSTEM, user, OptionAssumption, max_tokens=3000)


class CommitPatch(BaseModel):
    city: Optional[str] = None
    employment: Optional[Literal["employed", "unemployed", "student", "retired"]] = None
    field: Optional[FIELD] = None
    salary: Optional[float] = None
    currency: Optional[Literal["CAD", "USD"]] = None
    income_band: Optional[Literal["low", "lower_middle", "middle", "upper_middle", "high"]] = None
    graduates_in: Optional[int] = None
    relationship_status: Optional[Literal["single", "married", "divorced", "widowed"]] = None
    housing: Optional[Literal["renting", "owning", "with_family"]] = None


PATCH_SYSTEM = """Inside an imagined future, a person has written a further what-if decision \
("leave to start a company", "move back to Toronto", "go back to school for two years"). Turn \
it into the state changes it directly states or plainly implies at that moment, and leave \
everything else null. Transcribe their decision; do not predict its consequences — the \
simulation does that. Quitting a job to found a company is `employment: employed` with \
`income_band: low` only if they say the money drops; otherwise leave income alone."""


def extract_patch(branch_label: str, year: int, message: str) -> Optional[CommitPatch]:
    return _parse(PATCH_SYSTEM, f"Path: {branch_label}\nYear: {year}\nTheir decision: {message}", CommitPatch, max_tokens=2000)


# --- choosing what to look up on the live web ---


class ResearchQuestion(BaseModel):
    question: str
    search_query: str
    parameter: Literal["salary", "monthly_rent", "home_price", "program_years", "other"]


class ResearchPlan(BaseModel):
    questions: list[ResearchQuestion]


RESEARCH_PLAN_SYSTEM = """A person is about to imagine living one option of a real decision. \
Choose at most four factual things worth looking up on the public web so that life can be \
grounded in the real place, employer or program: typical pay for that role in that city, what \
rent and homes cost there, how long that program takes and what it costs. Prefer questions with \
a checkable figure. Skip anything they already told us. For each, give a web search query a \
careful person would type, and which simulator parameter it informs (`other` if none). You are \
choosing what to look up — never what the answer is, and never anything about a private person."""


def plan_research(situation: str, title: str, details: str, known: dict) -> Optional[list[ResearchQuestion]]:
    user = f"Situation: {situation}\n\nOption: {title}\n{details}\n\nAlready known: {known}"
    result = _parse(RESEARCH_PLAN_SYSTEM, user, ResearchPlan, max_tokens=3000)
    return result.questions[:4] if result else None


class ResearchedFact(BaseModel):
    claim: str
    value: Optional[float] = None
    unit: Optional[str] = None
    currency: Optional[Literal["CAD", "USD"]] = None
    snippet: str


class ResearchedFacts(BaseModel):
    facts: list[ResearchedFact]


FACTS_SYSTEM = """You are reading one public web page to answer one factual question. Report \
at most two facts that the page itself states and that answer the question. For each: `claim` \
is one plain sentence including the place and period it applies to; `value` is the single most \
representative figure as a plain number (annual for pay, monthly for rent, total for a home \
price, years for a program) with `unit` and `currency`; `snippet` is the exact sentence or \
table row from the page that supports it, copied verbatim. If the page does not answer the \
question, return no facts. Never estimate, never use outside knowledge."""


def extract_facts(question: str, url: str, page_text: str) -> Optional[list[ResearchedFact]]:
    user = f"Question: {question}\nPage: {url}\n\n<page>\n{page_text}\n</page>"
    result = _parse(FACTS_SYSTEM, user, ResearchedFacts, max_tokens=3000)
    return result.facts[:2] if result else None


# --- (b) narration, continued: a branch as chapters ---


class ChapterParagraph(BaseModel):
    text: str
    evidence_ids: list[str]


class ChapterDraft(BaseModel):
    title: str
    paragraphs: list[ChapterParagraph]


CHAPTER_SYSTEM = """You are writing one chapter of a life that has not happened. A person is \
deliberating something — it may be one evening or forty years — and a statistical simulation \
has lived one option forward. You are given the fixed skeleton of what happens in this stretch. \
Your job is to let them live inside it. For a night or a week: the phone face-down on the desk, \
what is in the fridge, the walk home, how the morning feels. For years: where they wake up, the \
commute, what the rent does to the month, who is at the table. A small decision deserves the \
same attention as a large one; never inflate it, never wave it away. Second person, present tense. \
Dry, specific, tender. Concrete nouns over adjectives. No advice, no moral, no summing up, no \
foreshadowing, no exclamation marks.

Hard rules.
1. Every simulated event listed appears, in its own step, as something lived.
2. Nothing else *happens*: no job, move, partner, marriage, separation, child, death, purchase \
of a home, illness or change of income that is not in the skeleton. Between events, life is \
texture — rooms, routines, meals, seasons, small habits — and you may invent that freely. \
Unnamed friends may appear; a partner may appear only if the skeleton says married.
3. A decision marked as the person's own commit is theirs: write it as a choice they make.
4. Facts about money and places (pay, rent, prices, program length) come only from the \
evidence list; when a paragraph uses one, put its id in that paragraph's `evidence_ids`. \
Figures from evidence may appear in the prose. When a paragraph rests on a simulated event, cite \
the statistic evidence for it if one is listed. When you call back to their real past, cite \
that personal evidence id.
5. Never state a probability or likelihood in the prose. If the outlook says something is far \
from certain, let it show as contingency in the telling, not as odds.
6. Three to five paragraphs, 60–120 words each. The title is two to five words, not a summary."""


def write_chapter(context: str) -> Optional[ChapterDraft]:
    return _parse(CHAPTER_SYSTEM, context, ChapterDraft, max_tokens=8000)


# --- any decision, any size: proposing what could happen (never how likely in numbers) ---

BIN = Literal["rare", "sometimes", "as often as not", "usually"]


class EventLink(BaseModel):
    key: str
    relation: Literal["likelier", "less_likely", "prevents", "requires"]


class ProposedEvent(BaseModel):
    key: str
    label: str
    domain: str
    kind: Literal["one_time", "recurring", "state"]
    first_step: int
    last_step: int
    bin: BIN
    depends_on: list[EventLink]
    reference_class: Optional[str] = None
    search_query: Optional[str] = None
    follow_through: bool = False


class ProposedOption(BaseModel):
    option_index: int
    events: list[ProposedEvent]


class ProposedQuestion(BaseModel):
    text: str
    why: str
    choices: list[str]
    applies_to_options: list[int]


class ProposedScenario(BaseModel):
    horizon_unit: Literal["days", "weeks", "months", "years"]
    horizon_count: int
    starts_tonight: bool
    options: list[ProposedOption]
    questions: list[ProposedQuestion]


MODEL_SYSTEM = """A person is deliberating something — it may be tiny (text an ex tonight, the \
party or the problem set, a haircut) or large (a move, a job, a degree). For each option they \
described, lay out WHAT COULD HAPPEN if they take it, so that a simulation can live it forward. \
You propose possibilities; you never say what will happen, and you never give a number.

1. Horizon: how far forward this decision actually plays out. `days` (up to 30) for tonight / \
this week; `weeks` (up to 26); `months` (up to 36); `years` (up to 40) for life-shaping choices. \
Steps are numbered 0..count-1; step 0 is today (or this week / this month / next year). If the \
horizon is given to you, use it as given.
2. For each option, 8 to 14 possible events, genuinely about THAT option. Three universities \
are three different places — different programs, co-op or not, residence or a commute, a \
different city, different people — not one list with the name swapped. The person may have \
written almost nothing (a sentence and the option names): that is enough; use what you know of \
the named places, programs, habits and situations to make each option concrete. Specific and human, in second person, the way the \
person would recognise them: "they reply within a day", "you sleep under five hours", "you are \
still not drinking at week four", "the loan comes back on time", "you stop going after the third \
session". Cover the near consequence and the slower ones, the good, the bad and the merely \
awkward. Include two or three that are unlikely but would matter or be interesting if they \
happened. No event may be about a named or identifiable third person's private life.
3. Track the outcomes the person actually cares about in EVERY option under the same `key` \
(for instance `regret_next_morning`, `sleep_under_five_hours`, `still_talking_in_a_month`), so \
the options can be compared on them. At least three shared keys.
4. Each event: `key` (snake_case), `label`, `domain` (a lowercase life-area tag such as work, \
money, health, body, mind, love, family, friends, learning, growth, home, play, food), `kind` \
(`one_time` happens at most once; `state` becomes true and stays true; `recurring` can happen \
in any step), the window of steps in which it can happen, and `depends_on` other keys of the \
same option (`likelier`, `less_likely`, `prevents`, `requires`).
5. `bin` is your only statement about likelihood, and it is verbal: how often this happens to \
people in this situation within its window (for `recurring`: in any one step) — rare, \
sometimes, as often as not, usually. It is used only if no published figure can be found.
6. Nobody publishes a statistic about this person's exact event, so never look for one. For an \
event where it helps, name the nearest researchable REFERENCE CLASS — the studied population \
whose published rate is the closest honest stand-in — as one phrase in `reference_class`, and a \
`search_query` that targets that class. Examples: "they reply within a day" -> "response and \
reconciliation rates among former partners"; "you finish the degree" -> "graduation and \
first-year retention rates for that university and program"; "still not drinking at week \
four" -> "completion rates in one-month alcohol abstinence challenges". Leave both null when no \
such class plausibly has published figures. At most four per option; prefer what matters most.
7. Set `follow_through` true on events that are simply the person keeping a commitment they \
themselves set (finishing the month, sticking to the plan).
8. `questions`: at most three, often none. Ask only what (a) is not already answered in what \
their log says, and (b) would materially change what could happen in at least one option — \
for a choice of university, the intended major; for a move, whether a partner comes too. Each \
has a short `why` clause, two to five quick `choices`, and the option indexes it applies to \
(empty = all). Never ask for anything just to be thorough, and never for a probability."""


def propose_scenario_model(situation: str, options: list[dict], horizon: Optional[dict], about: str,
                           known: str = "") -> Optional[ProposedScenario]:
    listed = "\n".join(f"Option {i}: {o['title']}. {o['details']}" for i, o in enumerate(options))
    fixed = f"\nThe horizon is fixed: {horizon['count']} {horizon['unit']}." if horizon else ""
    user = (f"About the person (background only): {about}\n\nWhat their log already says (do not ask about any of "
            f"this):\n{known or '(nothing relevant found)'}\n\nThe situation, in their words:\n{situation}\n\n{listed}{fixed}")
    return _parse(MODEL_SYSTEM, user, ProposedScenario, max_tokens=16000, fast=True)


class PublishedRate(BaseModel):
    claim: str
    figure_as_written: str
    span_days: Optional[int] = None
    snippet: str
    gap: str = ""
    gap_is_large: bool = True


class PublishedRates(BaseModel):
    rates: list[PublishedRate]


RATE_SYSTEM = """You are reading one public web page to find a published rate for a REFERENCE CLASS: a \
studied population that is the nearest honest stand-in for one person's possible event. Nobody \
has studied this person; you are looking for how often it happens in the class. Report at most one rate, and only if the \
page itself states it. `claim` is one plain sentence saying what the figure measures, for whom, \
and over what period. `figure_as_written` is the figure exactly as it appears on the page — for \
example "23%", "1 in 4", "41 per 1,000" — copied character for character. `span_days` is the \
period the figure covers in days (a year is 365) or null if it is not tied to a period. \
`snippet` is the full sentence or table row containing the figure, copied verbatim. `gap` is \
one plain sentence on how the studied population differs from this person's situation, and \
`gap_is_large` says whether that difference is substantial (different country, age group, \
decade, or a looser definition of the event) — describe the gap, never adjust the figure. If the \
page gives no such rate, return none. Also return none when the figure measures something \
materially different from the event — a usual habit rather than one particular night, a \
different outcome, a different kind of person altogether: a wrong stand-in is worse than an \
honest estimate. Never estimate, convert, round, or use outside knowledge: \
code will check that your figure appears in your snippet, and discard it if it does not."""


def extract_rate(event_label: str, reference_class: str, url: str, page_text: str) -> Optional[PublishedRate]:
    user = f"The person's possible event: {event_label}\nReference class to find a rate for: {reference_class}\nPage: {url}\n\n<page>\n{page_text}\n</page>"
    result = _parse(RATE_SYSTEM, user, PublishedRates, max_tokens=3000)
    return result.rates[0] if result and result.rates else None


class ModelPatch(BaseModel):
    force: list[str]
    prevent: list[str]
    likelier: list[str]
    less_likely: list[str]


MODEL_PATCH_SYSTEM = """Inside an imagined future, the person has written a further decision of \
their own. You are given the keys and labels of the possible events on this path. Say which of \
them their decision directly makes happen (`force`), rules out (`prevent`), or plainly makes \
more or less likely (`likelier`, `less_likely`). Use only the given keys; leave lists empty \
when the decision does not speak to an event. Transcribe the decision; do not predict."""


def extract_model_patch(message: str, events: list[dict]) -> Optional[ModelPatch]:
    listed = "\n".join(f"{e['key']}: {e['label']}" for e in events)
    return _parse(MODEL_PATCH_SYSTEM, f"Their decision: {message}\n\nPossible events:\n{listed}", ModelPatch, max_tokens=2000)


# --- the life script is opt-in ---


class LifeScript(BaseModel):
    partner: bool
    children: bool
    home: bool
    because: str


LIFE_SCRIPT_SYSTEM = """Hereafter does not assume anyone wants a partner, children or to buy a \
home. From the person's own words and the excerpts of their log below, say for each whether it \
is ALREADY part of their life or something they have said they WANT: `partner` (a partner, \
marriage, a relationship they are in or looking for), `children`, `home` (owning or saving to \
own). True only on their own evidence; silence means false. `because` is one short sentence \
quoting or pointing at what you relied on, or "nothing in their log or words" if all are false."""


def extract_life_script(situation: str, known: str) -> Optional[LifeScript]:
    return _parse(LIFE_SCRIPT_SYSTEM, f"Their words:\n{situation}\n\nFrom their log:\n{known or '(nothing)'}", LifeScript, max_tokens=1500)


# --- Jev: judging what was proposed (classify, score, check prerequisites — never a probability) ---

CATEGORY = Literal["career", "education", "research", "entrepreneurship", "financial", "social", "location",
                   "health", "relationship", "other"]


class Prerequisite(BaseModel):
    requirement: str
    met: Literal["yes", "no", "unknown"]
    basis: str


class JudgedEvent(BaseModel):
    key: str
    category: CATEGORY
    personal_fit: int
    experience_fit: int
    difficulty: int
    accessibility: int
    evidence_strength: int
    prerequisites: list[Prerequisite]
    rationale: str


class Judgement(BaseModel):
    events: list[JudgedEvent]


JEV_SYSTEM = """You are Jev, the judge in a life-decision simulator. Other parts of the system \
have already proposed possible events for one option of a decision the person is weighing. You do \
not generate events and you do NOT estimate how likely any event is: a separate probability model \
does that. You classify and score each event you are given, using only the person's own record \
and the evidence provided.

For every event, return:
- `category`: the one outcome type it belongs to (career, education, research, entrepreneurship, \
financial, social, location, health, relationship, other).
- Five integer scores from 1 to 5 (3 = cannot tell / typical):
  `personal_fit`: how well this outcome matches what the person has said they want, value, or \
tend to do.
  `experience_fit`: how well their skills, education and past work match what the outcome asks of them.
  `difficulty`: how hard the outcome is for a typical person in that situation, whatever the \
person's own strengths (5 = very selective or demanding).
  `accessibility`: how open the route is to THIS person right now (cost, location, eligibility, \
time, who they know) (5 = wide open).
  `evidence_strength`: how strongly the evidence provided (their record, and any published \
figure listed under the event) bears on this specific outcome (1 = nothing relevant, 5 = direct \
and specific).
- `prerequisites`: only HARD requirements that must hold for the outcome to be possible at all \
(a degree, a citizenship or visa, a minimum grade, a licence, a minimum age) — not preferences. \
For each, `met` is "yes" only if the person's record shows it, "no" only if the record shows \
they do not meet it, otherwise "unknown". `basis` is one short phrase pointing at what you relied on. \
Return an empty list when there are none.
- `rationale`: one plain sentence on the scores.

Rules. Judge only from what is given: silence in the record means 3 for the two fit scores and \
"unknown" for prerequisites, never a guess in either direction. Never invent facts about the \
person. Never output a probability, percentage or likelihood in any field. Return exactly one entry \
for every event key you are given, using the same key."""


def judge_events(about: str, record: str, option: str, events: list[dict]) -> Optional[Judgement]:
    listed = "\n".join(
        f"- key={e['key']} | {e['label']} | area: {e['domain']} | reference class: {e.get('reference_class') or 'none'}"
        f" | basis so far: {e['basis']}" for e in events)
    user = (f"About the person (background only): {about}\n\nThe option being judged: {option}\n\n"
            f"Their own record, retrieved for this option:\n{record or '(nothing relevant found)'}\n\n"
            f"Events to judge:\n{listed}")
    return _parse(JEV_SYSTEM, user, Judgement, max_tokens=8000, fast=True)
