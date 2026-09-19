"""Our own probability logic: how likely, how hard, how sure, and on what evidence.

It combines three things, and only code does the arithmetic:
  * real-world evidence  the event's base rate: a published figure that research found and
                         `outcome_model.apply_rate` verified ("sourced"), the person's own track
                         record ("personal"), or a verbal bin ("estimated");
  * personal context     what Elastic holds about the person, as Jev read it;
  * Jev's structured scores and yes/no prerequisite checks (see jev.py).

Jev's scores never *are* the probability. They move the base rate on the log-odds scale by a
bounded amount (`MAX_SHIFT`), so even five perfect scores cannot turn a rare outcome into a likely
one; a hard prerequisite that the person's record shows is unmet caps the outcome at `HARD_CAP`.
This module cannot import the LLM (tested), and the same inputs always give the same estimate.

The result is stored on the event as `event["estimate"]`; the sampler in `sim/outcomes.py` centres
each simulated life's draw on `estimate.likelihood` and spreads it by `estimate.spread`.
`event["probability"]` and `event["basis"]` are never changed here, so the audit trail back to the
published figure stays intact and `assess_events` can be re-run at any time (for instance when
research lands and an estimated event becomes sourced).
"""

from __future__ import annotations

import math

from .sim.engine import likelihood_words
from .sim.outcomes import BINS, DEFAULT_BIN

# Hand-set; listed in data/SOURCES.md under "Model assumptions".
MAX_SHIFT = {"sourced": 0.6, "personal": 0.3, "estimated": 0.9}   # log-odds: 0.9 is at most ~x2.5 on the odds
BASIS_CONFIDENCE = {"sourced": 0.70, "personal": 0.60, "estimated": 0.30}
HARD_CAP = 0.03            # an outcome whose hard prerequisite is shown unmet
FLOOR, CEILING = 0.005, 0.995
UNCERTAINTY_SPREAD = 0.12  # extra half-width at zero confidence
UNKNOWN_PREREQ_SPREAD = 0.03
MAX_SPREAD = 0.40

# How much each factor counts for each kind of outcome. personal_fit, experience_fit and
# accessibility push likelihood up when high; difficulty pushes it down. Each row sums to 1.
DEFAULT_WEIGHTS = {"personal_fit": 0.25, "experience_fit": 0.25, "accessibility": 0.25, "difficulty": 0.25}
CATEGORY_WEIGHTS = {
    "career":           {"personal_fit": 0.20, "experience_fit": 0.35, "accessibility": 0.25, "difficulty": 0.20},
    "education":        {"personal_fit": 0.20, "experience_fit": 0.30, "accessibility": 0.20, "difficulty": 0.30},
    "research":         {"personal_fit": 0.20, "experience_fit": 0.40, "accessibility": 0.25, "difficulty": 0.15},
    "entrepreneurship": {"personal_fit": 0.35, "experience_fit": 0.25, "accessibility": 0.20, "difficulty": 0.20},
    "financial":        {"personal_fit": 0.20, "experience_fit": 0.10, "accessibility": 0.40, "difficulty": 0.30},
    "social":           {"personal_fit": 0.50, "experience_fit": 0.10, "accessibility": 0.25, "difficulty": 0.15},
    "location":         {"personal_fit": 0.20, "experience_fit": 0.10, "accessibility": 0.40, "difficulty": 0.30},
    "health":           {"personal_fit": 0.40, "experience_fit": 0.10, "accessibility": 0.20, "difficulty": 0.30},
    "relationship":     {"personal_fit": 0.45, "experience_fit": 0.10, "accessibility": 0.25, "difficulty": 0.20},
}


def _logit(p: float) -> float:
    return math.log(p / (1 - p))


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def _clip(p: float) -> float:
    return min(max(p, FLOOR), CEILING)


def base_rate(event: dict) -> tuple[float, float]:
    """(probability, half-width) the event has before Jev: its published or personal figure with its
    own band, or the middle of its verbal bin with the bin's half-width."""
    if event.get("basis") in ("sourced", "personal") and event.get("probability") is not None:
        return _clip(float(event["probability"])), float(event.get("band") or 0.0)
    lo, hi = BINS.get(event.get("bin") or DEFAULT_BIN, BINS[DEFAULT_BIN])
    return (lo + hi) / 2, (hi - lo) / 2


def _signal(jev: dict, factor: str) -> float:
    """A factor as a number in [-1, 1] where positive always means 'more likely'."""
    score = max(1, min(5, int(jev.get(factor, 3))))
    return (3 - score) / 2 if factor == "difficulty" else (score - 3) / 2


def fit_signal(jev: dict) -> float:
    weights = CATEGORY_WEIGHTS.get(jev.get("category", "other"), DEFAULT_WEIGHTS)
    return sum(w * _signal(jev, f) for f, w in weights.items())


def _evidence_strength(event: dict, jev: dict) -> int:
    """Jev scored evidence before research may have arrived. Once an event is sourced or personal the
    strength is at least what the basis itself gives."""
    score = max(1, min(5, int(jev.get("evidence_strength", 3))))
    if event.get("basis") == "sourced":
        return max(score, 3 if event.get("band") else 4)
    if event.get("basis") == "personal":
        return max(score, 4)
    return score


def difficulty_of(jev: dict) -> float:
    """0 (easy) to 1 (very hard): how demanding the outcome is, blended with how closed the route is."""
    d = max(1, min(5, int(jev.get("difficulty", 3))))
    a = max(1, min(5, int(jev.get("accessibility", 3))))
    return round(0.6 * (d - 1) / 4 + 0.4 * (5 - a) / 4, 3)


def _label(difficulty: float, blocked: bool) -> str:
    return "blocked" if blocked else "easy" if difficulty < 0.34 else "moderate" if difficulty < 0.67 else "hard"


def _evidence_lines(event: dict, jev: dict, p0: float, shift: float, likelihood: float, unmet: list, unknown: list) -> list[dict]:
    basis = event.get("basis", "estimated")
    if basis == "sourced":
        head = f"Published figure sets the starting point at {p0:.0%}."
    elif basis == "personal":
        head = f"Your own track record sets the starting point at {p0:.0%}."
    else:
        head = f"No published figure found; starting from the estimate '{event.get('bin') or DEFAULT_BIN}' ({p0:.0%})."
    lines = [{"kind": basis, "text": head, "evidence_id": event.get("evidence_id")}]
    if abs(shift) >= 0.01:
        lines.append({"kind": "judged", "text": f"Fit and difficulty ({jev.get('category', 'other')}) moved it to {likelihood:.0%}: {jev.get('rationale', '')}".strip(),
                      "evidence_id": None})
    for p in unmet:
        lines.append({"kind": "prerequisite", "text": f"Not met: {p['requirement']} ({p.get('basis', '')}). Capped at {HARD_CAP:.0%}.", "evidence_id": None})
    for p in unknown:
        lines.append({"kind": "prerequisite", "text": f"Unknown: {p['requirement']}.", "evidence_id": None})
    return lines


def estimate(event: dict) -> dict:
    """The estimate for one event. Pure: reads `basis`, `probability`, `band`, `bin` and `jev`."""
    jev = event.get("jev") or {"category": "other"}
    p0, base_spread = base_rate(event)
    basis = event.get("basis", "estimated")
    if basis not in MAX_SHIFT:
        basis = "estimated"

    shift = MAX_SHIFT[basis] * max(-1.0, min(1.0, fit_signal(jev)))
    likelihood = _clip(_sigmoid(_logit(p0) + shift))

    prereqs = jev.get("prerequisites") or []
    unmet = [p for p in prereqs if p.get("met") == "no"]
    unknown = [p for p in prereqs if p.get("met") == "unknown"]
    if unmet:
        likelihood = min(likelihood, HARD_CAP)

    confidence = BASIS_CONFIDENCE[basis] + 0.15 * (_evidence_strength(event, jev) - 3) / 2
    confidence -= 0.08 * min(len(unknown), 2) + (0.10 if basis == "sourced" and event.get("band") else 0.0)
    confidence = round(min(max(confidence, 0.05), 0.95), 3)

    spread = base_spread + UNCERTAINTY_SPREAD * (1 - confidence) + UNKNOWN_PREREQ_SPREAD * len(unknown)
    spread = min(spread, MAX_SPREAD)
    if unmet:
        spread = min(spread, 0.02)
    difficulty = 1.0 if unmet else difficulty_of(jev)

    return {
        "likelihood": round(likelihood, 4), "low": round(_clip(likelihood - spread), 4),
        "high": round(_clip(likelihood + spread), 4), "spread": round(spread, 4),
        "difficulty": difficulty, "difficulty_label": _label(difficulty, bool(unmet)),
        "confidence": confidence, "category": jev.get("category", "other"),
        "base": {"probability": round(p0, 4), "basis": basis}, "shift": round(shift, 4),
        "blocked": bool(unmet), "judged_by": jev.get("judged_by", "none"),
        "evidence": _evidence_lines(event, jev, p0, shift, likelihood, unmet, unknown),
    }


def assess_events(events: list[dict]) -> None:
    """Attach `estimate` to every event and keep its plain-words label in step with it. Idempotent."""
    for e in events:
        e["estimate"] = estimate(e)
        e["words"] = likelihood_words(e["estimate"]["likelihood"])
