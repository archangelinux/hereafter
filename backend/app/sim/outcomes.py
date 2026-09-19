"""The generic sampler: any decision, any size.

An option's *outcome model* is a list of possible events over dated steps (tonight, week 3,
2031 …). This module samples a thousand lives from such a model with numpy and nothing else:
no LLM, no network, deterministic from its inputs. A stored model re-runs identically forever.

Where an event's likelihood comes from is recorded on the event (`basis`):
  sourced    a published figure found by research and verified in code -> a fixed probability
  estimate   (any basis) the probability logic has combined the base rate with the person's context; each
             life draws around its likelihood, spread by its stated uncertainty
  estimated  no published figure: only a verbal bin is known; each simulated life draws its own
             probability uniformly inside the bin's range, so the uncertainty is carried, not hidden
  background the life-course engine (engine.py), merged in by the caller on long horizons
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np

from .engine import likelihood_words

# Hand-set, listed in data/SOURCES.md under "Model assumptions".
BINS = {"rare": (0.02, 0.10), "sometimes": (0.15, 0.35), "as often as not": (0.40, 0.60), "usually": (0.70, 0.90)}
DEFAULT_BIN = "sometimes"
RELATION_MULTIPLIER = {"likelier": 2.0, "less_likely": 0.5, "prevents": 0.0}  # "requires" is handled as a gate
GAP_BAND = 0.15          # half-width drawn around a published figure whose studied population fits poorly
UNANSWERED_WIDEN = 0.08  # each open clarifying question stretches every range on the branch by this much
MAX_STEPS = {"days": 30, "weeks": 26, "months": 36, "years": 40}
STEP_DAYS = {"days": 1, "weeks": 7, "months": 30.4375, "years": 365.25}


def step_dates(unit: str, count: int, start: date) -> list[date]:
    """The date each step begins. Days start today; years start next January, like the engine."""
    count = max(1, min(int(count), MAX_STEPS[unit]))
    if unit == "days":
        return [start + timedelta(days=k) for k in range(count)]
    if unit == "weeks":
        return [start + timedelta(weeks=k) for k in range(count)]
    if unit == "months":
        return [date(start.year + (start.month - 1 + k) // 12, (start.month - 1 + k) % 12 + 1, min(start.day, 28))
                for k in range(count)]
    return [date(start.year + k + 1, 1, 1) for k in range(count)]


def step_labels(unit: str, dates: list[date], tonight: bool = False) -> list[str]:
    if unit == "days":
        first = "tonight" if tonight else "today"
        return [first if k == 0 else "tomorrow" if k == 1 else f"day {k + 1}" for k in range(len(dates))]
    if unit == "weeks":
        return ["this week" if k == 0 else f"week {k + 1}" for k in range(len(dates))]
    if unit == "months":
        return ["this month" if k == 0 else f"month {k + 1}" for k in range(len(dates))]
    return [str(d.year) for d in dates]


@dataclass
class OutcomeResult:
    seed: int
    runs: int
    keys: list[str]
    solidity: list[float]
    typical: int
    rare: int
    fired: np.ndarray            # [step, run, event] did it happen in this step
    happened: np.ndarray         # [step, run, event] has it happened by the end of this step
    shares: np.ndarray           # [step, event] share of runs for the outlook
    score: np.ndarray = field(default_factory=lambda: np.zeros(0))

    def life(self, run: int) -> list[list[str]]:
        """Event keys firing at each step in one simulated life."""
        return [[k for e, k in enumerate(self.keys) if self.fired[s, run, e]] for s in range(self.fired.shape[0])]

    def outlook(self, run: int) -> list[dict]:
        out = []
        for s in range(self.shares.shape[0]):
            out.append({
                k: {"share": round(float(self.shares[s, e]), 4), "words": likelihood_words(float(self.shares[s, e])),
                    "value": "yes" if self.happened[s, run, e] else "no"}
                for e, k in enumerate(self.keys)
            })
        return out


def _ordered(events: list[dict]) -> list[int]:
    """Dependencies first, so an event can react to another in the same step. Cycles fall back to list order."""
    index = {e["key"]: i for i, e in enumerate(events)}
    order, seen = [], set()

    def visit(i: int, trail: tuple = ()) -> None:
        if i in seen or i in trail:
            return
        for dep in events[i].get("depends_on", []):
            if dep.get("key") in index:
                visit(index[dep["key"]], trail + (i,))
        seen.add(i)
        order.append(i)

    for i in range(len(events)):
        visit(i)
    return order


def seed_for(person_id: str, events: list[dict], n_steps: int, runs: int, patches: list[dict]) -> int:
    core = [{k: e.get(k) for k in ("key", "kind", "window", "probability", "band", "bin", "basis", "depends_on")}
            | ({"estimate": [e["estimate"]["likelihood"], e["estimate"]["spread"]]} if e.get("estimate") else {})
            for e in events]
    blob = json.dumps([person_id, core, n_steps, runs, patches], sort_keys=True, default=str)
    return int.from_bytes(hashlib.sha256(blob.encode()).digest()[:8], "big")


def simulate_outcomes(person_id: str, events: list[dict], n_steps: int, runs: int,
                      patches: list[dict] | None = None, widen: float = 0.0) -> OutcomeResult:
    """`patches` are the person's commits: {step, force: [keys], prevent: [keys], likelier: [keys],
    less_likely: [keys]} — applied to every run from that step on."""
    patches = sorted(patches or [], key=lambda p: p.get("step", 0))
    seed = seed_for(person_id, events, n_steps, runs, patches + [{"widen": widen}] if widen else patches)
    rng = np.random.default_rng(seed)
    E, N = len(events), runs
    keys = [e["key"] for e in events]
    index = {k: i for i, k in enumerate(keys)}
    order = _ordered(events)

    # Each life's own probability for each event: fixed when sourced, drawn inside the bin when estimated.
    draw = rng.random((E, N))
    prob = np.zeros((E, N))
    hazard = np.zeros((E, N))
    windows = []
    for i, e in enumerate(events):
        lo, hi = (e.get("window") or [0, n_steps - 1])[:2]
        lo, hi = max(0, int(lo)), min(n_steps - 1, int(hi))
        windows.append((lo, max(lo, hi)))
        estimate = e.get("estimate")
        if estimate:
            # the probability logic's estimate (probability.py): its likelihood, spread by its own uncertainty
            half = float(estimate["spread"]) + widen
            prob[i] = np.clip(float(estimate["likelihood"]) + (2 * draw[i] - 1) * half, 0.005, 0.995)
        elif e.get("basis") in ("sourced", "personal") and e.get("probability") is not None:
            # a published (or personal track-record) figure; a band around it when the fit is poor
            half = float(e.get("band") or 0.0) + widen
            prob[i] = np.clip(float(e["probability"]) + (2 * draw[i] - 1) * half, 0.005, 0.995)
        else:
            b_lo, b_hi = BINS.get(e.get("bin") or DEFAULT_BIN, BINS[DEFAULT_BIN])
            b_lo, b_hi = max(0.005, b_lo - widen), min(0.995, b_hi + widen)
            prob[i] = b_lo + draw[i] * (b_hi - b_lo)
        span = windows[i][1] - windows[i][0] + 1
        # one_time / state: `prob` is the chance it happens at all inside the window.
        # recurring: `prob` is the chance in any one step.
        hazard[i] = prob[i] if e.get("kind") == "recurring" else 1.0 - (1.0 - prob[i]) ** (1.0 / span)

    fired = np.zeros((n_steps, N, E), bool)
    happened = np.zeros((n_steps, N, E), bool)
    so_far = np.zeros((E, N), bool)
    blocked = np.zeros(E, bool)
    nudge = np.ones(E)
    for s in range(n_steps):
        u = rng.random((E, N))  # always drawn in full, so the stream never depends on state
        forced = set()
        for p in patches:
            if p.get("step") != s:
                continue
            forced |= {index[k] for k in p.get("force", []) if k in index}
            for k in p.get("prevent", []):
                if k in index:
                    blocked[index[k]] = True
            for k in p.get("likelier", []):
                if k in index:
                    nudge[index[k]] *= RELATION_MULTIPLIER["likelier"]
            for k in p.get("less_likely", []):
                if k in index:
                    nudge[index[k]] *= RELATION_MULTIPLIER["less_likely"]
        for i in order:
            e = events[i]
            lo, hi = windows[i]
            recurring = e.get("kind") == "recurring"
            if i in forced:
                fires = np.ones(N, bool) if recurring else ~so_far[i]
            elif blocked[i] or not (lo <= s <= hi):
                fires = np.zeros(N, bool)
            else:
                mult = np.full(N, nudge[i])
                for dep in e.get("depends_on", []):
                    j = index.get(dep.get("key"))
                    if j is None:
                        continue
                    relation = dep.get("relation", "likelier")
                    if relation == "requires":
                        mult = np.where(so_far[j], mult, 0.0)
                    else:
                        mult = np.where(so_far[j], mult * RELATION_MULTIPLIER.get(relation, 1.0), mult)
                fires = (u[i] < np.clip(hazard[i] * mult, 0.0, 1.0)) & (recurring | ~so_far[i])
            so_far[i] |= fires
            fired[s, :, i] = fires
        happened[s] = so_far.T

    if E == 0:
        return OutcomeResult(seed, N, keys, [1.0] * n_steps, 0, 0, fired, happened, np.zeros((n_steps, 0)), np.zeros(N))

    # What is compared across lives: "has happened" for one-off events, "happened this step" for recurring ones.
    recurring_mask = np.array([e.get("kind") == "recurring" for e in events])
    view = np.where(recurring_mask[None, None, :], fired, happened)
    shares = view.mean(axis=1)
    modal = shares >= 0.5
    agree = view == modal[:, None, :]
    score = agree.sum(axis=(0, 2)).astype(float)
    typical = int(score.argmax())
    eventful = fired.sum(axis=(0, 2)) >= 2
    rare_pool = np.where(eventful, score, np.inf)
    rare = int(rare_pool.argmin()) if eventful.any() else int(score.argmin())
    solidity = [float((view[s] == view[s, typical]).mean()) for s in range(n_steps)]
    return OutcomeResult(seed, N, keys, solidity, typical, rare, fired, happened, shares, score)
