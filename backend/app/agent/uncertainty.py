"""Which question is worth asking? Answered with arithmetic, not with a language model.

The model of the decision is small:

  * each route has possible outcomes; an outcome is good (+1) or bad (-1) along one dimension
    (money, growth, stability, wellbeing, freedom);
  * an outcome's likelihood comes from `probability.py` (base rate, moved a bounded amount by how
    well it fits the person), and, for the good outcomes, falls to almost nothing if a hard requirement (a gate) is unmet;
  * how much each dimension matters is unknown, held as a probability over "what this person
    cares about most" (the priorities).

A route's score is the average, over its outcomes, of  valence x impact x likelihood x weight(dimension),
where impact says how much the outcome would change the person's life (1 minor, 2 notable, 3 life-changing).
Without impact a route full of certain, mundane outcomes would always beat one with an uncertain
life-changing upside.

An unknown is a gate we are unsure of (P(met) far from 0 and 1) or the priorities. For each we
compute the *expected value of perfect information*:

    EVPI = sum over answers [ P(answer) x best route score if that were the answer ]
           - best route score now

That is exactly "how much better would my choice be, on average, if I knew this". It is zero when
no answer could change which route is best, so a question about something that cannot matter is
never asked. `flip` is the probability that the answer changes which route leads.

Everything here reads the session and returns numbers. Nothing is written and nothing is random.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import prod
from typing import Optional

from .. import probability
from .model import DIMENSIONS, DIMENSION_MEANING, Event, Gate, Route, Session

# Hand-set. Listed in docs/AGENT.md.
BASE_WEIGHT = 0.10        # every outcome counts a little whatever the person's priority
PRIORITY_BOOST = 0.40     # extra weight on outcomes in the dimension the person cares about most
MIN_SPREAD = 0.01         # floor on the gap between routes when judging how big an EVPI is
STOP_REL_EVPI = 0.12      # stop asking when the best question is worth < 12% of the route spread ...
STOP_FLIP = 0.25          # ... and could change the leader in fewer than 1 in 4 of the possible answers
SETTLED = 0.03            # a gate this close to 0 or 1 is treated as known


def met_likelihood(e: Event) -> float:
    """The event's likelihood if every requirement is met: the repo's probability logic, unchanged."""
    return probability.estimate({
        "basis": "estimated", "bin": e.bin,
        "jev": {"category": e.category, "personal_fit": e.personal_fit, "experience_fit": e.experience_fit,
                "difficulty": e.difficulty, "accessibility": e.accessibility, "evidence_strength": e.evidence_strength,
                "prerequisites": [], "judged_by": "llm"},
    })["likelihood"]


def expected_likelihood(e: Event, gates: list[Gate], p_override: Optional[dict[str, float]] = None) -> float:
    """Likelihood averaged over whether each gate that applies to the event is met.

    A requirement that fails takes away the *upsides* (you cannot get what needs it). It does not take
    away the *risks* of trying: you can still burn savings on a company you cannot afford to run. So only
    good outcomes collapse; bad ones keep their likelihood. Without this, an unworkable route would score
    about zero, which beats any route with real downsides, and no requirement could ever change the answer."""
    likely = met_likelihood(e)
    if e.valence < 0:
        return likely
    p_override = p_override or {}
    ps = [p_override.get(g.id, g.p_met) for g in gates if not g.applies_to or e.key in g.applies_to]
    met = prod(ps) if ps else 1.0
    return met * likely + (1 - met) * min(likely, probability.HARD_CAP)


def route_score(route: Route, gates: list[Gate], probs: dict[str, float], p_override: Optional[dict[str, float]] = None) -> float:
    """Average of valence x impact x likelihood x weight. Because the weights are linear in the priority
    probabilities, the expectation over "what matters most" is just the weight at those probabilities."""
    mine = [g for g in gates if g.route_id == route.id]
    if not route.events:
        return 0.0
    return sum(
        e.valence * e.impact * expected_likelihood(e, mine, p_override) * (BASE_WEIGHT + PRIORITY_BOOST * probs.get(e.dimension, 0.0))
        for e in route.events
    ) / len(route.events)


def scores(s: Session, p_override: Optional[dict[str, float]] = None, probs: Optional[dict[str, float]] = None) -> dict[str, float]:
    probs = probs or s.priorities.probs
    return {r.id: route_score(r, s.gates, probs, p_override) for r in s.routes}


def leader(sc: dict[str, float]) -> Optional[str]:
    return max(sc, key=lambda k: (sc[k], k)) if sc else None


def event_likelihoods(s: Session) -> dict[str, dict[str, float]]:
    """{route id: {event key: likelihood}}: what the terminal shows next to each outcome."""
    return {r.id: {e.key: expected_likelihood(e, [g for g in s.gates if g.route_id == r.id]) for e in r.events} for r in s.routes}


@dataclass
class GapValue:
    gap: str                       # gate id, or "priorities"
    kind: str                      # "gate" | "priorities"
    label: str                     # what is unknown, in words
    p: float                       # P(met) for a gate; the top priority's probability for priorities
    evpi: float
    flip: float
    rel: float                     # evpi relative to the spread between routes
    affects: list[str] = field(default_factory=list)   # route ids whose score moves with the answer
    outcomes: list[tuple[float, str]] = field(default_factory=list)


def _open(g: Gate) -> bool:
    return g.status == "open" and SETTLED < g.p_met < 1 - SETTLED


def _value(s: Session, now: dict[str, float], outcomes: list[tuple[float, dict, Optional[dict]]]) -> tuple[float, float, list[str]]:
    """(EVPI, flip probability, routes affected) for a set of (probability, gate override, priorities override)."""
    best_now, lead_now = max(now.values()), leader(now)
    expected_best, flip, moved = 0.0, 0.0, set()
    for p, p_override, probs in outcomes:
        sc = scores(s, p_override, probs)
        expected_best += p * max(sc.values())
        flip += p * (leader(sc) != lead_now)
        moved |= {r for r in sc if abs(sc[r] - now[r]) > 1e-9}
    return max(0.0, expected_best - best_now), flip, sorted(moved)


def rank_gaps(s: Session) -> list[GapValue]:
    """Every open unknown, most valuable first."""
    if len(s.routes) < 2:
        return []
    now = scores(s)
    spread = max(max(now.values()) - min(now.values()), MIN_SPREAD)
    out: list[GapValue] = []

    for g in s.gates:
        if not _open(g):
            continue
        evpi, flip, affects = _value(s, now, [(g.p_met, {g.id: 1.0}, None), (1 - g.p_met, {g.id: 0.0}, None)])

        # A route often needs several requirements at once. Resolving one alone may not change the leader
        # while the others are still open, yet it is exactly the thing that could sink the route once they
        # hold. So also value it in the world where the route's other open requirements are met, weighted by
        # the chance that world is real. (If any of them fails the route is gone whatever this one says.)
        rest = [o for o in s.gates if o.route_id == g.route_id and o.id != g.id and o.status == "open"]
        if rest:
            met = {o.id: 1.0 for o in rest}
            p_rest = prod(o.p_met for o in rest)
            evpi_c, flip_c, affects_c = _value(s, scores(s, met), [(g.p_met, {**met, g.id: 1.0}, None), (1 - g.p_met, {**met, g.id: 0.0}, None)])
            if p_rest * evpi_c > evpi:
                evpi, flip, affects = p_rest * evpi_c, max(flip, p_rest * flip_c), affects_c
        out.append(GapValue(g.id, "gate", g.requirement, g.p_met, evpi, flip, evpi / spread, affects,
                            [(g.p_met, "met"), (1 - g.p_met, "unmet")]))

    pr = s.priorities
    if pr.status == "open" and max(pr.probs.values()) < 1 - SETTLED:
        outcomes = [(p, {}, {d: 1.0 if d == top else 0.0 for d in DIMENSIONS}) for top, p in pr.probs.items() if p > 0]
        evpi, flip, affects = _value(s, now, outcomes)
        top = max(pr.probs, key=pr.probs.get)
        out.append(GapValue("priorities", "priorities", "what matters most to you here", pr.probs[top], evpi, flip,
                            evpi / spread, affects, [(p, d) for d, p in pr.probs.items()]))

    return sorted(out, key=lambda v: (v.evpi, v.flip), reverse=True)


def should_stop(ranked: list[GapValue]) -> Optional[str]:
    """Why to stop asking, or None to carry on."""
    if not ranked:
        return "there is nothing left that we are unsure about"
    top = ranked[0]
    if top.rel < STOP_REL_EVPI and top.flip < STOP_FLIP:
        return "no remaining question could change which route looks best"
    return None


def describe_dimension(d: str) -> str:
    return f"{d} ({DIMENSION_MEANING[d]})"
