"""Loads the published transition tables in /data into age-indexed numpy arrays.

Every number the simulator uses comes from these files (cited in data/SOURCES.md) except the
few rule-of-thumb constants declared at the top of engine.py, which SOURCES.md also lists.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from ..models import INCOME_BANDS

MAX_AGE = 120
PCTL_KNOTS = np.array([0.10, 0.25, 0.50, 0.75, 0.90])


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"missing transition table {path} (see data/SOURCES.md)")
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _by_age(rows, value_key: str, default: float = 0.0, hold_last: bool = False) -> np.ndarray:
    """Single-year rows -> array indexed by age 0..MAX_AGE."""
    out = np.full(MAX_AGE + 1, default, dtype=float)
    ages = []
    for r in rows:
        a = int(float(r["age"]))
        if 0 <= a <= MAX_AGE:
            out[a] = float(r[value_key])
            ages.append(a)
    if hold_last and ages:
        out[max(ages):] = out[max(ages)]
    return out


def _band_to_age(bands: list[tuple[int, int, float]], interpolate: bool) -> np.ndarray:
    """(age_lo, age_hi, value) bands -> array indexed by age. Step function, or linear
    interpolation between band midpoints when `interpolate`."""
    out = np.zeros(MAX_AGE + 1)
    bands = sorted(bands)
    if interpolate:
        mids = [(lo + min(hi, 90)) / 2 for lo, hi, _ in bands]
        vals = [v for _, _, v in bands]
        return np.interp(np.arange(MAX_AGE + 1), mids, vals)
    for lo, hi, v in bands:
        out[max(lo, 0): min(hi, MAX_AGE) + 1] = v
    out[: bands[0][0]] = bands[0][2]
    out[min(bands[-1][1], MAX_AGE):] = bands[-1][2]
    return out


@dataclass(frozen=True)
class Tables:
    mortality: dict[str, np.ndarray]        # sex -> qx[age]
    first_marriage: dict[str, np.ndarray]   # sex -> hazard[age]
    divorce: np.ndarray                     # hazard[duration_years]
    fertility: np.ndarray                   # births per woman per year [age]
    income: dict[str, np.ndarray]           # field -> [age, 5 percentile knots] CAD
    band_edges: np.ndarray                  # upper-exclusive lower edges of bands 1..4
    purchase_hazard: np.ndarray             # [age, income band] annual P(renter buys)
    separation: np.ndarray                  # [age] annual P(start a new job)
    interprovincial: np.ndarray             # [age] annual P(move province)
    emigration: np.ndarray                  # [age] annual P(leave Canada)
    flows: dict[str, tuple[list[str], np.ndarray]]  # origin -> (destinations, shares)
    trait_effects: dict[str, dict[str, float]]      # hazard -> trait -> log hazard ratio per SD

    def tilt(self, hazard: str, traits: dict[str, float]) -> float:
        """Sum of beta x z over the Big Five for one hazard. Zero for every unsourced row."""
        return sum(beta * traits.get(t, 0.0) for t, beta in self.trait_effects.get(hazard, {}).items())

    def income_at(self, field: str, age: int, rank: np.ndarray) -> np.ndarray:
        """Annual income for percentile ranks in (0,1); flat beyond the p10/p90 knots."""
        table = self.income.get(field, self.income["all"])
        return np.interp(rank, PCTL_KNOTS, table[min(age, MAX_AGE)])

    def band_of(self, income: np.ndarray) -> np.ndarray:
        return np.searchsorted(self.band_edges, income, side="right")


@lru_cache(maxsize=2)
def load_tables(data_dir: str) -> Tables:
    d = Path(data_dir)

    mort_rows = _rows(d / "mortality.csv")
    mortality = {
        s: _by_age([r for r in mort_rows if r["sex"] == s], "qx", default=1.0, hold_last=True)
        for s in ("M", "F", "both")
    }
    for qx in mortality.values():
        qx[MAX_AGE] = 1.0

    fm_rows = _rows(d / "first_marriage.csv")
    first_marriage = {
        s: _by_age([r for r in fm_rows if r["sex"] == s], "hazard") for s in ("M", "F", "both")
    }

    div_rows = _rows(d / "divorce.csv")
    divorce = np.zeros(MAX_AGE + 1)
    last = 0
    for r in div_rows:
        k = int(float(r["duration_years"]))
        divorce[k] = float(r["hazard"])
        last = max(last, k)
    divorce[last:] = divorce[last]

    fertility = _by_age(_rows(d / "fertility.csv"), "rate")

    income: dict[str, np.ndarray] = {}
    by_field: dict[str, list[dict[str, str]]] = {}
    for r in _rows(d / "income.csv"):
        by_field.setdefault(r["field"], []).append(r)
    for field, rows in by_field.items():
        cols = []
        for p in ("p10", "p25", "p50", "p75", "p90"):
            bands = [(int(r["age_lo"]), int(r["age_hi"]), float(r[p])) for r in rows]
            cols.append(_band_to_age(bands, interpolate=False))
        income[field] = np.stack(cols, axis=1)
    if "all" not in income:
        raise ValueError("income.csv must contain field=all rows")

    edges = {r["band"]: float(r["lo"]) for r in _rows(d / "income_bands.csv")}
    band_edges = np.array([edges[b] for b in INCOME_BANDS[1:]])

    # Cross-sectional ownership rate H(age, band) -> annual purchase hazard for renters:
    # h(a) = (H(a+1) - H(a)) / (1 - H(a)), floored at zero.
    own_rows = _rows(d / "homeownership.csv")
    purchase = np.zeros((MAX_AGE + 1, len(INCOME_BANDS)))
    for j, band in enumerate(INCOME_BANDS):
        bands = [
            (int(r["age_lo"]), int(r["age_hi"]), float(r["owner_rate"]))
            for r in own_rows
            if r["income_band"] == band
        ]
        H = _band_to_age(bands, interpolate=True)
        h = np.diff(H) / np.clip(1.0 - H[:-1], 1e-6, None)
        purchase[:-1, j] = np.clip(h, 0.0, 1.0)

    # Share of the employed with under a year of tenure = annual rate of starting a new job.
    sep_bands: dict[tuple[int, int], float] = {}
    for r in _rows(d / "job_tenure.csv"):
        key = (int(r["age_lo"]), int(r["age_hi"]))
        sep_bands.setdefault(key, 0.0)
        if float(r["tenure_hi_months"]) <= 12:
            sep_bands[key] += float(r["share"])
    separation = _band_to_age([(lo, hi, v) for (lo, hi), v in sep_bands.items()], interpolate=False)

    mig_rows = [r for r in _rows(d / "migration.csv") if r["field"] == "all"]
    interprovincial = _band_to_age(
        [(int(r["age_lo"]), int(r["age_hi"]), float(r["interprovincial_rate"])) for r in mig_rows],
        interpolate=False,
    )
    emigration = _band_to_age(
        [(int(r["age_lo"]), int(r["age_hi"]), float(r["emigration_rate"])) for r in mig_rows],
        interpolate=False,
    )

    raw_flows: dict[str, list[tuple[str, float]]] = {}
    for r in _rows(d / "interprovincial_flows.csv"):
        raw_flows.setdefault(r["origin"], []).append((r["destination"], float(r["share"])))
    flows = {}
    for origin, pairs in raw_flows.items():
        shares = np.array([s for _, s in pairs])
        flows[origin] = ([dst for dst, _ in pairs], shares / shares.sum())

    # Optional: published personality effect sizes. Only rows that are sourced and were
    # statistically significant in their source are applied (data/PERSONALITY_SOURCES.md).
    trait_effects: dict[str, dict[str, float]] = {}
    effects_path = d / "personality_effects.csv"
    if effects_path.exists():
        for r in _rows(effects_path):
            beta = float(r["beta_per_sd"] or 0)
            if beta and r.get("status") != "unsourced" and r.get("significant", "1") == "1":
                trait_effects.setdefault(r["hazard"], {})[r["trait"]] = beta

    return Tables(
        mortality=mortality,
        first_marriage=first_marriage,
        divorce=divorce,
        fertility=fertility,
        income=income,
        band_edges=band_edges,
        purchase_hazard=purchase,
        separation=separation,
        interprovincial=interprovincial,
        emigration=emigration,
        flows=flows,
        trait_effects=trait_effects,
    )
