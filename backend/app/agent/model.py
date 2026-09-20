"""The agent's state. Everything here is plain data, so a whole session saves to one JSON file
and loads back exactly.

  ContextItem  one thing known about the person, numbered so a question can point at it
  Route        one option of the decision, lived forward as a handful of possible outcomes
  Event        one possible outcome on a route
  Gate         a hard requirement a route's outcomes depend on, with the probability it is met
  Priorities   what the person seems to care about most, as a probability over dimensions
  QA           one asked question and what came of it
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

DIMENSIONS = ("money", "growth", "stability", "wellbeing", "freedom")
Dimension = Literal["money", "growth", "stability", "wellbeing", "freedom"]
Bin = Literal["almost certainly", "usually", "as often as not", "sometimes", "rare"]
Source = Literal["linkedin", "github", "instagram", "resume", "chat", "web", "told", "other"]

DIMENSION_MEANING = {
    "money": "income and financial security",
    "growth": "learning, skills and career trajectory",
    "stability": "predictability and low risk",
    "wellbeing": "health, stress and time for the rest of life",
    "freedom": "autonomy, flexibility and control over your own time",
}


class ContextItem(BaseModel):
    id: int
    source: str
    date: str = ""
    text: str
    confidence: float = 1.0


class Cite(BaseModel):
    """A pointer into the context: which item, and a phrase copied from it exactly."""

    item: int
    quote: str


class Event(BaseModel):
    key: str
    label: str
    dimension: Dimension
    valence: Literal[1, -1] = 1     # +1 something the person would want, -1 something they would not
    impact: Literal[1, 2, 3] = 2    # how much it would change their life: 1 minor, 2 notable, 3 life-changing
    bin: Bin = "sometimes"
    category: str = "other"
    # Jev's reading of this event against the person's record (1-5, 3 = cannot tell)
    personal_fit: int = 3
    experience_fit: int = 3
    difficulty: int = 3
    accessibility: int = 3
    evidence_strength: int = 1
    cites: list[Cite] = Field(default_factory=list)
    note: str = ""


class Gate(BaseModel):
    id: str
    route_id: str
    requirement: str                # worded so that "yes" means it is satisfied
    applies_to: list[str] = Field(default_factory=list)   # event keys; empty = every event on the route
    p_met: float = 0.5
    basis: Literal["record", "typical", "answer"] = "typical"   # from your record / a typical person's base rate / your answer
    cites: list[Cite] = Field(default_factory=list)
    status: Literal["open", "resolved", "skipped"] = "open"


class Route(BaseModel):
    id: str
    title: str
    summary: str = ""
    events: list[Event] = Field(default_factory=list)


class Priorities(BaseModel):
    probs: dict[str, float] = Field(default_factory=lambda: {d: 1 / len(DIMENSIONS) for d in DIMENSIONS})
    cites: list[Cite] = Field(default_factory=list)
    status: Literal["open", "resolved", "skipped"] = "open"


class Choice(BaseModel):
    text: str
    resolves: str          # "met" | "unmet" for a gate; a dimension name for priorities


class QA(BaseModel):
    n: int
    gap: str               # gate id, or "priorities"
    question: str
    choices: list[Choice]
    grounding: list[Cite]
    why: str
    evpi: float
    flip: float
    fallback: bool = False           # true when the written question failed checks and a plain one was used
    answer: Optional[str] = None
    answer_item: Optional[int] = None
    kind: Literal["choice", "text", "skip"] = "text"
    before: dict[str, float] = Field(default_factory=dict)   # route scores before the answer
    after: dict[str, float] = Field(default_factory=dict)


class Session(BaseModel):
    id: str
    created: str
    decision: str
    who: str                       # "fixture:dev" or "person:p_abc"
    status: Literal["asking", "done", "decided"] = "asking"
    items: list[ContextItem] = Field(default_factory=list)
    routes: list[Route] = Field(default_factory=list)
    gates: list[Gate] = Field(default_factory=list)
    priorities: Priorities = Field(default_factory=Priorities)
    qas: list[QA] = Field(default_factory=list)
    initial_scores: dict[str, float] = Field(default_factory=dict)
    decided_route: Optional[str] = None
    stop_reason: str = ""
    warnings: list[str] = Field(default_factory=list)
