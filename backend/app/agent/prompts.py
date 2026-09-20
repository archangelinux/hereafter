"""Everything the language model is asked to do, in one place.

The model has four jobs and none of them is deciding anything:

  imagine   what could happen on each route                       (propose_routes)
  judge     how the person's record bears on each outcome,        (judge_route, judge_priorities)
            what hard requirements it depends on, and how likely
            each is met: the stand-in for Jev
  word      the question that a calculation has already chosen    (write_question)
  read      what a free-text answer settles                       (read_answer)

Every claim about the person carries a citation (context item + a phrase copied from it) that
code checks in verify.py. Every method returns None when the model is off or the call fails, and
the caller degrades instead of guessing.
"""

from __future__ import annotations

import json
from typing import Literal, Optional, Protocol

from pydantic import BaseModel

from .. import llm
from .model import DIMENSION_MEANING, Bin, Dimension

CATEGORY = Literal["career", "education", "research", "entrepreneurship", "financial", "social", "location",
                   "health", "relationship", "other"]


# --- what the model returns ---


class PCite(BaseModel):
    item: int
    quote: str


class PEvent(BaseModel):
    key: str
    label: str
    dimension: Dimension
    valence: Literal[1, -1]
    impact: Literal[1, 2, 3]
    bin: Bin
    category: CATEGORY


class PRoute(BaseModel):
    title: str
    summary: str
    events: list[PEvent]


class RoutesProposal(BaseModel):
    routes: list[PRoute]


class JEvent(BaseModel):
    key: str
    personal_fit: int
    experience_fit: int
    difficulty: int
    accessibility: int
    evidence_strength: int
    cites: list[PCite]
    note: str


class JGate(BaseModel):
    requirement: str
    applies_to: list[str]
    p_typical: float
    p_met: float
    cites: list[PCite]


class RouteJudgement(BaseModel):
    events: list[JEvent]
    gates: list[JGate]


class PriorityP(BaseModel):
    dimension: Dimension
    p: float


class PriorityJudgement(BaseModel):
    probs: list[PriorityP]
    cites: list[PCite]


class QChoice(BaseModel):
    text: str
    resolves: str


class WrittenQuestion(BaseModel):
    question: str
    choices: list[QChoice]
    grounding: list[PCite]


class GapUpdate(BaseModel):
    gap: str
    resolves: str        # "met" | "unmet" | "unclear" for a requirement; a dimension or "unclear" for priorities
    p: float
    quote: str


class AnswerReading(BaseModel):
    updates: list[GapUpdate]


class Brain(Protocol):
    def propose_routes(self, decision: str, options: list[str], record: str, about: str) -> Optional[RoutesProposal]: ...
    def judge_route(self, decision: str, route: dict, record: str) -> Optional[RouteJudgement]: ...
    def judge_priorities(self, decision: str, routes: list[str], record: str) -> Optional[PriorityJudgement]: ...
    def write_question(self, spec: dict, record: str, feedback: list[str]) -> Optional[WrittenQuestion]: ...
    def read_answer(self, question: str, answer: str, gaps: list[dict]) -> Optional[AnswerReading]: ...


# --- prompts ---

DIMENSIONS_TEXT = "\n".join(f"  {d}: {m}" for d, m in DIMENSION_MEANING.items())
NO_INVENTING = ("Use only what is written in the record and the decision. If the record is silent, say so by "
                "using the neutral value; never guess. Never infer health, relationships, religion, politics, "
                "sexuality or any other private fact that the person has not stated about themselves.")

PROPOSE_SYSTEM = f"""You lay out what could happen if a person takes each option of a decision they are weighing. \
You imagine possibilities; you never say what will happen and you never give a number, percentage or probability.

For EACH option give exactly 6 possible outcomes:
- specific to THAT option and to the places, programs, roles or people named in the decision; second person, present \
tense, under 14 words. Two options are two different lives, not one list with a name swapped.
- at least two outcomes the person would want (valence 1), at least two they would not (valence -1), and one that is \
unlikely but would matter if it happened.
- `impact`: how much it would change their life if it happened: 1 = minor, 2 = notable, 3 = life-changing.
- Every outcome must be a meaningful change or risk. Never list trivial or near-certain filler such as "you keep your \
routine" or "nothing changes". Give every option the same ambition: staying put or doing nothing has real costs and real \
upsides too (stagnation, a missed chance, an itch left unresolved), and taking a leap has ordinary outcomes as well.
- `dimension`: the one part of life it mainly touches:
{DIMENSIONS_TEXT}
  Across ALL options use the same dimensions, and give every option outcomes in at least four different dimensions, so \
the options can be compared fairly.
- `bin`: how often this happens to people in this situation in general (not this person): almost certainly, usually, as \
often as not, sometimes, rare.
- `category`: career, education, research, entrepreneurship, financial, social, location, health, relationship or other.
- `key`: snake_case, unique within the option. `summary`: one plain, neutral sentence describing the option itself.

You may use the person's record only to make outcomes concrete (their field, level, city). Do not assert any fact \
about them that the record does not state. {NO_INVENTING} No outcome may be about a named third person's private life."""

JUDGE_SYSTEM = f"""You are Jev, the judge in a decision tool. Outcomes for one route were already imagined by someone \
else. You do NOT imagine outcomes and you do NOT say how likely anything is in the world. You read the person's \
numbered record and judge how it bears on each outcome and on the route.

For every outcome, return five integer scores from 1 to 5 (3 = the record cannot tell):
  personal_fit: does the outcome match what this person has said they want or tend to do?
  experience_fit: do their skills, education and past work match what the outcome asks of them?
  difficulty: how demanding the outcome is for a typical person, whatever this person's strengths (5 = very demanding).
  accessibility: how open the route to it is for THIS person now (cost, location, eligibility, time) (5 = wide open).
  evidence_strength: how directly the record bears on it (1 = not at all, 5 = direct and specific).
`cites`: the record items that justify any score other than the neutral one; each cite is the item number and a phrase \
COPIED EXACTLY from that item (at least three words). A score you cannot back with an exact quote MUST be 3 \
(evidence_strength 1). `note`: one plain sentence.

Then list the route's GATES: 0 to 3 hard requirements that must be true for this route to work at all, where failing \
one would make the route unworkable (right to work or study in a country, an admission or licence requirement, enough \
money to live on, enough free time). Not preferences and not skills; things a person could answer in one line. Word each \
so that "yes" means it is satisfied ("You are allowed to work in Germany"). Skip requirements the record already shows \
are met, and skip any that almost everyone in this situation meets anyway (an application form that anyone can submit, \
having a phone or internet): list only those with real doubt. `applies_to`: the outcome keys that cannot happen without it (empty = all outcomes on the route).
  p_typical: the probability that a TYPICAL person in this broad situation meets the requirement, from general \
knowledge (a base rate, not a claim about this person). Between 0.1 and 0.9. Be honest: "can give notice at a job" is \
usually true (0.9); "is allowed to work in a foreign country" usually is not (0.3).
  p_met: the probability THIS person meets it given the record. It may differ from p_typical ONLY if `cites` (exact \
quotes from the record) show it; otherwise repeat p_typical.

Cite only text that DIRECTLY supports the specific score or requirement. Never stretch an unrelated phrase to justify a \
score: if there is no direct quote, use 3.

{NO_INVENTING} Return one entry per outcome key you were given, using the same key."""

PRIORITY_SYSTEM = f"""You judge what a person seems to care about most when making one particular decision, using only \
their numbered record. The dimensions are:
{DIMENSIONS_TEXT}
Return a probability for each of the five dimensions that it is what matters MOST to them for this decision; they must \
sum to 1. If the record says nothing that bears on it, return 0.2 for each. Move away from 0.2 only for dimensions the \
record supports, and put the supporting evidence in `cites`: item number plus a phrase copied EXACTLY from that item \
(at least three words). With no valid quote you may not deviate from 0.2.
{NO_INVENTING}"""

QUESTION_SYSTEM = f"""You write the single most useful question to ask a person who is deciding something. A \
calculation has ALREADY chosen what we most need to know; you do not choose another topic. You are given the decision, \
that one unknown, what we already know about the person (numbered items), and the questions already asked.

Write a question that:
1. Asks about exactly that unknown and nothing else.
2. Is anchored in something we already know about them, so it could not be asked of a stranger. Cite it in `grounding`: \
the item number and a phrase COPIED EXACTLY from the item (at least three words). Mention the item naturally \
("Your resume says...", "You've been asking about...").
3. Is one sentence, at most 25 words, plain second-person language a thoughtful friend would use.
4. Is neutral: no advice, no judging any option, no hint at which answer is better.
5. Mentions no number, name or fact that is not in the numbered items or the decision.
6. Is one question, not two joined by "and" or "or".
7. Never mentions probabilities, scores or percentages.

For a PRIORITY question do NOT ask "what matters most?" in the abstract. Name the real trade-off that separates THESE \
options and that their record shows they are weighing (for example paying more for one thing against keeping something \
else), and make each choice one concrete way of resolving it, in everyday words ("Pay more to get the co-op", "Keep \
costs low and stay home"). Each choice still resolves to one candidate dimension.

Then give 2 to 4 answer `choices`: the ways a person would truly answer, in their own voice ("Yes, I do"), each at \
most 8 words and clearly different. Include the honest middle when it is real. Each choice has `resolves`:
  - for a REQUIREMENT question: "met" or "unmet" only. At least one of each.
  - for a PRIORITY question: exactly one dimension name (money, growth, stability, wellbeing, freedom). Use the \
candidate dimensions you are given, at least two of them, each worded in everyday language.
Do NOT add "not sure" or "other"; the interface adds those.

Example of the style (different topic, do not reuse): unknown "You hold a valid nursing licence in Alberta"; record item \
[4] "Registered nurse, Ontario, since 2019". Question: "Your profile shows you've worked as a nurse in Ontario since \
2019; do you also hold a licence to practise in Alberta?" grounding: item 4, "worked as a nurse in Ontario" would fail \
because it is not verbatim, so quote "Registered nurse, Ontario, since 2019". Choices: "Yes, I'm licensed there" (met), \
"No, not yet" (unmet).
{NO_INVENTING}"""

READ_SYSTEM = """A person answered a question we asked while helping them decide. You are given their exact words \
and the list of things we are still unsure about (each with an id). Decide which of those unknowns their words \
DIRECTLY settle. For each such unknown return:
  - `gap`: its id.
  - `resolves`: for a requirement, "met" or "unmet" ("unclear" if their words do not settle it); for `priorities`, \
the one dimension they said matters most (money, growth, stability, wellbeing, freedom) or "unclear".
  - `p`: for a requirement, the probability it is satisfied given ONLY their words (0.97 if they clearly said yes, \
0.03 if clearly no, 0.5 if unclear); for priorities, your confidence in the dimension (0.85 if clear).
  - `quote`: the words from their answer, copied exactly, that support it.
Only include unknowns their words speak to directly. Never infer beyond what they wrote, and never guess what they \
meant. If nothing is settled, return an empty list."""


# --- the real thing ---


def _json(o) -> str:
    return json.dumps(o, ensure_ascii=False, indent=1)


class LLMBrain:
    """The language model behind the agent (OpenAI when OPENAI_API_KEY is set; see config.py)."""

    def propose_routes(self, decision, options, record, about):
        user = (f"The decision, in the person's words: {decision}\n\nThe options:\n" + "\n".join(f"- {o}" for o in options)
                + f"\n\nBackground (do not repeat as fact): {about or 'none'}\n\nWhat we know about them:\n{record}")
        return llm._parse(PROPOSE_SYSTEM, user, RoutesProposal, max_tokens=12000, fast=True)

    def judge_route(self, decision, route, record):
        user = (f"The decision: {decision}\n\nThe route being judged: {route['title']}. {route['summary']}\n\n"
                f"Outcomes to judge (key: label):\n" + "\n".join(f"- {e['key']}: {e['label']}" for e in route["events"])
                + f"\n\nThe person's record:\n{record}")
        return llm._parse(JUDGE_SYSTEM, user, RouteJudgement, max_tokens=8000, fast=True)

    def judge_priorities(self, decision, routes, record):
        user = f"The decision: {decision}\nThe options: {', '.join(routes)}\n\nThe person's record:\n{record}"
        return llm._parse(PRIORITY_SYSTEM, user, PriorityJudgement, max_tokens=3000, fast=True)

    def write_question(self, spec, record, feedback):
        user = f"THE UNKNOWN (already chosen):\n{_json(spec)}\n\nWhat we know about them:\n{record}"
        if feedback:
            user += "\n\nYour previous attempt was rejected. Fix ALL of these:\n" + "\n".join(f"- {f}" for f in feedback)
        return llm._parse(QUESTION_SYSTEM, user, WrittenQuestion, max_tokens=4000, fast=True)

    def read_answer(self, question, answer, gaps):
        user = f"The question we asked: {question}\n\nTheir answer, exactly:\n<answer>\n{answer}\n</answer>\n\nOpen unknowns:\n{_json(gaps)}"
        return llm._parse(READ_SYSTEM, user, AnswerReading, max_tokens=3000, fast=True)
