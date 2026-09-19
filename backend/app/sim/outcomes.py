"""The generic sampler: any decision, any size.

An option's *outcome model* is a list of possible events over dated steps (tonight, week 3,
2031 …). This module samples a thousand lives from such a model with numpy and nothing else:
no LLM, no network, deterministic from its inputs. A stored model re-runs identically forever.

Where an event's likelihood comes from is recorded on the event (`basis`):
  sourced    a published figure found by research and verified in code -> a fixed probability
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
BINS = {"almost certainly": (0.93, 0.99), "rare": (0.02, 0.10), "sometimes": (0.15, 0.35), "as often as not": (0.40, 0.60), "usually": (0.70, 0.90)}
DEFAULT_BIN = "sometimes"
RELATION_MULTIPLIER = {"likelier": 2.0, "less_likely": 0.5, "prevents": 0.0}  # "requires" is handled as a gate
ASSUMED_BETA = 0.20      # log-odds per SD of a trait when only the DIRECTION of a personality effect is known
TRAIT_NAMES = {"O": "openness", "C": "conscientiousness", "E": "extraversion", "A": "agreeableness", "N": "neuroticism"}
EXTRAS_WEIGHT = 0.35     # how strongly the life you read is held to a typical NUMBER of less-than-even events
GAP_BAND = 0.15          # half-width drawn around a published figure whose studied population fits poorly
UNANSWERED_WIDEN = 0.08  # each open clarifying question stretches every range on the branch by this much
MAX_STEPS = {"days": 30, "weeks": 26, "months": 36, "years": 40}
STEP_DAYS = {"days": 1, "weeks": 7, "months": 30.4375, "years": 365.25}


BIG_DEFAULT_YEARS, BIG_MAX_YEARS = 3, 5   # a big decision is modelled where it plays out: three years, five at most
LONG_MONTHS = 6                           # from here on a horizon is "long": finer steps early, coarser later


def is_long(unit: str, count: int) -> bool:
    return unit == "years" or (unit == "months" and count >= LONG_MONTHS)


def _add_months(start: date, k: int) -> date:
    return date(start.year + (start.month - 1 + k) // 12, (start.month - 1 + k) % 12 + 1, min(start.day, 28))


def step_dates(unit: str, count: int, start: date) -> list[date]:
    """The date each step begins; step 0 is the day of the decision. Short horizons step evenly.
    Long ones are finer where a decision is felt most: weekly for the first month, monthly to the
    end of year one, then quarterly."""
    count = max(1, min(int(count), MAX_STEPS[unit]))
    if unit == "days":
        return [start + timedelta(days=k) for k in range(count)]
    if unit == "weeks":
        return [start + timedelta(weeks=k) for k in range(count)]
    months = count * 12 if unit == "years" else count
    if not is_long(unit, count):
        return [_add_months(start, k) for k in range(months)]
    weekly = [start + timedelta(weeks=k) for k in range(4)]
    monthly = [_add_months(start, k) for k in range(1, min(months, 12))]
    quarterly = [_add_months(start, k) for k in range(12, months, 3)]
    return weekly + monthly + quarterly


def horizon_end(unit: str, count: int, start: date) -> date:
    count = max(1, min(int(count), MAX_STEPS[unit]))
    if unit in ("days", "weeks"):
        return start + timedelta(days=count * (1 if unit == "days" else 7))
    return _add_months(start, count * 12 if unit == "years" else count)


def step_offsets(unit: str, count: int, start: date) -> list[int]:
    """Days from the decision to the start of each step, plus one last entry: the end of the horizon."""
    return [(d - start).days for d in step_dates(unit, count, start)] + [(horizon_end(unit, count, start) - start).days]


def window_from_days(offsets: list[int], from_day: float, to_day: float) -> list[int]:
    """A window given in days after the decision -> [first step, last step]."""
    n = len(offsets) - 1
    at = lambda day: max(0, max((i for i in range(n) if offsets[i] <= day), default=0))
    lo = at(max(0, from_day))
    return [lo, max(lo, at(max(from_day, to_day)))]


def date_label(at: date, unit: str, today: date | None = None) -> str:
    """How a step is captioned: simply its date. "21 September" (with the year when it is not this
    year), and "today" only for today's date. Never a count
    of days, weeks or months."""
    today = today or date.today()
    if at == today:
        return "today"
    return f"{at.day} {at:%B}" + ("" if at.year == today.year else f" {at.year}")


def step_labels(unit: str, dates: list[date], tonight: bool = False) -> list[str]:
    return [date_label(d, unit) for d in dates]


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
    cumulative: np.ndarray = field(default_factory=lambda: np.zeros((0, 0)))  # [step, event] share in which it has happened by then
    score: np.ndarray = field(default_factory=lambda: np.zeros(0))

    def life(self, run: int) -> list[list[str]]:
        """Event keys firing at each step in one simulated life."""
        return [[k for e, k in enumerate(self.keys) if self.fired[s, run, e]] for s in range(self.fired.shape[0])]

    def outlook(self, run: int) -> list[dict]:
        out = []
        for s in range(self.shares.shape[0]):
            out.append({
                k: {"share": round(float(self.shares[s, e]), 4), "words": likelihood_words(float(self.shares[s, e])),
                    "value": "yes" if self.happened[s, run, e] else "no",
                    "probability": round(float(self.cumulative[s, e]), 4)}
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
        before = [d.get("key") for d in events[i].get("depends_on", [])] + list(events[i].get("after") or []) \
            + list(events[i].get("requires") or [])
        for key in before:
            if key in index:
                visit(index[key], trail + (i,))
        seen.add(i)
        order.append(i)

    for i in range(len(events)):
        visit(i)
    return order


def logit(p):
    return np.log(p / (1.0 - p))


def logistic(x):
    return 1.0 / (1.0 + np.exp(-x))


def personality_shift(event: dict, personality: dict | None) -> tuple[float, list[dict]]:
    """Log-odds shift for one event, and its itemised terms. z is shrunk by the estimate's confidence,
    exactly as the background engine does; no estimate, no shift."""
    if not personality:
        return 0.0, []
    confidence = float(personality.get("confidence") or 0.0)
    items = []
    for term in (event.get("terms") or [])[:2]:
        z = float(personality.get(term["trait"]) or 0.0)
        shift = term["direction"] * term["beta"] * z * confidence
        items.append({"trait": term["trait"], "trait_name": TRAIT_NAMES[term["trait"]], "z": round(z, 3),
                      "confidence": round(confidence, 3), "direction": term["direction"], "beta": term["beta"],
                      "shift_logodds": round(shift, 4), "basis": term["basis"]})
    return float(sum(i["shift_logodds"] for i in items)), items


def base_of(event: dict, widen: float = 0.0) -> tuple[float, tuple[float, float] | None]:
    """(central base probability, the range each life draws it from or None for a point)."""
    if event.get("basis") in ("sourced", "personal") and event.get("base_probability") is not None:
        p = float(event["base_probability"])
        half = float(event.get("band") or 0.0) + widen
        return p, ((max(0.005, p - half), min(0.995, p + half)) if half else None)
    lo, hi = BINS.get(event.get("bin") or DEFAULT_BIN, BINS[DEFAULT_BIN])
    lo, hi = max(0.005, lo - widen), min(0.995, hi + widen)
    return (lo + hi) / 2, (lo, hi)


def seed_for(person_id: str, events: list[dict], n_steps: int, runs: int, patches: list[dict]) -> int:
    fields = ("key", "kind", "window", "base_probability", "band", "bin", "basis", "depends_on", "terms", "after", "requires", "head")
    core = sorted(({k: e.get(k) for k in fields} for e in events), key=lambda e: e["key"])
    blob = json.dumps([person_id, core, n_steps, runs, patches], sort_keys=True, default=str)
    return int.from_bytes(hashlib.sha256(blob.encode()).digest()[:8], "big")


def simulate_outcomes(person_id: str, events: list[dict], n_steps: int, runs: int,
                      patches: list[dict] | None = None, widen: float = 0.0,
                      personality: dict | None = None, durations: list[float] | None = None) -> OutcomeResult:
    """`patches` are the person's commits: {step, force: [keys], prevent: [keys], likelier: [keys],
    less_likely: [keys]} — applied to every run from that step on."""
    events = sorted(events, key=lambda e: e["key"])  # a canonical order: how the list is displayed never changes the lives
    patches = sorted(patches or [], key=lambda p: p.get("step", 0))
    traits = {k: personality.get(k) for k in ("O", "C", "E", "A", "N", "confidence")} if personality else None
    durations = list(durations) if durations else [1.0] * n_steps  # days each step lasts; steps need not be equal
    extras = ([{"widen": widen}] if widen else []) + ([{"personality": traits}] if traits else []) \
        + ([{"durations": durations}] if len(set(durations)) > 1 else [])
    seed = seed_for(person_id, events, n_steps, runs, patches + extras)
    rng = np.random.default_rng(seed)
    E, N = len(events), runs
    keys = [e["key"] for e in events]
    index = {k: i for i, k in enumerate(keys)}
    order = _ordered(events)

    # Each life's own probability for each event: fixed when sourced, drawn inside the bin when estimated.
    draw = rng.random((E, N))
    prob = np.zeros((E, N))
    windows = []
    length = np.array(durations, dtype=float)
    for i, e in enumerate(events):
        lo, hi = (e.get("window") or [0, n_steps - 1])[:2]
        lo, hi = max(0, int(lo)), min(n_steps - 1, int(hi))
        windows.append((lo, max(lo, hi)))
        # 1. base: a published or personal figure (a band around it when the fit is poor), or a draw inside the bin
        centre, band = base_of(e, widen)
        prob[i] = band[0] + draw[i] * (band[1] - band[0]) if band else centre
        # 2. personality: a shift in log-odds, the same for every life
        shift, _ = personality_shift(e, personality)
        if shift:
            prob[i] = logistic(logit(np.clip(prob[i], 0.005, 0.995)) + shift)
        prob[i] = np.clip(prob[i], 0.005, 0.995)

    until = np.concatenate([[0.0], np.cumsum(length)])  # days elapsed at the start of each step
    open_since = np.full((E, N), -1)                    # the step at which each life first became free to have the event

    def hazard_at(i: int, s: int, free: np.ndarray) -> np.ndarray:
        """one_time / state: `prob` is the chance it happens at all GIVEN that what it follows or
        requires has happened; it is spread, in proportion to how long each step lasts, over what is
        left of the window from the moment the life became free to have it. recurring: per step."""
        if events[i].get("kind") == "recurring":
            return prob[i]
        lo, hi = windows[i]
        open_since[i] = np.where((open_since[i] < 0) & free, s, open_since[i])
        left = until[hi + 1] - until[np.clip(open_since[i], lo, hi)]
        return 1.0 - (1.0 - prob[i]) ** (length[s] / np.maximum(left, 1e-9))

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
            if e.get("head"):  # step zero IS the choice: it happens, first, in every life
                fires = np.full(N, s == 0)
            elif i in forced:
                fires = np.ones(N, bool) if recurring else ~so_far[i]
            elif blocked[i] or not (lo <= s <= hi):
                fires = np.zeros(N, bool)
            else:
                mult = np.full(N, nudge[i])
                free = np.ones(N, bool)
                for key in e.get("requires") or []:       # cannot happen at all unless that has happened
                    if key in index:
                        free &= so_far[index[key]]
                for key in e.get("after") or []:          # not before that has happened, or its window has closed
                    if key in index:
                        free &= so_far[index[key]] | (s > windows[index[key]][1])
                for dep in e.get("depends_on", []):
                    j = index.get(dep.get("key"))
                    if j is None:
                        continue
                    relation = dep.get("relation", "likelier")
                    if relation == "requires":
                        mult = np.where(so_far[j], mult, 0.0)
                    else:
                        mult = np.where(so_far[j], mult * RELATION_MULTIPLIER.get(relation, 1.0), mult)
                fires = free & (u[i] < np.clip(hazard_at(i, s, free) * mult, 0.0, 1.0)) & (recurring | ~so_far[i])
            so_far[i] |= fires
            fired[s, :, i] = fires
        happened[s] = so_far.T

    if E == 0:
        return OutcomeResult(seed, N, keys, [1.0] * n_steps, 0, 0, fired, happened, np.zeros((n_steps, 0)),
                             np.zeros((n_steps, 0)), np.zeros(N))

    # What is compared across lives: "has happened" for one-off events, "happened this step" for recurring ones.
    recurring_mask = np.array([e.get("kind") == "recurring" for e in events])
    view = np.where(recurring_mask[None, None, :], fired, happened)
    shares = view.mean(axis=1)
    cumulative = happened.mean(axis=1)

    # The life you read is the MODAL life: every event that happens in at least half of the lives
    # happens, the rest do not. Among the thousand, the run closest to that (each event weighted by
    # how far its probability is from a coin flip); ties go to the run whose timing is most typical.
    p_final = cumulative[-1]
    target = p_final >= 0.5
    weight = np.abs(p_final - 0.5)
    distance = ((happened[-1] != target[None, :]) * weight[None, :]).sum(axis=1)
    # ...and a typical life also has its share of the less-than-even things: as many of them as the
    # thousand lives have on average. Which ones is left to the weights above (the likeliest cost least).
    expected_extras = int(round(float(p_final[~target].sum())))
    extras = (happened[-1] & ~target[None, :]).sum(axis=1)
    distance = distance + EXTRAS_WEIGHT * np.abs(extras - expected_extras)
    first = np.where(happened.any(axis=0), happened.argmax(axis=0), -1).astype(float)      # [run, event] first step, -1 = never
    seen = np.where(first >= 0, first, np.nan)
    with np.errstate(all="ignore"):
        median = np.nan_to_num(np.nanmedian(seen, axis=0), nan=0.0)
    timing = np.where(target[None, :] & (first >= 0), np.abs(first - median[None, :]), 0.0).sum(axis=1)
    typical = int(np.lexsort((timing, np.round(distance, 9)))[0])
    # The rare life: a run far from the target that still has a life in it (three events beyond the choice).
    head_mask = np.array([bool(e.get("head")) for e in events])
    eventful = (happened[-1] & ~head_mask[None, :]).sum(axis=1) >= 3
    pool = np.where(eventful, distance, -1.0)
    rare = int(pool.argmax()) if eventful.any() else int(distance.argmax())
    # Solidity: how settled things are at each step across the thousand lives (1 = every event is either
    # sure to have happened or sure not to have; 0.5 = all coin flips). It does not depend on which life is shown.
    solidity = [float(np.maximum(shares[s], 1.0 - shares[s]).mean()) for s in range(n_steps)]
    return OutcomeResult(seed, N, keys, solidity, typical, rare, fired, happened, shares, cumulative, -distance)


RELATION_NOTE_ORDER = {"after": "not before that has happened (or its moment has passed)",
                       "requires": "cannot happen at all unless that has happened"}
RELATION_NOTE = {"likelier": "doubles the chance once that has happened", "less_likely": "halves the chance once that has happened",
                 "prevents": "cannot happen once that has happened", "requires": "can only happen after that has happened"}


def describe(events: list[dict], result: OutcomeResult, personality: dict | None, widen: float = 0.0) -> None:
    """Writes `probability` and the full `breakdown` onto each event (in place): base -> personality
    shift -> dependencies -> the share of the simulated lives in which it actually happened."""
    labels = {e["key"]: e["label"] for e in events}
    final = dict(zip(result.keys, result.cumulative[-1])) if result.cumulative.size else {}
    for e in events:
        if e.get("head"):
            e["probability"] = 1.0
            e["breakdown"] = {"base": {"kind": "choice", "value": 1.0, "range": None, "evidence_id": None, "reference_class": None,
                                       "note": "this is the option itself: on this path it is what you chose, so it happens"},
                              "personality": [], "dependencies": [], "adjusted": 1.0, "simulated": 1.0,
                              "simulated_note": "the first step of every simulated life on this path"}
            continue
        centre, band = base_of(e, widen)
        shift, items = personality_shift(e, personality)
        adjusted = float(logistic(logit(min(max(centre, 0.005), 0.995)) + shift)) if shift else centre
        per = "in any one step" if e.get("kind") == "recurring" else "within its window"
        note = {
            "sourced": f"a published figure for the nearest studied group, converted to the chance {per}"
                       + ("; drawn from a band around it because that group fits loosely" if band else ""),
            "personal": f"your own track record of kept commitments, as the chance {per}",
        }.get(e.get("basis"), f"no published figure was found: “{e.get('bin') or DEFAULT_BIN}” means this range, and each "
                              f"simulated life draws its own value inside it (the chance {per})")
        simulated = round(float(final.get(e["key"], 0.0)), 4)
        e["probability"] = simulated
        e["breakdown"] = {
            "base": {"kind": e.get("basis", "estimated"), "value": round(centre, 4),
                     "range": [round(band[0], 4), round(band[1], 4)] if band else None,
                     "evidence_id": e.get("evidence_id"), "reference_class": e.get("reference_class"), "note": note},
            "personality": items,
            "dependencies": [{"on": d["key"], "label": labels.get(d["key"], d["key"]), "relation": d.get("relation", "likelier"),
                              "multiplier": RELATION_MULTIPLIER.get(d.get("relation", "likelier"), 1.0),
                              "note": RELATION_NOTE.get(d.get("relation", "likelier"), "")} for d in e.get("depends_on", [])]
                            + [{"on": k, "label": labels.get(k, k), "relation": rel, "multiplier": 1.0, "note": RELATION_NOTE_ORDER[rel]}
                               for rel in ("requires", "after") for k in (e.get(rel) or [])
                               if k in labels and not (rel == "after" and k in (e.get("requires") or []))],
            "adjusted": round(adjusted, 4),
            "simulated": simulated,
            "simulated_note": ("share of the 1,000 lives in which it happens at least once before the horizon"
                               if e.get("kind") == "recurring" else
                               "share of the 1,000 lives in which it has happened (and, for a lasting state, is true) at the horizon"),
        }


# --- four running measures, as change from now (now = 0) ---

MEASURES = ("health", "joy", "fulfilment", "money")
HALF_LIFE_DAYS = {"health": 730.0, "joy": 10.0, "fulfilment": None, "money": None}  # None = it stays
BAND = (10, 90)                                  # the percentile band reported around the mean of the thousand lives
MARK_THRESHOLDS = (0.5, 1.5, 3.0)                # |change| at which one, two and three marks are shown
PER_DAYS = {"month": 30.4375, "year": 365.25}
USD_TO_CAD_MEASURES = 1.37


def marks(delta: float) -> str:
    n = sum(abs(delta) >= t for t in MARK_THRESHOLDS)
    return "=" if n == 0 else ("+" if delta > 0 else "\u2212") * n


def _convert(value: float, currency: str, to: str) -> float:
    if currency == to:
        return value
    if (currency, to) == ("USD", "CAD"):
        return value * USD_TO_CAD_MEASURES
    if (currency, to) == ("CAD", "USD"):
        return value / USD_TO_CAD_MEASURES
    return value  # other pairs are not converted; the card says so


def measures(result: OutcomeResult, events: list[dict], offsets: list[int], dates: list[str], currency: str | None = None,
             baseline: dict | None = None) -> dict:
    """Accumulates each event's effects inside every simulated life, step by step. An effect is a
    judgement on a five-point scale about what a moment MEANS (never whether it happens). Joy is a
    pulse that fades fast; health persists and fades slowly; fulfilment and money stay. Separately,
    real amounts (where known) run through a currency ledger."""
    by_key = {e["key"]: e for e in events}
    ordered = [by_key[k] for k in result.keys]
    n_steps, N = result.fired.shape[0], result.fired.shape[1]
    effect = np.array([[int((e.get("effects") or {}).get(m, 0)) for m in MEASURES] for e in ordered], dtype=float).reshape(len(ordered), 4)
    level = np.zeros((N, 4))
    series = {m: [] for m in MEASURES}
    for s in range(n_steps):
        if s:
            elapsed = offsets[s] - offsets[s - 1]
            fade = np.array([1.0 if HALF_LIFE_DAYS[m] is None else 0.5 ** (elapsed / HALF_LIFE_DAYS[m]) for m in MEASURES])
            level = level * fade
        level = level + result.fired[s].astype(float) @ effect
        low, high = np.percentile(level, BAND, axis=0)
        for j, m in enumerate(MEASURES):
            series[m].append({"at": dates[s], "mean": round(float(level[:, j].mean()), 3), "low": round(float(low[j]), 3),
                              "high": round(float(high[j]), 3)})
    end = {m: {"delta": series[m][-1]["mean"], "low": series[m][-1]["low"], "high": series[m][-1]["high"],
               "marks": marks(series[m][-1]["mean"])} for m in MEASURES} if n_steps else {}

    money_end = None
    priced = [(i, e["money_amount"]) for i, e in enumerate(ordered) if e.get("money_amount")]
    if priced and n_steps:
        currency = currency or priced[0][1].get("currency") or "CAD"
        horizon = float(offsets[-1])
        first = np.where(result.happened.any(axis=0), result.happened.argmax(axis=0), -1)  # [run, event]
        ledger = np.zeros(N)
        for i, amount in priced:
            value = _convert(float(amount["value"]), amount.get("currency") or currency, currency)
            since = np.where(first[:, i] >= 0, horizon - np.array(offsets)[np.clip(first[:, i], 0, n_steps - 1)], 0.0)
            times = np.where(first[:, i] >= 0, 1.0, 0.0) if amount.get("per", "once") == "once" else since / PER_DAYS[amount["per"]]
            ledger += value * times
        low, high = np.percentile(ledger, BAND)
        money_end = {"value": round(float(ledger.mean())), "low": round(float(low)), "high": round(float(high)), "currency": currency,
                     "note": _against(float(ledger.mean()), baseline, currency, horizon)}
    return {"series": series, "end": end, "money_end": money_end}


def _against(total: float, baseline: dict | None, currency: str, horizon_days: float) -> str:
    """The ledger set against what the person told us they earn or own, in words."""
    sign = "in" if total >= 0 else "out"
    plain = f"about {abs(total):,.0f} {currency} {sign} over this stretch, counting only the amounts that are known"
    if not baseline:
        return plain
    income, worth = baseline.get("income"), baseline.get("net_worth")
    if income:
        ratio = abs(total) / (_convert(float(income), baseline.get("currency") or currency, currency) * max(horizon_days / 365.25, 1e-9))
        return f"{plain}: roughly {_fraction(ratio)} what you earn now over the same stretch"
    if worth:
        return f"{plain}: roughly {_fraction(abs(total) / _convert(float(worth), baseline.get('currency') or currency, currency))} your current net worth"
    return plain


def _fraction(ratio: float) -> str:
    names = [(0.15, "a tenth of"), (0.23, "a fifth of"), (0.29, "a quarter of"), (0.42, "a third of"), (0.62, "half of"),
             (0.87, "three quarters of"), (1.2, "about the same as"), (1.7, "one and a half times"), (2.5, "twice"), (3.5, "three times")]
    return next((name for ceiling, name in names if ratio < ceiling), f"{ratio:.0f} times")
