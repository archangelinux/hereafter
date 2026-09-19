"""Building an option's outcome model, and keeping the LLM out of its numbers.

The LLM proposes *what could happen* and, per event, a verbal bin and a research question. It
never supplies a probability. A number enters the model in exactly one way: a published figure
that research found, that code has verified appears literally in the quoted snippet, and that
code has converted to the event's window. Everything else stays an "estimated" bin.
"""

from __future__ import annotations

import re
from typing import Optional

from . import llm
from .models import Horizon, Option
from .sim.outcomes import BINS, MAX_STEPS, STEP_DAYS

KEY_RE = re.compile(r"[^a-z0-9_]+")
SHORT_WORDS = re.compile(r"\b(tonight|today|tomorrow|this weekend|this week)\b", re.I)
WEEK_WORDS = re.compile(r"\b(next week|few weeks|a month|for a month|dry january|30 days|thirty days)\b", re.I)
MONTH_WORDS = re.compile(r"\b(this term|semester|this year|few months|months|marathon|training)\b", re.I)


# --- horizon ---


def rules_horizon(situation: str, options: list[Option]) -> Horizon:
    text = situation + " " + " ".join(f"{o.title} {o.details}" for o in options)
    if SHORT_WORDS.search(text):
        return Horizon(unit="days", count=7, tonight=bool(re.search(r"\btonight\b", text, re.I)))
    if WEEK_WORDS.search(text):
        return Horizon(unit="weeks", count=8)
    if MONTH_WORDS.search(text):
        return Horizon(unit="months", count=12)
    return Horizon(unit="years", count=40)


def clamp(h: Horizon) -> Horizon:
    return Horizon(unit=h.unit, count=max(1, min(h.count, MAX_STEPS[h.unit])), tonight=h.tonight and h.unit == "days")


# --- proposal -> model ---


def _key(raw: str) -> str:
    return KEY_RE.sub("_", raw.strip().lower()).strip("_")[:60] or "event"


def from_proposal(proposed: llm.ProposedOption, n_steps: int) -> list[dict]:
    events, seen = [], set()
    for e in proposed.events[:14]:
        key = _key(e.key)
        if key in seen:
            continue
        seen.add(key)
        lo = max(0, min(e.first_step, n_steps - 1))
        hi = max(lo, min(e.last_step, n_steps - 1))
        events.append({
            "key": key, "label": e.label.strip(), "domain": _key(e.domain) or "life", "kind": e.kind,
            "window": [lo, hi], "bin": e.bin, "probability": None, "basis": "estimated", "evidence_id": None,
            "words": e.bin, "depends_on": [{"key": _key(d.key), "relation": d.relation} for d in e.depends_on],
            "reference_class": e.reference_class, "search_query": e.search_query,
            "follow_through": e.follow_through, "band": 0.0,
        })
    keys = {e["key"] for e in events}
    for e in events:
        e["depends_on"] = [d for d in e["depends_on"] if d["key"] in keys and d["key"] != e["key"]]
    return events


def public_model(events: list[dict]) -> dict:
    """What is stored on the branch: the events, and an honest count of where their likelihoods come from."""
    return {"events": events, "mix": {b: sum(e["basis"] == b for e in events) for b in ("sourced", "personal", "estimated")}}


# --- the only door a number may come through ---

PERCENT = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:%|percent|per cent)", re.I)
ONE_IN = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:in|out of|of every)\s*(\d[\d,]*)", re.I)
PER = re.compile(r"(\d+(?:[.,]\d+)?)\s*per\s*(\d[\d,]*)", re.I)


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _num(raw: str) -> float:
    return float(raw.replace(",", ""))


def figure_in_snippet(figure: str, snippet: str) -> bool:
    """The figure, exactly as written, must appear in the snippet that is quoted as its source."""
    return bool(figure.strip()) and _squash(figure) in _squash(snippet)


RANGE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:-|–|—|to|and)\s*(\d+(?:[.,]\d+)?)\s*(?:%|percent|per cent)", re.I)


def parse_share(figure: str) -> Optional[float]:
    """A proportion in (0,1) from "23%", "61 to 64%" (the midpoint), "1 in 4", "41 per 1,000".
    Anything else is not accepted."""
    m = RANGE.search(figure)
    if m:
        share = (_num(m.group(1)) + _num(m.group(2))) / 200
    elif (m := PERCENT.search(figure)):
        share = _num(m.group(1)) / 100
    else:
        m = ONE_IN.search(figure) or PER.search(figure)
        if not m or _num(m.group(2)) == 0:
            return None
        share = _num(m.group(1)) / _num(m.group(2))
    return share if 0 < share < 1 else None


def window_probability(share: float, span_days: Optional[int], event: dict, unit: str) -> tuple[float, str]:
    """Convert a published share to this event. The published figure says: within `span_days` of
    starting, this share of the studied group had it happen. Assuming a constant daily hazard,
    the chance it has happened by the END of this event's window is 1-(1-share)^(exposure/span),
    where exposure runs from the start of the branch to the end of the window (one step, for a
    recurring event). Returns the probability and the arithmetic, in words."""
    lo, hi = event["window"]
    exposure = STEP_DAYS[unit] * (1 if event["kind"] == "recurring" else hi + 1)
    if not span_days:
        return share, f"published share {share:.3f} used as the chance within this event's window (the source gives no period)"
    p = 1 - (1 - share) ** (exposure / span_days)
    return p, (f"published share {share:.3f} within {span_days} days; this event's window closes {exposure:.0f} days in "
               f"-> 1-(1-{share:.3f})^({exposure:.0f}/{span_days}) = {p:.3f}")


def apply_rate(event: dict, rate: llm.PublishedRate, evidence_id: str, unit: str) -> Optional[str]:
    """Make an event 'sourced' if, and only if, the figure survives the checks. Returns the
    arithmetic (for the evidence's `used_for`) or None when rejected."""
    if not figure_in_snippet(rate.figure_as_written, rate.snippet):
        return None
    share = parse_share(rate.figure_as_written)
    if share is None:
        return None
    p, arithmetic = window_probability(share, rate.span_days, event, unit)
    p = min(max(p, 0.005), 0.995)
    from .sim.engine import likelihood_words

    from .sim.outcomes import GAP_BAND

    event.update({"basis": "sourced", "probability": round(p, 4), "evidence_id": evidence_id,
                  "words": likelihood_words(p), "band": GAP_BAND if rate.gap_is_large else 0.0})
    return f"likelihood of “{event['label']}”: {arithmetic}"


# --- commits on the model ---


def rules_patch(message: str, events: list[dict]) -> dict:
    """LLM-off fallback: if the decision plainly names one possible event, force it."""
    want = set(re.findall(r"[a-z]{3,}", message.lower()))
    best, overlap = None, 1
    for e in events:
        n = len(want & set(re.findall(r"[a-z]{3,}", e["label"].lower())))
        if n > overlap:
            best, overlap = e["key"], n
    return {"force": [best] if best else [], "prevent": [], "likelier": [], "less_likely": []}


def model_patch(message: str, events: list[dict]) -> dict:
    if not events:
        return {"force": [], "prevent": [], "likelier": [], "less_likely": []}
    parsed = llm.extract_model_patch(message, events)
    if parsed is None:
        return rules_patch(message, events)
    keys = {e["key"] for e in events}
    return {k: [x for x in getattr(parsed, k) if x in keys] for k in ("force", "prevent", "likelier", "less_likely")}


assert set(BINS) == {"rare", "sometimes", "as often as not", "usually"}
