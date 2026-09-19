"""Builds the present-day StateVector from main, by way of a small retrieval agent.

The agent decides *which* store queries to run (LLM planner when enabled, a rules planner
otherwise) and every choice is logged. What the retrieved events *mean* is never up to the
agent: `reduce_events` is plain code.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from . import llm
from .models import AgentStep, Decision, LifeEvent, Person, StateVector
from .store import EventStore

SLOTS = ["city", "education", "field", "employment", "income_band", "relationship_status", "housing"]
SLOT_DOMAIN = {
    "city": "housing", "housing": "housing", "education": "career", "field": "career",
    "employment": "career", "income_band": "money", "relationship_status": "relationship",
}
SLOT_SEARCH = {
    "city": "moved to city lives in based in",
    "education": "degree university graduated studied",
    "field": "studied major field works in",
    "employment": "job started working employed student",
    "income_band": "salary income raise",
    "relationship_status": "married partner wedding divorce",
    "housing": "bought home rents apartment lives with family",
}
EVENT_IMPLIES = {
    "marriage": {"relationship_status": "married"},
    "divorce": {"relationship_status": "divorced"},
    "home_purchase": {"housing": "owning"},
    "job_start": {"employment": "employed"},
    "job_change": {"employment": "employed"},
    "retirement": {"employment": "retired"},
}
DEFAULT_AGE = 25
MAX_STEPS = 10

_cache: dict[tuple[str, int], tuple[StateVector, list[AgentStep], list[Decision]]] = {}


RECENCY_HALF_LIFE_YEARS = 2.0


def _weight(e: LifeEvent, today: date) -> float:
    """Recency + confidence: confidence, halved for every two years of age."""
    try:
        age_years = max(0.0, (today - date.fromisoformat(e.date[:10])).days / 365.25)
    except ValueError:
        age_years = 10.0
    return e.confidence * 0.5 ** (age_years / RECENCY_HALF_LIFE_YEARS)


def reduce_events(events: list[LifeEvent]) -> tuple[dict[str, Any], list[Decision]]:
    """RECONCILE: every retrieved event votes for the slots it speaks to; where sources
    disagree (resume says Toronto, posts say Waterloo) the heaviest vote wins and the ruling
    is logged. Goal events are wishes, not facts, and never vote."""
    today = date.today()
    votes: dict[str, list[tuple[float, str, LifeEvent]]] = {}
    children = 0
    for e in events:
        if e.event_type == "goal":
            continue
        claims = dict(EVENT_IMPLIES.get(e.event_type, {}))
        if e.event_type == "city_move" and e.payload.get("to"):
            claims["city"] = e.payload["to"]
        claims.update({slot: e.payload[slot] for slot in SLOTS if e.payload.get(slot)})
        for slot, value in claims.items():
            votes.setdefault(slot, []).append((_weight(e, today), str(value), e))
        children += e.event_type == "birth"

    filled: dict[str, Any] = {}
    decisions: list[Decision] = []
    for slot, cast in votes.items():
        cast.sort(key=lambda v: v[0], reverse=True)
        _, winner, source_event = cast[0]
        filled[slot] = winner
        losers = list(dict.fromkeys(v for _, v, _ in cast if v.lower() != winner.lower()))
        if losers:
            decisions.append(Decision(
                slot=slot, chosen=winner, over=losers,
                reason=f"{source_event.source} event from {source_event.date[:7]} carries the most weight "
                       f"(recency and confidence) among {len(cast)} that speak to {slot.replace('_', ' ')}",
            ))
    if children:
        filled["children"] = children
    signals = [(e.date, e.payload["activity_proxy"]) for e in events if "activity_proxy" in e.payload]
    if signals:
        filled["activity_proxy"] = max(signals)[1]
    return filled, decisions


def _rules_plan(empty: list[str], ran: list[dict]) -> list[dict]:
    """Cheapest useful query first: one domain listing per domain with gaps, then a targeted
    hybrid search for whatever a listing already failed to fill."""
    listed = {q["args"].get("domain") for q in ran if q["tool"] == "latest_in_domain"}
    searched = {q["args"].get("text") for q in ran if q["tool"] == "hybrid_search"}
    plan = []
    for slot in empty:
        domain = SLOT_DOMAIN[slot]
        if domain not in listed:
            listed.add(domain)
            plan.append({"tool": "latest_in_domain", "args": {"domain": domain},
                         "reason": f"{slot} is empty; start with the newest {domain} events"})
        elif SLOT_SEARCH[slot] not in searched:
            plan.append({"tool": "hybrid_search", "args": {"text": SLOT_SEARCH[slot]},
                         "reason": f"the {domain} listing did not settle {slot}; search event text"})
    return plan


def _llm_plan(empty: list[str], filled: dict, ran: list[dict]) -> Optional[list[dict]]:
    planned = llm.plan_queries(empty, filled, ran)
    if planned is None:
        return None
    out = []
    for q in planned:
        args = {"text": q.text} if q.tool == "hybrid_search" else {"domain": q.domain}
        if None not in args.values():
            out.append({"tool": q.tool, "args": args, "reason": q.reason})
    return out


def build_state(store: EventStore, person: Person, n_main: int) -> tuple[StateVector, list[AgentStep], list[Decision]]:
    key = (person.id, n_main)
    if key in _cache:
        return _cache[key]

    seen: dict[str, LifeEvent] = {}
    steps: list[AgentStep] = []
    ran: list[dict] = []

    def run(q: dict, planner: str) -> None:
        if q["tool"] == "domain_histogram":
            hist = store.domain_histogram(person.id, q["args"]["domain"])
            hits = sum(hist["types"].values())
        else:
            found = getattr(store, q["tool"])(person.id, **q["args"])
            hits = len(found)
            seen.update({e.id: e for e in found})
        ran.append(q)
        steps.append(AgentStep(step=len(steps) + 1, tool=q["tool"], args=q["args"],
                               reason=q["reason"], hits=hits, planner=planner))

    for _round in range(3):  # plan, run, look at what is still empty, plan again
        filled, _ = reduce_events(list(seen.values()))
        empty = [s for s in SLOTS if s not in filled]
        if not empty or len(steps) >= MAX_STEPS:
            break
        plan = _llm_plan(empty, filled, ran)
        planner = "llm"
        if plan is None:
            plan, planner = _rules_plan(empty, ran), "rules"
        if not plan:
            break
        for q in plan[: MAX_STEPS - len(steps)]:
            run(q, planner)

    # Activity density always comes from the aggregation: events per recent year, all domains.
    this_year = date.today().year
    recent = 0
    for domain in ("career", "relationship", "housing"):
        hist = store.domain_histogram(person.id, domain)
        recent += sum(sum(v.values()) for y, v in hist["per_year"].items() if int(y) >= this_year - 3)
        steps.append(AgentStep(step=len(steps) + 1, tool="domain_histogram", args={"domain": domain},
                               reason="activity density: recent per-year event counts",
                               hits=sum(hist["types"].values()), planner="rules"))
    activity = min(1.0, recent / 12)

    filled, decisions = reduce_events(list(seen.values()))
    if "activity_proxy" in filled:  # a measured social signal and event density, averaged
        activity = (activity + float(filled.pop("activity_proxy"))) / 2
    age = this_year - person.birth_year if person.birth_year else DEFAULT_AGE
    state = StateVector(year=this_year, age=age, activity_proxy=round(activity, 3),
                        **{k: v for k, v in filled.items() if k in StateVector.model_fields})
    _cache[key] = (state, steps, decisions)
    return state, steps, decisions
