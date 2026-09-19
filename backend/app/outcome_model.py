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
from .sim.outcomes import BIG_DEFAULT_YEARS, BIG_MAX_YEARS, BINS, MAX_STEPS, step_offsets, window_from_days

KEY_RE = re.compile(r"[^a-z0-9_]+")
SHORT_WORDS = re.compile(r"\b(tonight|today|tomorrow|this weekend|this week)\b", re.I)
WEEK_WORDS = re.compile(r"\b(next week|few weeks|a month|for a month|dry january|30 days|thirty days)\b", re.I)
MONTH_WORDS = re.compile(r"\b(this term|semester|this year|few months|months|marathon|training)\b", re.I)


# --- horizon ---


LIFE_WORDS = re.compile(r"\b(offer|job|career|move|moving|relocat\w*|uni|university|college|degree|master'?s?|mmath|phd|school|program|"
                        r"marry|married|wedding|propose|baby|kids?|children|house|mortgage|retire\w*|emigrat\w*|immigrat\w*|quit|resign|"
                        r"start a (company|business))\b", re.I)
DEFAULT_HORIZON = Horizon(unit="weeks", count=8)  # nothing to go on: a modest stretch, not forty years


def inferred_horizon(situation: str, options) -> Optional[Horizon]:
    """The rules' reading of how far a decision plays out, or None when the words give no clue."""
    text = situation + " " + " ".join(f"{o.title} {o.details}" for o in options)
    if not (SHORT_WORDS.search(text) or WEEK_WORDS.search(text) or MONTH_WORDS.search(text) or LIFE_WORDS.search(text)):
        return None
    return rules_horizon(situation, options)


def scale_of(horizon: Horizon) -> str:
    """Firm, and applied after the LLM: under six months is a small decision, six months or more a big one."""
    six_months = {"days": 10**9, "weeks": 26, "months": 6, "years": 1}[horizon.unit]
    return "big" if horizon.count >= six_months else "small"


def decide_scale(chosen: Optional[str], horizon: Optional[Horizon], opinion: Optional[str]) -> str:
    """The person's explicit choice always wins; then the horizon; the LLM's opinion only when no
    horizon could be inferred at all; otherwise small."""
    if chosen:
        return chosen
    if horizon is not None:
        return scale_of(horizon)
    return opinion or "small"


def rules_horizon(situation: str, options: list[Option]) -> Horizon:
    text = situation + " " + " ".join(f"{o.title} {o.details}" for o in options)
    if SHORT_WORDS.search(text):
        return Horizon(unit="days", count=7, tonight=bool(re.search(r"\btonight\b", text, re.I)))
    if WEEK_WORDS.search(text):
        return Horizon(unit="weeks", count=8)
    if MONTH_WORDS.search(text):
        return Horizon(unit="months", count=12)
    if LIFE_WORDS.search(text):
        return Horizon(unit="years", count=BIG_DEFAULT_YEARS)
    return DEFAULT_HORIZON.model_copy()


def clamp(h: Horizon, person_set: bool = False) -> Horizon:
    """A big decision is modelled where it plays out: never more than five years unless the person says so."""
    ceiling = MAX_STEPS[h.unit] if person_set or h.unit != "years" else BIG_MAX_YEARS
    return Horizon(unit=h.unit, count=max(1, min(h.count, ceiling)), tonight=h.tonight and h.unit == "days")


# --- proposal -> model ---


def _key(raw: str) -> str:
    return KEY_RE.sub("_", raw.strip().lower()).strip("_")[:60] or "event"


CHOICE_VERBS = {"accept", "answer", "apply", "ask", "buy", "call", "cut", "decline", "do", "finish", "go", "join", "just", "keep",
                "leave", "lend", "move", "pass", "play", "quit", "say", "sell", "skip", "start", "stay", "study", "take", "tell",
                "text", "wait"}


def choice_label(title: str) -> str:
    """LLM-off wording of step zero: "Take the offer" -> "You take the offer"; "McMaster" -> "You choose McMaster"."""
    title = title.strip().rstrip(".?!")
    first = title.split(" ", 1)[0].lower() if title else ""
    return f"You {title[0].lower()}{title[1:]}" if first in CHOICE_VERBS else f"You choose {title}"


def head_event(label: str) -> dict:
    """Step zero IS the choice: the one step a merge commits. Always happens, first, in every life."""
    return {"key": "choice", "label": label.strip().rstrip("."), "domain": "growth", "kind": "one_time", "phase": "right_away",
            "window": [0, 0], "days": [0, 0], "bin": None, "base_probability": 1.0, "basis": "choice", "evidence_id": None,
            "words": "almost always", "band": 0.0, "depends_on": [], "after": [], "requires": [], "head": True,
            "reference_class": None, "search_query": None, "follow_through": False, "hazard": None, "traits": [],
            "effects": {"health": 0, "joy": 0, "fulfilment": 0, "money": 0}, "money_amount": None, "effects_basis": "judgement"}


def ensure_head(events: list[dict], label: str) -> list[dict]:
    if not any(e.get("head") for e in events):
        events.insert(0, head_event(label))
    return events


def repair(events: list[dict]) -> list[dict]:
    """Makes the story causally valid, in code: unknown keys are dropped from `after`/`requires`;
    whatever is required is also 'after'; cycles are cut; and no window may open before the window
    of something it must come after — such a window is moved later rather than the event lost."""
    by_key = {e["key"]: e for e in events}
    for e in events:
        e["requires"] = [k for k in dict.fromkeys(e.get("requires") or []) if k in by_key and k != e["key"] and not by_key[k].get("head")]
        e["after"] = [k for k in dict.fromkeys([*(e.get("after") or []), *e["requires"]])
                      if k in by_key and k != e["key"] and not by_key[k].get("head")]

    def reaches(start: str, goal: str, seen: set) -> bool:
        if start == goal:
            return True
        seen.add(start)
        return any(reaches(k, goal, seen) for k in by_key[start]["after"] if k not in seen)

    for e in events:  # cut any link that would close a loop
        for k in list(e["after"]):
            if reaches(k, e["key"], set()):
                e["after"].remove(k)
                e["requires"] = [r for r in e["requires"] if r != k]
    for _ in range(len(events)):  # push windows later until every one opens no earlier than what it follows
        moved = False
        for e in events:
            for k in e["after"]:
                opens = by_key[k]["window"][0]
                if e["window"][0] < opens:
                    e["window"] = [opens, max(opens, e["window"][1])]
                    moved = True
                # what is required may happen on the last day of its window: leave room to follow it
                if k in e["requires"] and e["window"][1] < by_key[k]["window"][1]:
                    e["window"] = [e["window"][0], by_key[k]["window"][1]]
                    moved = True
        if not moved:
            break
    return events


def _effects(given) -> dict:
    """Four integers in -2..2. A judgement about what a moment means; never about whether it happens."""
    raw = given.model_dump() if hasattr(given, "model_dump") else dict(given or {})
    return {m: max(-2, min(2, int(raw.get(m, 0) or 0))) for m in ("health", "joy", "fulfilment", "money")}


def stated(value: float, said: str) -> bool:
    """A money figure counts as the person's own only if the number is literally in their words:
    165000, 165,000, 165k or 165 thousand. The LLM may copy an amount; it may not supply one."""
    text = re.sub(r"(?<=\d)[,\s](?=\d{3})", "", said.lower())
    whole = int(round(abs(value)))
    if whole and re.search(rf"(?<!\d){whole}(?!\d)", text):
        return True
    return whole >= 1000 and whole % 1000 == 0 and bool(re.search(rf"(?<!\d){whole // 1000}\s?(k\b|thousand|grand)", text))


def from_proposal(proposed: llm.ProposedOption, offsets: list[int], title: str = "", said: str = "") -> list[dict]:
    """The proposal's events, with day windows turned into steps, repaired, and step zero in front."""
    events, seen = [], {"choice"}
    for e in proposed.events[:14]:
        key = _key(e.key)
        if key in seen:
            continue
        seen.add(key)
        window = window_from_days(offsets, e.from_day, e.to_day)
        events.append({
            "key": key, "label": e.label.strip(), "domain": _key(e.domain) or "life", "kind": e.kind, "phase": e.phase,
            "window": window, "days": [max(0, e.from_day), max(e.from_day, e.to_day)],
            "bin": e.bin, "base_probability": None, "basis": "estimated", "evidence_id": None,
            "words": e.bin, "depends_on": [{"key": _key(d.key), "relation": d.relation} for d in e.depends_on],
            "after": [_key(k) for k in e.after], "requires": [_key(k) for k in e.requires],
            "reference_class": e.reference_class, "search_query": e.search_query,
            "follow_through": e.follow_through, "band": 0.0, "hazard": e.hazard,
            "traits": [{"trait": t.trait, "direction": 1 if t.effect == "raises" else -1} for t in e.traits[:2]],
            "effects": _effects(e.effects), "money_kind": e.money_kind,
            "money_amount": ({**e.money_amount.model_dump(), "evidence_id": None}
                             if e.money_amount and stated(e.money_amount.value, said) else None),
            "effects_basis": "sourced" if e.money_amount and stated(e.money_amount.value, said) else "judgement",
        })
    keys = {e["key"] for e in events}
    for e in events:
        e["depends_on"] = [d for d in e["depends_on"] if d["key"] in keys and d["key"] != e["key"]]
    repair(events)
    events = ensure_head(events, (proposed.choice_label or "").strip() or choice_label(title))
    events[0]["effects"] = _effects(proposed.choice_effects)
    return events


def normalize(events: list[dict]) -> list[dict]:
    """Models stored before v2.5 kept the base figure in `probability`, which now means the simulated share."""
    for e in events:
        if "base_probability" not in e:
            e["base_probability"] = e.get("probability") if e.get("basis") in ("sourced", "personal") else None
        e.setdefault("traits", [])
        e.setdefault("hazard", None)
        e.setdefault("after", [])
        e.setdefault("requires", [])
        e["effects"] = _effects(e.get("effects"))
        e.setdefault("money_amount", None)
        e.setdefault("effects_basis", "sourced" if e.get("money_amount") else "judgement")
        # before "requires" had its own list it was a kind of dependency
        e["requires"] += [d["key"] for d in e.get("depends_on", []) if d.get("relation") == "requires" and d["key"] not in e["requires"]]
        e["depends_on"] = [d for d in e.get("depends_on", []) if d.get("relation") != "requires"]
    return repair(events)


def resolve_terms(events: list[dict], published: dict[str, dict[str, float]]) -> None:
    """Which personality terms apply to each event, at most two. A published, significant effect for
    a matching life-course hazard is used as published; otherwise the named direction gets the one
    fixed assumed size. The LLM never supplies a size."""
    from .sim.outcomes import ASSUMED_BETA

    for e in events:
        found = published.get(e.get("hazard") or "", {})
        if found:
            top = sorted(found.items(), key=lambda kv: abs(kv[1]), reverse=True)[:2]
            e["terms"] = [{"trait": t, "direction": 1 if b > 0 else -1, "beta": round(abs(b), 4), "basis": "published"} for t, b in top]
        else:
            e["terms"] = [{"trait": t["trait"], "direction": 1 if t["direction"] > 0 else -1, "beta": ASSUMED_BETA, "basis": "assumed"}
                          for t in (e.get("traits") or [])[:2] if t.get("trait") in ("O", "C", "E", "A", "N")]


LAYOUT = "graded-1"  # weekly, then monthly, then quarterly steps; step zero is the choice


def public_model(events: list[dict]) -> dict:
    """What is stored on the branch: the events, and an honest count of where their likelihoods come from."""
    return {"events": events, "layout": LAYOUT,
            "mix": {b: sum(e["basis"] == b for e in events) for b in ("sourced", "personal", "estimated")}}


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


def _offsets(span) -> list[int]:
    from datetime import date

    if isinstance(span, str):  # a bare unit: evenly spaced steps
        span = Horizon(unit=span, count=MAX_STEPS[span] if span != "years" else BIG_MAX_YEARS)
    return step_offsets(span.unit, span.count, date(2026, 1, 1))


def window_probability(share: float, span_days: Optional[int], event: dict, span) -> tuple[float, str]:
    """Convert a published share to this event. The published figure says: within `span_days` of
    starting, this share of the studied group had it happen. Assuming a constant daily hazard,
    the chance it has happened by the END of this event's window is 1-(1-share)^(exposure/span),
    where exposure runs from the decision to the end of the window in days (one step, for a
    recurring event). Returns the probability and the arithmetic, in words."""
    lo, hi = event["window"]
    offsets = _offsets(span)
    hi, lo = min(hi, len(offsets) - 2), min(lo, len(offsets) - 2)
    exposure = (offsets[lo + 1] - offsets[lo]) if event["kind"] == "recurring" else offsets[hi + 1]
    if not span_days:
        return share, f"published share {share:.3f} used as the chance within this event's window (the source gives no period)"
    p = 1 - (1 - share) ** (exposure / span_days)
    return p, (f"published share {share:.3f} within {span_days} days; this event's window closes {exposure:.0f} days in "
               f"-> 1-(1-{share:.3f})^({exposure:.0f}/{span_days}) = {p:.3f}")


def apply_rate(event: dict, rate: llm.PublishedRate, evidence_id: str, span) -> Optional[str]:
    """Make an event 'sourced' if, and only if, the figure survives the checks. Returns the
    arithmetic (for the evidence's `used_for`) or None when rejected."""
    if not figure_in_snippet(rate.figure_as_written, rate.snippet):
        return None
    share = parse_share(rate.figure_as_written)
    if share is None:
        return None
    p, arithmetic = window_probability(share, rate.span_days, event, span)
    p = min(max(p, 0.005), 0.995)
    from .sim.engine import likelihood_words

    from .sim.outcomes import GAP_BAND

    event.update({"basis": "sourced", "base_probability": round(p, 4), "evidence_id": evidence_id,
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


assert set(BINS) == {"rare", "sometimes", "as often as not", "usually", "almost certainly"}
