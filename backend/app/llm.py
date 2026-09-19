"""The only three things the LLM is allowed to do: extract structure from messy input (pages,
the person's own words, their options and what-ifs), pick what to look up (Elastic queries,
research questions), and narrate a life that the simulator already decided.
It never sees a request to invent, choose, or weigh a future. Every function here returns
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


def _parse(system: str, user: str, schema: type[BaseModel], max_tokens: int = 16000, fast: bool = False,
           model: str = ""):
    """One structured-output call. Returns the parsed model, or None on any failure."""
    if not enabled():
        return None
    effort = config.LLM_FAST_EFFORT if fast or model else ""
    model = model or (config.LLM_FAST_MODEL if fast else config.LLM_MODEL)
    try:
        if config.LLM_PROVIDER == "openai":
            return _parse_openai(system, user, schema, max_tokens, model, effort)
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
    income: Optional[float] = None      # yearly, only if they state it
    net_worth: Optional[float] = None   # only if they state it
    currency: Optional[str] = None


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

1. `events`: dated things that happened to this person. Write `date` at exactly the precision \
the input supports and no finer: "YYYY-MM-DD" for a day, "YYYY-MM" for a month, "YYYY" for a \
year (a season or term such as "Summer 2021" is "2021"). Never pad a year to January or a month \
to its first day, and never use today's date for something the input does not date: leave \
`date` null instead. A \
`domain` (a lowercase life-area tag: use career, housing, relationship, money or health when \
the event establishes where they work, live, who they are with, what they earn or their \
health; otherwise whatever fits — family, friends, learning, growth, body, mind, play, food), \
a snake_case event_type (education, graduation, job_start, job_change, job_end, \
city_move, marriage, divorce, birth, home_purchase, project, social_activity, \
decision_pending, goal_set, goal_kept, goal_dropped, note), a short factual `text`, and a confidence between 0 and 1 for how \
directly the input supports it. Fill an event's state fields only when that event \
establishes them. `birth` always means a child born to this person; their own birth is \
not an event (put the year in `facts.birth_year`). `facts.income` (yearly), `facts.net_worth` and `facts.currency` only when \
they state a figure themselves; never guess.
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
no consolation, and never a probability, likelihood, or statistic. Begin each line with the year and a colon. \
Tell time in dates and plain words, never as "day 3" or "week 2".
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
    recap: str = ""


class BiblePerson(BaseModel):
    name: str
    role: str


class StoryBible(BaseModel):
    setting: str
    neighbourhood: str
    people: list[BiblePerson]


BIBLE_SYSTEM = """You are fixing the invented texture of one imagined path through someone's \
life, once, so that every chapter written later agrees with every other. Invent, plainly and \
plausibly for the option described: `setting` — one line on the workplace, school, venue or \
whatever the path mostly happens in (a kind of place, not a real named small business); \
`neighbourhood` — one line on where they live or spend their time on this path; and `people` — \
two or three recurring figures with a first name and a role ("Dario, the teammate who sits \
opposite"). These people are INVENTED: never use a real person from their life unless the \
person named them in their own words, which are given to you. Keep it modest and specific."""


def write_bible(context: str) -> Optional[StoryBible]:
    return _parse(BIBLE_SYSTEM, context, StoryBible, max_tokens=1500, fast=True)


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
5a. You are told, in words, how the person is doing on health, joy, fulfilment and money by the \
end of this stretch relative to now. Let it colour the telling (tired, flush, restless, settled) — \
never as a score, a number or a list.
5. Never state a probability or likelihood in the prose. If the outlook says something is far \
from certain, let it show as contingency in the telling, not as odds.
6. Order. The chapter follows the dated events in the order given and never reorders them. \
If the skeleton begins with the choice itself (marked STEP ZERO), the chapter OPENS on it: the \
moment of choosing and that first day, before anything else.
7. Continuity. Use the STORY BIBLE exactly as given — the same setting, the same neighbourhood, \
the same two or three named people — and pick up from THE STORY SO FAR. Never contradict \
either, never rename anyone, and introduce no other named characters.
8. `recap`: two plain sentences saying where things stand as this chapter ends, for whoever \
writes the next one.
9. Time is told in dates and plain words ("on 21 September", "that Friday", "the next \
morning", "by spring"). Never "day 3", "week 2", "month 4" or any other count of steps.
10. Three to five paragraphs, 60–120 words each. The title is two to five words, not a summary."""


def write_chapter(context: str) -> Optional[ChapterDraft]:
    return _parse(CHAPTER_SYSTEM, context, ChapterDraft, max_tokens=8000)


# --- any decision, any size: proposing what could happen (never how likely in numbers) ---

BIN = Literal["rare", "sometimes", "as often as not", "usually", "almost certainly"]


class EventLink(BaseModel):
    key: str
    relation: Literal["likelier", "less_likely", "prevents"]


class TraitLink(BaseModel):
    trait: Literal["O", "C", "E", "A", "N"]
    effect: Literal["raises", "lowers"]


class Effects(BaseModel):
    health: int = 0
    joy: int = 0
    fulfilment: int = 0
    money: int = 0


class MoneyAmount(BaseModel):
    value: float
    currency: str
    per: Literal["once", "month", "year"]


class ProposedEvent(BaseModel):
    key: str
    label: str
    domain: str
    phase: Literal["right_away", "settling_in", "later"]
    from_day: int
    to_day: int
    after: list[str] = []
    requires: list[str] = []
    depends_on: list[EventLink] = []
    bin: BIN
    kind: Literal["one_time", "recurring", "state"] = "one_time"
    reference_class: Optional[str] = None
    search_query: Optional[str] = None
    follow_through: bool = False
    hazard: Optional[Literal["marriage", "divorce", "fertility", "migration", "job_change", "mortality"]] = None
    traits: list[TraitLink] = []
    effects: Effects = Effects()
    money_amount: Optional[MoneyAmount] = None
    money_kind: Optional[Literal["salary", "rent", "tuition", "loan", "other"]] = None


class ProposedOption(BaseModel):
    option_index: int
    choice_label: str
    choice_effects: Effects = Effects()
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
    scale: Literal["big", "small"] = "small"
    options: list[ProposedOption]
    questions: list[ProposedQuestion]


MODEL_SYSTEM = """A person is deliberating something — it may be tiny (text an ex tonight, the \
party or the problem set) or large (a move, a job, a degree). For each option they described, \
lay out WHAT COULD HAPPEN if they take it, as a causal story a simulation can live forward. You \
propose possibilities; you never say what will happen, and you never give a number.

1. Horizon: the stretch where this decision actually plays out, and no longer. `days` (up to \
30) for tonight or this week; `weeks` (up to 26); `months` (up to 36); `years` for a life \
decision: 3 by default, never more than 5. If the horizon is given to you, use it as given. \
`scale` is `big` for a life decision (six months or more) and `small` for a day-to-day one.
2. `choice_label`: the option as the first thing that happens, second person, present tense: \
"You accept the offer", "You go to the housewarming", "You say no". The simulation adds it \
itself as day 0; do not repeat it among the events.
3. For each option, 10 to 14 possible events that are CONSEQUENCES OF THAT OPTION, told in \
three phases, in order:
   - `right_away`: the obvious first consequences, which must be there — the job starts, the \
move happens, the first day, the first week, the message is read, the money leaves the account;
   - `settling_in`: what the first months (or, for a small decision, the next days) bring;
   - `later`: where it can lead by the end of the horizon, including two or three unlikely \
outcomes that would matter.
   Each event is a MOMENT — something that happens on a day — never a standing state: "you \
make your first friend outside work", not "you have friends who are not from work"; "you sign \
a lease on a room", not "you live in a shared flat". Nothing generic that would be equally true \
on any path (no "you feel stressed sometimes"). Specific, human, second person. Three \
universities are three different places; use what you know of the named places, programs, \
employers and situations even when the person wrote almost nothing. No event may be about a \
named or identifiable third person's private life. A label never counts days or weeks.
4. When: `from_day` and `to_day` are days after the decision (0 = the day of the decision) \
between which the moment can fall, matching its phase. A first day at a job that starts in \
January, decided in September, is around day 105, not day 0.
5. Order and cause. `after`: keys of events this one cannot come before (you cannot be \
promoted before you start; you cannot miss home before you have moved). `requires`: keys of \
events without which this one cannot happen at all (no second date without a first). \
`depends_on`: other events that make it `likelier`, `less_likely`, or that it `prevents`. Every \
settling-in and later event should hang off at least one earlier event through `after` or \
`requires`, so the path reads as one story rather than a list.
6. Wherever the same thing can happen on more than one option, use the SAME `key` on each (for \
instance `regret_the_choice`, `first_real_friend_there`, `money_runs_tight`), so the options \
can be compared. At least three shared keys.
7. Each event also has: `key` (snake_case), `domain` (a lowercase life-area tag such as work, \
money, health, body, mind, love, family, friends, learning, growth, home, play, food), and \
`kind`: `one_time` almost always; `recurring` only for something that genuinely happens again \
and again.
8. `bin` is your only statement about likelihood, and it is verbal: how often this happens to \
people in this situation within its window, GIVEN that whatever it requires has happened — \
rare, sometimes, as often as not, usually, almost certainly. The obvious first consequences of \
a choice (you sign, you move, the first day comes) are `almost certainly`; do not hedge them, \
or the path never gets started. It is used only if no published figure is found.
9. Nobody publishes a statistic about this person's exact event, so never look for one. For an \
event where it helps, name the nearest researchable REFERENCE CLASS — the studied population \
whose published rate is the closest honest stand-in — as one phrase in `reference_class`, and a \
`search_query` that targets that class. Examples: "they reply within a day" -> "response and \
reconciliation rates among former partners"; "you finish the degree" -> "graduation and \
first-year retention rates for that university and program". Leave both null when no such \
class plausibly has published figures. At most four per option; prefer what matters most.
10. Set `follow_through` true on events that are simply the person keeping a commitment they \
themselves set (finishing the month, sticking to the plan).
11. Personality. If, and only if, one of the Big Five traits (O openness, C conscientiousness, \
E extraversion, A agreeableness, N neuroticism) plainly bears on whether this event happens to \
someone, name at most two in `traits`, each with an `effect`: `raises` if people higher in the \
trait are more likely to have it happen, `lowers` if less likely. A direction only — never a \
size, which is fixed elsewhere. Leave `traits` empty when unsure. If the event IS one of these \
life-course transitions — marriage, divorce, fertility (having a child), migration (moving \
city or country), job_change, mortality — name it in `hazard`.
12. What each moment MEANS, as change from how the person is now, on four measures: `health`, \
`joy` (short-term happiness, a pulse that fades in days), `fulfilment` (the long-term kind) and \
`money`. Each is an integer from -2 to +2, and 0 for most. This is a judgement about what the \
event means if it happens — never about whether it happens. The choice itself has \
`choice_effects` too. If THE PERSON'S OWN WORDS give a real figure that belongs to this moment (a \
salary that starts, a rent, tuition, a loan), copy it into `money_amount`: `value` signed \
(positive coming in, negative going out), `currency`, and `per` (once / month / year). Never \
estimate an amount. If no figure is given but a real one would apply, name its `money_kind` so \
research can attach one.
13. `questions`: at most three, often none. Ask only what (a) is not already answered in what \
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


# --- reading a one-line decision ---


class Ticket(BaseModel):
    situation: str
    options: list[str]


TICKET_SYSTEM = """Someone has written down a decision they are turning over, the way they would \
write a ticket or a commit message: plainly, in one or two lines. Return `situation` (their own \
words, lightly tidied, never embellished) and `options`: the two to four things they could do, as \
short titles in their own words. If they name only one course of action, the second option is \
simply not doing it, phrased naturally. Never add an option they did not name or clearly imply."""


def extract_ticket(text: str) -> Optional[Ticket]:
    return _parse(TICKET_SYSTEM, text, Ticket, max_tokens=2000, model=config.LLM_TICKET_MODEL)
