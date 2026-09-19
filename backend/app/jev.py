"""Jev: classify and score the events the LLM proposed. It judges; it never says how likely.

For each possible event on an option, Jev returns
  - a category (career, education, research, entrepreneurship, financial, social, location, ...),
    which routes the event to that category's weighting in `probability.py`;
  - five 1-5 scores: personal fit, experience fit, difficulty, accessibility, evidence strength;
  - hard prerequisites, each answered yes / no / unknown from the person's own record.

The record comes from Elastic (hybrid search over the person's log), so Jev sees only what bears
on this option. With the LLM off, `rules_judgement` labels the event from its domain tag and
scores everything neutral, so the pipeline still runs and simply moves nothing.

Jev's output is stored on the event as `event["jev"]`. It is an input to the probability logic,
not a probability.
"""

from __future__ import annotations

import logging
from typing import Optional

from . import llm
from .models import Option, Person, Scenario
from .store import get_store

log = logging.getLogger("hereafter.jev")

CATEGORIES = ("career", "education", "research", "entrepreneurship", "financial", "social", "location",
              "health", "relationship", "other")
FACTORS = ("personal_fit", "experience_fit", "difficulty", "accessibility", "evidence_strength")
NEUTRAL = 3
RECORD_HITS = 8

# Free-form domain tags on proposed events -> a Jev category. Used only by the LLM-off fallback and
# when the model returns a category we cannot use.
DOMAIN_CATEGORY = {
    "work": "career", "career": "career", "job": "career", "learning": "education", "school": "education",
    "education": "education", "research": "research", "money": "financial", "financial": "financial",
    "home": "location", "housing": "location", "location": "location", "move": "location",
    "love": "relationship", "relationship": "relationship", "family": "relationship", "friends": "social",
    "social": "social", "play": "social", "health": "health", "body": "health", "mind": "health",
    "food": "health", "startup": "entrepreneurship", "business": "entrepreneurship",
}


def category_for(domain: str) -> str:
    return DOMAIN_CATEGORY.get((domain or "").lower(), "other")


def _score(value) -> int:
    try:
        return max(1, min(5, int(value)))
    except (TypeError, ValueError):
        return NEUTRAL


def rules_judgement(event: dict) -> dict:
    """What Jev says with no model: the category from the domain tag, every score neutral, no prerequisites."""
    return {"category": category_for(event.get("domain", "")), **{f: NEUTRAL for f in FACTORS},
            "prerequisites": [], "rationale": "No model was available to judge this; scored neutral.", "judged_by": "rules"}


def _from_llm(item: llm.JudgedEvent) -> dict:
    return {
        "category": item.category if item.category in CATEGORIES else "other",
        **{f: _score(getattr(item, f)) for f in FACTORS},
        "prerequisites": [{"requirement": p.requirement.strip(), "met": p.met, "basis": p.basis.strip()}
                          for p in item.prerequisites[:4]],
        "rationale": item.rationale.strip(), "judged_by": "llm",
    }


def record_for(person: Person, scenario: Scenario, option: Option) -> str:
    """The person's own log, filtered to what bears on this option (Elastic hybrid search)."""
    probe = f"{scenario.situation} {option.title} {option.details}"[:600]
    found = [e for e in get_store().hybrid_search(person.id, probe, size=RECORD_HITS)
             if e.event_type not in ("breadcrumb", "social_connectedness")]
    return "\n".join(f"- {e.date[:10]}: {e.text}" for e in sorted(found, key=lambda e: e.date))


def judge(events: list[dict], about: str = "", option: str = "", record: str = "") -> int:
    """Attach `event["jev"]` to every event that does not have one. Returns how many the model judged
    (0 when it is off or failed; those events get the rules judgement)."""
    todo = [e for e in events if not e.get("jev") and not e.get("head")]
    if not todo:
        return 0
    parsed = llm.judge_events(about, record, option, todo)
    by_key = {j.key: j for j in (parsed.events if parsed else [])}
    judged = 0
    for e in todo:
        item: Optional[llm.JudgedEvent] = by_key.get(e["key"])
        e["jev"] = _from_llm(item) if item else rules_judgement(e)
        judged += bool(item)
    return judged


def judge_option(person: Person, scenario: Scenario, option: Option, events: list[dict], about: str = "") -> int:
    """Jev for one option's events, given what the person's log says about it. Never raises."""
    if not events:
        return 0
    try:
        return judge(events, about, f"{option.title}. {option.details}".strip(), record_for(person, scenario, option))
    except Exception:
        log.exception("Jev failed; these events are scored neutral")
        for e in events:
            e.setdefault("jev", rules_judgement(e))
        return 0
