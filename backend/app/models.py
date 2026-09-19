from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

Source = Literal["scraped", "passive", "told", "simulated"]
Domain = Literal["career", "housing", "relationship", "health", "money"]
BranchStatus = Literal["open", "merged", "faded", "stale", "expired"]  # "expired" only in old rows

INCOME_BANDS = ["low", "lower_middle", "middle", "upper_middle", "high"]
EMPLOYMENT = ["employed", "unemployed", "student", "retired"]
RELATIONSHIP = ["single", "married", "divorced", "widowed"]
HOUSING = ["renting", "owning", "with_family"]


class LifeEvent(BaseModel):
    id: str
    person_id: str
    source: Source
    branch_id: str = "main"
    date: str
    domain: str  # a free lowercase life-area tag
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 1.0
    text: str = ""
    origin: str = ""  # which offering it came from (an upload's name, a URL, "your words"); lets a source be forgotten


class StateVector(BaseModel):
    year: int
    age: int
    city: str = "Toronto"
    education: str = "unknown"
    field: str = "all"
    employment: str = "employed"
    income_band: str = "middle"
    relationship_status: str = "single"
    housing: str = "renting"
    activity_proxy: float = 0.5
    children: int = 0
    alive: bool = True


class Option(BaseModel):
    id: str
    title: str
    details: str = ""
    deadline: Optional[str] = None


class Horizon(BaseModel):
    unit: Literal["days", "weeks", "months", "years"] = "years"
    count: int = 40
    tonight: bool = False


class Question(BaseModel):
    id: str
    scenario_id: str
    text: str
    why: str = ""
    choices: list[str] = Field(default_factory=list)
    applies_to: list[str] = Field(default_factory=list)  # option ids; empty = all
    answer: Optional[str] = None


class Scenario(BaseModel):
    id: str
    person_id: str
    situation: str
    created_at: str
    horizon: Horizon = Field(default_factory=Horizon)
    scale: Literal["big", "small"] = "small"  # big = a life decision; small = a day-to-day action or dilemma
    scale_chosen: bool = False  # the person set the scale themselves: never re-inferred afterwards
    questions: list[Question] = Field(default_factory=list)
    assuming_branch_id: Optional[str] = None
    assuming_at: Optional[str] = None      # the date on that branch this decision splits off at
    fork_at: Optional[str] = None          # where to draw its node: on the assumed path at this date (null = at now, on main)
    assumed_facts: list[str] = Field(default_factory=list)  # what had already happened on that path by then
    nearest_deadline: Optional[str] = None
    options: list[Option]
    branch_ids: list[str] = Field(default_factory=list)
    status: Literal["open", "decided"] = "open"
    decided_branch_id: Optional[str] = None


class Commit(BaseModel):
    """A what-if decision the person makes inside a branch. Hypothetical, so undoable."""

    id: str
    branch_id: str
    year: int
    at: str = ""
    message: str
    patch: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class Branch(BaseModel):
    id: str
    person_id: str
    label: str
    forked_at: str
    assumption: dict[str, Any] = Field(default_factory=dict)
    precondition: Optional[str] = None
    status: BranchStatus = "open"
    carried_event_id: Optional[str] = None
    scenario_id: Optional[str] = None
    option_id: Optional[str] = None
    commits: list[Commit] = Field(default_factory=list)
    research: Literal["none", "pending", "running", "done", "failed"] = "none"
    revision: int = 0
    params: dict[str, Any] = Field(default_factory=dict)  # researched facts the simulator was given
    fork: dict[str, Any] = Field(default_factory=dict)    # the present this branch left from, frozen
    horizon: int = 40
    span: Horizon = Field(default_factory=Horizon)        # how far, and in what steps, this branch is lived
    model: Optional[dict[str, Any]] = Field(default_factory=lambda: {"events": []})  # what could happen here; null while forming
    measures: Optional[dict[str, Any]] = None  # health, joy, fulfilment, money: change from now, per step and at the end
    forming: bool = False  # true until the first simulation lands (and again while answers are being folded in)


class AspectOutlook(BaseModel):
    share: float
    words: str
    value: str
    probability: float = 0.0  # cumulative by this step (for background aspects: the share with the value shown)


class BranchYear(BaseModel):
    year: int
    at: str = ""
    label: str = ""
    solidity: float
    state: StateVector
    events: list[LifeEvent]
    outlook: dict[str, AspectOutlook] = Field(default_factory=dict)


class BranchView(BaseModel):
    branch: Branch
    years: list[BranchYear]


class Evidence(BaseModel):
    id: str
    person_id: str = ""
    branch_id: Optional[str] = None
    kind: Literal["researched", "statistic", "personal"]
    claim: str
    value: Optional[str] = None
    unit: Optional[str] = None
    source_title: str
    source_url: Optional[str] = None
    retrieved_at: str
    snippet: Optional[str] = None
    used_for: Optional[str] = None
    question: Optional[str] = None  # what was being looked up; lets later research reuse it
    figure: Optional[str] = None    # the figure exactly as the source writes it
    span_days: Optional[int] = None
    reference_class: Optional[str] = None  # the studied population the figure is really about
    gap: Optional[str] = None              # how that population differs from this person


class Paragraph(BaseModel):
    text: str
    evidence_ids: list[str] = Field(default_factory=list)


class Chapter(BaseModel):
    branch_id: str
    revision: int
    from_year: int
    to_year: int
    from_at: str = ""
    to_at: str = ""
    which: Literal["typical", "rare"] = "typical"
    recap: str = ""  # two sentences on where things stand at the end, handed to the next chapter
    title: str
    status: Literal["writing", "ready"]
    paragraphs: list[Paragraph]


class ResearchStep(BaseModel):
    at: str
    state: Literal["searching", "reading", "found", "skipped", "done"]
    message: str
    url: Optional[str] = None
    session_url: Optional[str] = None


class AgentStep(BaseModel):
    step: int
    tool: str
    args: dict[str, Any]
    reason: str
    hits: int
    planner: Literal["llm", "rules"]


class Person(BaseModel):
    id: str
    display_name: str = ""
    birth_year: Optional[int] = None
    sex: Optional[Literal["M", "F"]] = None
    personality: Optional[dict[str, Any]] = None
    money: Optional[dict[str, Any]] = None  # {income, net_worth, currency}: only what the person chose to say; encrypted at rest


class Decision(BaseModel):
    """One reconciliation ruling: which value won a state slot, over what, and why."""

    slot: str
    chosen: str
    over: list[str]
    reason: str


# --- request bodies (/ingest is multipart; see main.py) ---


class SimulateRequest(BaseModel):
    person_id: str
    label: str
    assumption: dict[str, Any] = Field(default_factory=dict)
    precondition: Optional[str] = None
    horizon_years: Optional[int] = None


class MergeRequest(BaseModel):
    branch_id: str
    confirm: str = ""


class PersonRequest(BaseModel):
    display_name: Optional[str] = None
    birth_year: Optional[int] = None
    sex: Optional[Literal["M", "F"]] = None
    income: Optional[float] = None
    net_worth: Optional[float] = None
    currency: Optional[str] = None


class OptionRequest(BaseModel):
    title: str
    details: str = ""
    deadline: Optional[str] = None


class ScenarioRequest(BaseModel):
    person_id: str
    # Either `text` — one plain line, as the person would write a ticket; the options are found
    # inside it — or `situation` with explicit `options`.
    text: Optional[str] = None
    situation: str = ""
    options: list[OptionRequest] = Field(default_factory=list, max_length=4)
    horizon: Optional[Horizon] = None
    scale: Optional[Literal["big", "small"]] = None
    assuming_branch_id: Optional[str] = None
    assuming_at: Optional[str] = None


class EditRequest(BaseModel):
    situation: Optional[str] = None
    scale: Optional[Literal["big", "small"]] = None
    rename: dict[str, str] = Field(default_factory=dict)              # option id -> new title
    deadline: dict[str, Optional[str]] = Field(default_factory=dict)  # option id -> YYYY-MM-DD, or null to clear
    add: list[OptionRequest] = Field(default_factory=list)


class AnswersRequest(BaseModel):
    answers: dict[str, str]


class CommitRequest(BaseModel):
    message: str = ""
    event_key: Optional[str] = None  # instead of a message: "assume this possibility happens"
    at: Optional[str] = None
    year: Optional[int] = None


class UndoRequest(BaseModel):
    commit_id: Optional[str] = None


class EraseRequest(BaseModel):
    person_id: str
    confirm: str


class ForgetRequest(BaseModel):
    person_id: str
    origin: str


class CarryRequest(BaseModel):
    branch_id: str
    event_id: str
