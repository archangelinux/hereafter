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


# --- an option in the person's words -> the assumption it makes

class OptionAssumption(BaseModel):
    city: str | None = None
    country: str | None = None
    employment: Literal['employed', 'unemployed', 'student', 'retired'] | None = None
    field: Literal['education', 'arts', 'humanities', 'social_sciences_law', 'business', 'sciences', 'math_cs', 'engineering', 'agriculture', 'health', 'services'] | None = None
    occupation: str | None = None
    employer: str | None = None
    salary: float | None = None
    currency: Literal['CAD', 'USD'] | None = None
    program: str | None = None
    institution: str | None = None
    graduates_in: int | None = None
    relationship_status: Literal['single', 'married', 'divorced', 'widowed'] | None = None
    housing: Literal['renting', 'owning', 'with_family'] | None = None
    deadline: str | None = None

ASSUMPTION_SYSTEM = """A person is weighing a decision and has described one option they could take. Turn what they wrote into structured fields. This is transcription, not judgement: fill a field only when their words (the situation or this option) state or plainly imply it, and leave everything else null. `salary` is annual; `graduates_in` is whole years of study remaining under this option; `deadline` is an ISO date only if they gave one for deciding. Never add anything they did not say, and never assess whether the option is a good idea."""

def extract_assumption(situation: str, title: str, details: str, today: str) -> Optional[OptionAssumption]:
    user = f"Today: {today}\n\nThe situation, in their words:\n{situation}\n\nThis option: {title}\n{details}"
    return _parse(ASSUMPTION_SYSTEM, user, OptionAssumption, 3000)


# --- a commit: one step the person adds to a path

class CommitPatch(BaseModel):
    city: str | None = None
    employment: Literal['employed', 'unemployed', 'student', 'retired'] | None = None
    field: Literal['education', 'arts', 'humanities', 'social_sciences_law', 'business', 'sciences', 'math_cs', 'engineering', 'agriculture', 'health', 'services'] | None = None
    salary: float | None = None
    currency: Literal['CAD', 'USD'] | None = None
    income_band: Literal['low', 'lower_middle', 'middle', 'upper_middle', 'high'] | None = None
    graduates_in: int | None = None
    relationship_status: Literal['single', 'married', 'divorced', 'widowed'] | None = None
    housing: Literal['renting', 'owning', 'with_family'] | None = None

class ModelPatch(BaseModel):
    force: list[str]
    prevent: list[str]
    likelier: list[str]
    less_likely: list[str]

PATCH_SYSTEM = """Inside an imagined future, a person has written a further what-if decision ("leave to start a company", "move back to Toronto", "go back to school for two years"). Turn it into the state changes it directly states or plainly implies at that moment, and leave everything else null. Transcribe their decision; do not predict its consequences — the simulation does that. Quitting a job to found a company is `employment: employed` with `income_band: low` only if they say the money drops; otherwise leave income alone."""

MODEL_PATCH_SYSTEM = """Inside an imagined future, the person has written a further decision of their own. You are given the keys and labels of the possible events on this path. Say which of them their decision directly makes happen (`force`), rules out (`prevent`), or plainly makes more or less likely (`likelier`, `less_likely`). Use only the given keys; leave lists empty when the decision does not speak to an event. Transcribe the decision; do not predict."""

def extract_patch(branch_label: str, year: int, message: str) -> Optional[CommitPatch]:
    return _parse(PATCH_SYSTEM, f"Path: {branch_label}\nYear: {year}\nTheir decision: {message}", CommitPatch, 2000)

def extract_model_patch(message: str, events: list[dict]) -> Optional[ModelPatch]:
    listed = "\n".join(f"- {e['key']}: {e['label']}" for e in events)
    return _parse(MODEL_PATCH_SYSTEM, f"Their decision: {message}\n\nPossible events:\n{listed}", ModelPatch, 2000)


# --- choosing what to look up, and reading it back

class ResearchQuestion(BaseModel):
    question: str
    search_query: str
    parameter: Literal['salary', 'monthly_rent', 'home_price', 'program_years', 'other']

class ResearchPlan(BaseModel):
    questions: list[ResearchQuestion]

class ResearchedFact(BaseModel):
    claim: str
    value: float | None = None
    unit: str | None = None
    currency: Literal['CAD', 'USD'] | None = None
    snippet: str

class ResearchedFacts(BaseModel):
    facts: list[ResearchedFact]

class PublishedRate(BaseModel):
    claim: str
    figure_as_written: str
    span_days: int | None = None
    snippet: str
    gap: str = ''
    gap_is_large: bool = True

class PublishedRates(BaseModel):
    rates: list[PublishedRate]

RESEARCH_PLAN_SYSTEM = """A person is about to imagine living one option of a real decision. Choose at most four factual things worth looking up on the public web so that life can be grounded in the real place, employer or program: typical pay for that role in that city, what rent and homes cost there, how long that program takes and what it costs. Prefer questions with a checkable figure. Skip anything they already told us. For each, give a web search query a careful person would type, and which simulator parameter it informs (`other` if none). You are choosing what to look up — never what the answer is, and never anything about a private person."""

FACTS_SYSTEM = """You are reading one public web page to answer one factual question. Report at most two facts that the page itself states and that answer the question. For each: `claim` is one plain sentence including the place and period it applies to; `value` is the single most representative figure as a plain number (annual for pay, monthly for rent, total for a home price, years for a program) with `unit` and `currency`; `snippet` is the exact sentence or table row from the page that supports it, copied verbatim. If the page does not answer the question, return no facts. Never estimate, never use outside knowledge."""

RATE_SYSTEM = """You are reading one public web page to find a published rate for a REFERENCE CLASS: a studied population that is the nearest honest stand-in for one person's possible event. Nobody has studied this person; you are looking for how often it happens in the class. Report at most one rate, and only if the page itself states it. `claim` is one plain sentence saying what the figure measures, for whom, and over what period. `figure_as_written` is the figure exactly as it appears on the page — for example "23%", "1 in 4", "41 per 1,000" — copied character for character. `span_days` is the period the figure covers in days (a year is 365) or null if it is not tied to a period. `snippet` is the full sentence or table row containing the figure, copied verbatim. `gap` is one plain sentence on how the studied population differs from this person's situation, and `gap_is_large` says whether that difference is substantial (different country, age group, decade, or a looser definition of the event) — describe the gap, never adjust the figure. If the page gives no such rate, return none. Also return none when the figure measures something materially different from the event — a usual habit rather than one particular night, a different outcome, a different kind of person altogether: a wrong stand-in is worse than an honest estimate. Never estimate, convert, round, or use outside knowledge: code will check that your figure appears in your snippet, and discard it if it does not."""

def plan_research(situation: str, title: str, details: str, known: dict) -> Optional[list[ResearchQuestion]]:
    user = f"Situation: {situation}\n\nOption: {title}\n{details}\n\nAlready known: {known}"
    found = _parse(RESEARCH_PLAN_SYSTEM, user, ResearchPlan, 3000)
    return found.questions if found else None

def extract_facts(question: str, url: str, page_text: str) -> Optional[list[ResearchedFact]]:
    user = f"Question: {question}\nPage: {url}\n\n<page>\n{page_text}\n</page>"
    found = _parse(FACTS_SYSTEM, user, ResearchedFacts, 3000)
    return found.facts if found else None

def extract_rate(event_label: str, reference_class: str, url: str, page_text: str) -> Optional[PublishedRate]:
    user = (f"The person's possible event: {event_label}\nReference class to find a rate for: {reference_class}"
            f"\nPage: {url}\n\n<page>\n{page_text}\n</page>")
    found = _parse(RATE_SYSTEM, user, PublishedRates, 3000)
    return found.rates[0] if found and found.rates else None


# --- what could happen on each option, and what to ask

class EventLink(BaseModel):
    key: str
    relation: Literal['likelier', 'less_likely', 'prevents']

class TraitLink(BaseModel):
    trait: Literal['O', 'C', 'E', 'A', 'N']
    effect: Literal['raises', 'lowers']

class Effects(BaseModel):
    health: int = 0
    joy: int = 0
    fulfilment: int = 0
    money: int = 0

class MoneyAmount(BaseModel):
    value: float
    currency: str
    per: Literal['once', 'month', 'year']

class ProposedEvent(BaseModel):
    key: str
    label: str
    domain: str
    phase: Literal['right_away', 'settling_in', 'later']
    from_day: int
    to_day: int
    after: list[str] = []
    requires: list[str] = []
    depends_on: list[EventLink] = []
    bin: Literal['rare', 'sometimes', 'as often as not', 'usually', 'almost certainly']
    kind: Literal['one_time', 'recurring', 'state'] = 'one_time'
    reference_class: str | None = None
    search_query: str | None = None
    follow_through: bool = False
    hazard: Literal['marriage', 'divorce', 'fertility', 'migration', 'job_change', 'mortality'] | None = None
    traits: list[TraitLink] = []
    effects: Effects = Effects(health=0, joy=0, fulfilment=0, money=0)
    money_amount: MoneyAmount | None = None
    money_kind: Literal['salary', 'rent', 'tuition', 'loan', 'other'] | None = None

class ProposedOption(BaseModel):
    option_index: int
    choice_label: str
    choice_effects: Effects = Effects(health=0, joy=0, fulfilment=0, money=0)
    events: list[ProposedEvent]

class ProposedQuestion(BaseModel):
    text: str
    why: str
    choices: list[str]
    applies_to_options: list[int]

class ProposedScenario(BaseModel):
    horizon_unit: Literal['days', 'weeks', 'months', 'years']
    horizon_count: int
    starts_tonight: bool
    scale: Literal['big', 'small'] = 'small'
    options: list[ProposedOption]
    questions: list[ProposedQuestion]

class LifeScript(BaseModel):
    partner: bool
    children: bool
    home: bool
    because: str

MODEL_SYSTEM = """A person is deliberating something — it may be tiny (text an ex tonight, the party or the problem set) or large (a move, a job, a degree). For each option they described, lay out WHAT COULD HAPPEN if they take it, as a causal story a simulation can live forward. You propose possibilities; you never say what will happen, and you never give a number.

1. Horizon: the stretch where this decision actually plays out, and no longer. `days` (up to 30) for tonight or this week; `weeks` (up to 26); `months` (up to 36); `years` for a life decision: 3 by default, never more than 5. If the horizon is given to you, use it as given. `scale` is `big` for a life decision (six months or more) and `small` for a day-to-day one.
2. `choice_label`: the option as the first thing that happens, second person, present tense: "You accept the offer", "You go to the housewarming", "You say no". The simulation adds it itself as day 0; do not repeat it among the events.
3. For each option, 10 to 14 possible events that are CONSEQUENCES OF THAT OPTION, told in three phases, in order:
   - `right_away`: the obvious first consequences, which must be there — the job starts, the move happens, the first day, the first week, the message is read, the money leaves the account;
   - `settling_in`: what the first months (or, for a small decision, the next days) bring;
   - `later`: where it can lead by the end of the horizon, including two or three unlikely outcomes that would matter.
   Each event is a MOMENT — something that happens on a day — never a standing state: "you make your first friend outside work", not "you have friends who are not from work"; "you sign a lease on a room", not "you live in a shared flat". Nothing generic that would be equally true on any path (no "you feel stressed sometimes"). Specific, human, second person. Three universities are three different places; use what you know of the named places, programs, employers and situations even when the person wrote almost nothing. No event may be about a named or identifiable third person's private life. A label never counts days or weeks.
4. When: `from_day` and `to_day` are days after the decision (0 = the day of the decision) between which the moment can fall, matching its phase. A first day at a job that starts in January, decided in September, is around day 105, not day 0.
5. Order and cause. `after`: keys of events this one cannot come before (you cannot be promoted before you start; you cannot miss home before you have moved). `requires`: keys of events without which this one cannot happen at all (no second date without a first). `depends_on`: other events that make it `likelier`, `less_likely`, or that it `prevents`. Every settling-in and later event should hang off at least one earlier event through `after` or `requires`, so the path reads as one story rather than a list.
6. Wherever the same thing can happen on more than one option, use the SAME `key` on each (for instance `regret_the_choice`, `first_real_friend_there`, `money_runs_tight`), so the options can be compared. At least three shared keys.
7. Each event also has: `key` (snake_case), `domain` (a lowercase life-area tag such as work, money, health, body, mind, love, family, friends, learning, growth, home, play, food), and `kind`: `one_time` almost always; `recurring` only for something that genuinely happens again and again.
8. `bin` is your only statement about likelihood, and it is verbal: how often this happens to people in this situation within its window, GIVEN that whatever it requires has happened — rare, sometimes, as often as not, usually, almost certainly. The obvious first consequences of a choice (you sign, you move, the first day comes) are `almost certainly`; do not hedge them, or the path never gets started. It is used only if no published figure is found.
9. Nobody publishes a statistic about this person's exact event, so never look for one. For an event where it helps, name the nearest researchable REFERENCE CLASS — the studied population whose published rate is the closest honest stand-in — as one phrase in `reference_class`, and a `search_query` that targets that class. Examples: "they reply within a day" -> "response and reconciliation rates among former partners"; "you finish the degree" -> "graduation and first-year retention rates for that university and program". Leave both null when no such class plausibly has published figures. At most four per option; prefer what matters most.
10. Set `follow_through` true on events that are simply the person keeping a commitment they themselves set (finishing the month, sticking to the plan).
11. Personality. If, and only if, one of the Big Five traits (O openness, C conscientiousness, E extraversion, A agreeableness, N neuroticism) plainly bears on whether this event happens to someone, name at most two in `traits`, each with an `effect`: `raises` if people higher in the trait are more likely to have it happen, `lowers` if less likely. A direction only — never a size, which is fixed elsewhere. Leave `traits` empty when unsure. If the event IS one of these life-course transitions — marriage, divorce, fertility (having a child), migration (moving city or country), job_change, mortality — name it in `hazard`.
12. What each moment MEANS, as change from how the person is now, on four measures: `health`, `joy` (short-term happiness, a pulse that fades in days), `fulfilment` (the long-term kind) and `money`. Each is an integer from -2 to +2, and 0 for most. This is a judgement about what the event means if it happens — never about whether it happens. The choice itself has `choice_effects` too. If THE PERSON'S OWN WORDS give a real figure that belongs to this moment (a salary that starts, a rent, tuition, a loan), copy it into `money_amount`: `value` signed (positive coming in, negative going out), `currency`, and `per` (once / month / year). Never estimate an amount. If no figure is given but a real one would apply, name its `money_kind` so research can attach one.
13. `questions`: at most three, often none. Ask only what (a) is not already answered in what their log says, and (b) would materially change what could happen in at least one option — for a choice of university, the intended major; for a move, whether a partner comes too. Each has a short `why` clause, two to five quick `choices`, and the option indexes it applies to (empty = all). Never ask for anything just to be thorough, and never for a probability."""

LIFE_SCRIPT_SYSTEM = """Hereafter does not assume anyone wants a partner, children or to buy a home. From the person's own words and the excerpts of their log below, say for each whether it is ALREADY part of their life or something they have said they WANT: `partner` (a partner, marriage, a relationship they are in or looking for), `children`, `home` (owning or saving to own). True only on their own evidence; silence means false. `because` is one short sentence quoting or pointing at what you relied on, or "nothing in their log or words" if all are false."""

def propose_scenario_model(situation: str, options: list[dict], horizon: Optional[dict], about: str,
                           known: str = "") -> Optional[ProposedScenario]:
    listed = "\n".join(f"{i + 1}. {o['title']}\n{o['details']}" for i, o in enumerate(options))
    fixed = f"\nThe horizon is fixed: {horizon['count']} {horizon['unit']}." if horizon else ""
    user = (f"About the person (background only): {about}"
            f"\n\nWhat their log already says (do not ask about any of this):\n{known or '(nothing relevant found)'}"
            f"\n\nThe situation, in their words:\n{situation}{fixed}\n\n{listed}")
    return _parse(MODEL_SYSTEM, user, ProposedScenario, 16000)

def extract_life_script(situation: str, known: str) -> Optional[LifeScript]:
    return _parse(LIFE_SCRIPT_SYSTEM, f"Their words:\n{situation}\n\nFrom their log:\n{known or '(nothing)'}", LifeScript, 1500)


# --- reading a decision written like a ticket

class Ticket(BaseModel):
    situation: str
    options: list[str]

TICKET_SYSTEM = """Someone has written down a decision they are turning over, the way they would write a ticket or a commit message: plainly, in one or two lines. Return `situation` (their own words, lightly tidied, never embellished) and `options`: the two to four things they could do, as short titles in their own words. If they name only one course of action, the second option is simply not doing it, phrased naturally. Never add an option they did not name or clearly imply."""

def extract_ticket(text: str) -> Optional[Ticket]:
    return _parse(TICKET_SYSTEM, text, Ticket, 2000, model=config.LLM_TICKET_MODEL)


# --- Jev: judging what each possible event asks of this person (never how likely it is)

class Prerequisite(BaseModel):
    requirement: str
    met: Literal["yes", "no", "unknown"]
    basis: str


class JudgedEvent(BaseModel):
    key: str
    category: Literal["career", "education", "research", "entrepreneurship", "financial", "social",
                      "location", "health", "relationship", "other"]
    personal_fit: int
    experience_fit: int
    difficulty: int
    accessibility: int
    evidence_strength: int
    prerequisites: list[Prerequisite]
    rationale: str


class Judgement(BaseModel):
    events: list[JudgedEvent]


JUDGE_SYSTEM = """You are Jev. For each possible event on one option a person is weighing, judge \
what it ASKS OF THIS PERSON. You never say how likely anything is — no probabilities, no \
percentages, no "usually" — that is decided elsewhere by simulation.

For every event give:
- `category`: career, education, research, entrepreneurship, financial, social, location, health, \
relationship, or other.
- five scores, each a whole number from 1 to 5, judged for THIS person against THEIR record:
  `personal_fit` (how well it suits what they want and how they are), `experience_fit` (how much \
of it they have already done), `difficulty` (5 = very demanding), `accessibility` (5 = easily \
within reach), `evidence_strength` (5 = their record directly supports it, 1 = nothing in the \
record bears on it). Use 3 when you genuinely cannot tell.
- `prerequisites`: at most four hard requirements this event depends on. Answer each `met` with \
yes / no / unknown from the person's record alone, and say in `basis` which line of the record \
settles it, or that nothing does.
- `rationale`: one short sentence, specific to this person.

Judge only from the record and the option as written. Never invent facts about them, never give \
advice, and never leave out an event you were given."""


def judge_events(about: str, record: str, option: str, events: list[dict]) -> Optional[Judgement]:
    listed = "\n".join(f"- {e['key']}: {e['label']}" for e in events)
    user = (f"About the person: {about or '(little is known)'}"
            f"\n\nTheir own record, as far as it bears on this option:\n{record or '(nothing relevant found)'}"
            f"\n\nThe option: {option}\n\nThe possible events:\n{listed}")
    return _parse(JUDGE_SYSTEM, user, Judgement, 8000)
