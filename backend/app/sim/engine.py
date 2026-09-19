"""Deterministic Monte Carlo over the published transition tables.

No LLM, no ML: numpy draws against hazards read from /data. Same fork state + same assumption
-> same seed -> same futures, every time.

The branch's visible log is the medoid run (the single simulated life that agrees most with
the per-year modal state across all runs), so the story is one coherent life rather than a
stitched average. Per-year solidity is the share of runs that agree with that life's state.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from dataclasses import field as dataclass_field

import numpy as np

from ..models import EMPLOYMENT, HOUSING, INCOME_BANDS, RELATIONSHIP, LifeEvent, StateVector
from .tables import MAX_AGE, Tables

# Rules of thumb, not published statistics. Listed in data/SOURCES.md under "Model assumptions".
RETIREMENT_AGE = 65            # standard OAS / CPP pension age
LEAVE_FAMILY_HOME_AGE = 25
STUDENT_YEARS_REMAINING = 2    # default when the assumption doesn't say
RANK_PERSISTENCE = 0.95        # year-to-year persistence of income rank (normal-score AR(1))
JOB_CHANGE_RANK_SHOCK = 0.35   # extra rank noise in a job-change year
SALARY_RANK_SPREAD = 0.25      # spread (normal-score SD) of runs around a researched starting salary
USD_TO_CAD = 1.37              # one fixed conversion for researched US salaries
HOUSING_RATIO_BOUNDS = (0.25, 2.0)  # clip on the purchase-hazard multiplier 1 / housing_cost_ratio
PEERS_MIN, PEERS_PER_ACTIVITY = 2, 6  # close same-age peers = 2 + 6 x activity_proxy
PARENT_AGE_GAP = 30            # both parents assumed alive at the fork and this much older
BAND_IN_CANADA = 0.25          # each life's hazards are scaled by a factor drawn in 1 +/- this: a national
BAND_ELSEWHERE = 0.50          # average is a loose fit for one person, and looser still outside Canada
LIFE_SCRIPT = {"partner": ("marriage", "divorce", "widowed"), "children": ("birth",), "home": ("home_purchase",)}

PROVINCE_MAIN_CITY = {
    "ON": "Toronto", "QC": "Montréal", "BC": "Vancouver", "AB": "Calgary", "MB": "Winnipeg",
    "SK": "Saskatoon", "NS": "Halifax", "NB": "Moncton", "NL": "St. John's",
    "PE": "Charlottetown", "YT": "Whitehorse", "NT": "Yellowknife", "NU": "Iqaluit",
}
CITY_PROVINCE = {
    **{city.lower(): prov for prov, city in PROVINCE_MAIN_CITY.items()},
    "montreal": "QC", "ottawa": "ON", "waterloo": "ON", "kitchener": "ON", "hamilton": "ON",
    "london": "ON", "mississauga": "ON", "kingston": "ON", "guelph": "ON", "quebec city": "QC",
    "edmonton": "AB", "victoria": "BC", "burnaby": "BC", "kelowna": "BC", "regina": "SK",
    "fredericton": "NB", "st johns": "NL",
}
ABROAD = "abroad"

EVENT_TYPES = [
    "death", "marriage", "divorce", "widowed", "birth", "job_change", "graduation",
    "retirement", "income_up", "income_down", "home_purchase", "leaves_family_home",
    "city_move", "emigration", "peer_wedding", "peer_child", "parent_death",
]
EVENT_DOMAIN = {
    "death": "health", "marriage": "relationship", "divorce": "relationship",
    "widowed": "relationship", "birth": "relationship", "job_change": "career",
    "graduation": "career", "retirement": "career", "income_up": "money",
    "income_down": "money", "home_purchase": "housing", "leaves_family_home": "housing",
    "city_move": "housing", "emigration": "housing", "peer_wedding": "relationship",
    "peer_child": "relationship", "parent_death": "health",
}
EV = {name: i for i, name in enumerate(EVENT_TYPES)}

# State dimensions compared across runs for the medoid and for solidity.
DIMS = ["alive", "place", "employment", "income_band", "relationship", "housing", "children"]
ASPECTS = ["alive", "city", "employment", "income_band", "relationship", "housing", "children"]
CHILD_CAP = 3
CHILD_WORDS = ["no children", "one child", "two children", "three or more children"]
LIKELIHOOD_WORDS = [(0.9, "almost always"), (0.7, "usually"), (0.45, "as often as not"), (0.2, "sometimes")]


def likelihood_words(share: float) -> str:
    return next((words for floor, words in LIKELIHOOD_WORDS if share >= floor), "rarely")


@dataclass
class SimResult:
    seed: int
    runs: int
    years: list[int]
    solidity: list[float]
    states: list[StateVector]
    events: list[list[dict]]       # per year: [{event_type, domain, payload}]
    medoid_run: int
    outlook: list[dict] = dataclass_field(default_factory=list)  # per year: aspect -> {share, words, value}


def seed_for(person_id: str, fork: StateVector, assumption: dict, horizon: int, runs: int,
             personality: dict | None = None, commits: list | None = None, params: dict | None = None) -> int:
    blob = json.dumps(
        [person_id, fork.model_dump(), assumption, horizon, runs, personality, commits or [], params or {}],
        sort_keys=True, default=str,
    )
    return int.from_bytes(hashlib.sha256(blob.encode()).digest()[:8], "big")


def apply_assumption(fork: StateVector, assumption: dict) -> StateVector:
    allowed = {
        "city", "education", "field", "employment", "income_band", "relationship_status",
        "housing",
    }
    patch = {k: v for k, v in assumption.items() if k in allowed and v not in (None, "")}
    return fork.model_copy(update=patch)


def _index(options: list[str], value: str, default: int = 0) -> int:
    return options.index(value) if value in options else default


def simulate(
    tables: Tables,
    person_id: str,
    fork: StateVector,
    assumption: dict,
    sex: str | None,
    horizon: int,
    runs: int,
    personality: dict | None = None,
    commits: list[tuple[int, dict]] | None = None,
    params: dict | None = None,
    script: dict | None = None,
    fit_band: float = 0.0,
) -> SimResult:
    """`commits` are the person's own what-if decisions inside the branch: (calendar year, patch),
    each applied to every run when that year begins. `params` are researched facts about the
    option: salary (CAD), graduates_in, housing_cost_ratio."""
    commits = sorted(commits or [], key=lambda c: c[0])
    params = params or {}
    # The life script (a partner, children, a home) is simulated only where the person's own
    # log or words show it is wanted or already theirs. The bare engine defaults to all of it.
    script = {"partner": True, "children": True, "home": True, **(script or {})}
    seed = seed_for(person_id, fork, assumption, horizon, runs, personality, commits,
                    {**params, "_script": script, "_band": fit_band})
    rng = np.random.default_rng(seed)
    start = apply_assumption(fork, assumption)
    N = runs
    sex_key = sex if sex in ("M", "F") else "both"
    partner_key = {"M": "F", "F": "M"}.get(sex_key, "both")

    # A national average is a loose fit for any one person: each life scales each hazard by its
    # own factor inside the band, so the looseness shows up as spread rather than false precision.
    wobble = 1.0 + (2.0 * rng.random((7, runs)) - 1.0) * fit_band
    fit = dict(zip(("mortality", "marriage", "divorce", "fertility", "job_change", "home_purchase", "migration"), wobble))

    # Big Five z-scores, shrunk toward the mean by how little we trust the estimate, tilt each
    # hazard by exp(sum of published beta x z). With no estimate every multiplier is exactly 1.
    trust = float((personality or {}).get("confidence", 0.0))
    traits = {t: float((personality or {}).get(t, 0.0)) * trust for t in "OCEAN"}
    mult = {h: float(np.exp(tables.tilt(h, traits))) for h in
            ("mortality", "marriage", "divorce", "fertility", "job_change", "home_purchase", "migration")}
    rank_mean = tables.tilt("income_rank", traits)

    # Places a run can be in: where it starts, each province's main city, and abroad.
    # The start city stands in for its own province, so a move back lands there.
    start_prov = CITY_PROVINCE.get(start.city.lower())
    others = [(prov, city) for prov, city in PROVINCE_MAIN_CITY.items() if prov != start_prov]
    committed = list(dict.fromkeys(
        str(patch["city"]) for _, patch in commits if patch.get("city") and patch["city"] != start.city
    ))
    places = [start.city] + committed + [city for _, city in others] + [ABROAD]
    place_prov = ([start_prov] + [CITY_PROVINCE.get(c.lower()) for c in committed]
                  + [prov for prov, _ in others] + [None])
    prov_place: dict[str, int] = {}
    for i, prov in enumerate(place_prov):
        if prov:
            prov_place.setdefault(prov, i)
    in_canada = np.array([p is not None for p in place_prov])
    abroad_idx = len(places) - 1

    alive = np.ones(N, bool)
    place = np.zeros(N, int)
    employment = np.full(N, _index(EMPLOYMENT, start.employment))
    relationship = np.full(N, _index(RELATIONSHIP, start.relationship_status))
    housing = np.full(N, _index(HOUSING, start.housing))
    children = np.full(N, start.children)
    married_for = np.zeros(N, int)
    student_years_left = np.full(
        N, int(params.get("graduates_in") or assumption.get("graduates_in") or STUDENT_YEARS_REMAINING))
    field = start.field
    hazard_ratio = 1.0
    if params.get("housing_cost_ratio"):
        hazard_ratio = float(np.clip(1.0 / float(params["housing_cost_ratio"]), *HOUSING_RATIO_BOUNDS))

    # Income rank: start inside the current band's quintile, then drift as a persistent
    # normal score. The rank is only ever turned into money through the published table.
    band0 = _index(INCOME_BANDS, start.income_band, default=2)
    rank = (band0 + rng.random(N)) / len(INCOME_BANDS)
    z = _norm_ppf(np.clip(rank, 0.01, 0.99))
    salary_noise = rng.standard_normal(N)  # always drawn, so the stream is the same with or without a salary
    if params.get("salary"):
        z, band0 = _rank_from_salary(tables, field, start.age + 1, float(params["salary"]), salary_noise)
    band = np.full(N, band0)
    pending_band = band.copy()

    EMPLOYED, UNEMPLOYED, STUDENT, RETIRED = (EMPLOYMENT.index(k) for k in EMPLOYMENT)
    SINGLE, MARRIED, DIVORCED, WIDOWED = (RELATIONSHIP.index(k) for k in RELATIONSHIP)
    RENTING, OWNING, WITH_FAMILY = (HOUSING.index(k) for k in HOUSING)

    # The people around each run: a few close peers of the same age, and two parents.
    n_peers = int(round(PEERS_MIN + PEERS_PER_ACTIVITY * float(start.activity_proxy)))
    peer_unmarried = np.ones((n_peers, N), bool)
    peer_childless = np.ones((n_peers, N), bool)
    parent_alive = np.ones((2, N), bool)  # mother, father
    parent_lost = np.zeros((horizon, N), dtype=np.int8)  # bit 1 mother, bit 2 father

    S = np.zeros((horizon, N, len(DIMS)), dtype=np.int16)
    E = np.zeros((horizon, N, len(EVENT_TYPES)), dtype=bool)
    moved_to = np.zeros((horizon, N), dtype=np.int16)

    for y in range(horizon):
        age = min(start.age + y + 1, MAX_AGE)
        # Draw every uniform up front, in a fixed order, so the stream never depends on state.
        u = rng.random((9, N))
        shock = rng.standard_normal((2, N))
        dest_u = rng.random(N)
        u_peer = rng.random((2, n_peers, N))
        u_parent = rng.random((2, N))

        # the person's own committed decisions for this year, applied to every run
        for commit_year, patch in commits:
            if commit_year != start.year + y + 1:
                continue
            if patch.get("city"):
                place[alive] = places.index(str(patch["city"]))
                housing[alive & (housing == OWNING)] = RENTING
            if patch.get("employment") in EMPLOYMENT:
                employment[alive] = EMPLOYMENT.index(patch["employment"])
                student_years_left[:] = int(patch.get("graduates_in") or STUDENT_YEARS_REMAINING)
            if patch.get("relationship_status") in RELATIONSHIP:
                relationship[alive] = RELATIONSHIP.index(patch["relationship_status"])
                married_for[alive] = 0
            if patch.get("housing") in HOUSING:
                housing[alive] = HOUSING.index(patch["housing"])
            if patch.get("field"):
                field = str(patch["field"])
            if patch.get("salary"):
                z, fixed = _rank_from_salary(tables, field, age, float(patch["salary"]), shock[1])
                band = np.where(alive, fixed, band)
                pending_band = band.copy()
            elif patch.get("income_band") in INCOME_BANDS:
                fixed = INCOME_BANDS.index(patch["income_band"])
                z = np.where(alive, _norm_ppf(np.full(N, (fixed + 0.5) / len(INCOME_BANDS))), z)
                band = np.where(alive, fixed, band)
                pending_band = band.copy()

        # health
        dies = alive & (u[0] < tables.mortality[sex_key][age] * mult["mortality"] * fit["mortality"])
        E[y, dies, EV["death"]] = True
        alive &= ~dies

        # relationship
        unmarried = alive & (relationship != MARRIED)
        marries = unmarried & script["partner"] & (u[1] < tables.first_marriage[sex_key][age] * mult["marriage"] * fit["marriage"])
        was_married = alive & (relationship == MARRIED) & ~marries
        divorces = was_married & (u[2] < tables.divorce[np.minimum(married_for, MAX_AGE)] * mult["divorce"] * fit["divorce"])
        widowed = was_married & ~divorces & (u[3] < tables.mortality[partner_key][age])
        relationship[marries] = MARRIED
        married_for[marries] = 0
        relationship[divorces] = DIVORCED
        relationship[widowed] = WIDOWED
        married_for[relationship == MARRIED] += 1
        E[y, marries, EV["marriage"]] = True
        E[y, divorces, EV["divorce"]] = True
        E[y, widowed, EV["widowed"]] = True

        births = alive & script["children"] & (u[4] < tables.fertility[age] * mult["fertility"] * fit["fertility"])
        children[births] += 1
        E[y, births, EV["birth"]] = True

        # career
        student_years_left[employment == STUDENT] -= 1
        graduates = alive & (employment == STUDENT) & (student_years_left <= 0)
        employment[graduates] = EMPLOYED
        E[y, graduates, EV["graduation"]] = True

        retires = alive & (employment != RETIRED) & (age >= RETIREMENT_AGE)
        employment[retires] = RETIRED
        E[y, retires, EV["retirement"]] = True

        working = alive & (employment == EMPLOYED) & ~graduates
        changes_job = working & (u[5] < tables.separation[age] * mult["job_change"] * fit["job_change"])
        E[y, changes_job, EV["job_change"]] = True

        # money
        z = rank_mean + RANK_PERSISTENCE * (z - rank_mean) + np.sqrt(1 - RANK_PERSISTENCE**2) * shock[0]
        z = np.where(changes_job, z + JOB_CHANGE_RANK_SHOCK * shock[1], z)
        rank = _norm_cdf(z)
        earning = alive & (employment == EMPLOYED)
        # A band change counts only once it has held for two years running, so one noisy
        # year at a band edge is not reported as a change in fortunes.
        seen_band = np.where(earning, tables.band_of(tables.income_at(field, age, rank)), band)
        new_band = np.where(seen_band == pending_band, seen_band, band)
        pending_band = seen_band
        E[y, earning & (new_band > band), EV["income_up"]] = True
        E[y, earning & (new_band < band), EV["income_down"]] = True
        band = new_band

        # housing
        leaves = alive & (housing == WITH_FAMILY) & (age >= LEAVE_FAMILY_HOME_AGE)
        housing[leaves] = RENTING
        E[y, leaves, EV["leaves_family_home"]] = True
        buys = alive & script["home"] & (housing == RENTING) & ~leaves & (u[6] < tables.purchase_hazard[age, band] * mult["home_purchase"] * hazard_ratio * fit["home_purchase"])
        housing[buys] = OWNING
        E[y, buys, EV["home_purchase"]] = True

        # migration (published rates cover residents of Canada only)
        here = alive & in_canada[place]
        emigrates = here & (u[7] < tables.emigration[age] * mult["migration"] * fit["migration"])
        moves = here & ~emigrates & (u[8] < tables.interprovincial[age] * mult["migration"] * fit["migration"])
        origin_place = place.copy()
        for idx in np.unique(origin_place[moves]):
            origin = place_prov[idx]
            if origin not in tables.flows:
                moves &= origin_place != idx
                continue
            dests, shares = tables.flows[origin]
            sel = moves & (origin_place == idx)
            pick = np.searchsorted(np.cumsum(shares), dest_u[sel], side="right")
            pick = np.minimum(pick, len(dests) - 1)
            place[sel] = np.array([prov_place.get(dests[k], idx) for k in pick])
        place[emigrates] = abroad_idx
        relocated = moves | emigrates
        housing[relocated & ~buys] = RENTING
        E[y, moves, EV["city_move"]] = True
        E[y, emigrates, EV["emigration"]] = True
        moved_to[y] = place

        # the people around them: the same published hazards, applied to peers and parents
        weds = peer_unmarried & (u_peer[0] < tables.first_marriage["both"][age])
        peer_unmarried &= ~weds
        has_child = peer_childless & (u_peer[1] < tables.fertility[age])
        peer_childless &= ~has_child
        E[y, alive & weds.any(axis=0), EV["peer_wedding"]] = True
        E[y, alive & has_child.any(axis=0), EV["peer_child"]] = True
        parent_age = min(age + PARENT_AGE_GAP, MAX_AGE)
        for k, parent_sex in enumerate(("F", "M")):
            lost = parent_alive[k] & (u_parent[k] < tables.mortality[parent_sex][parent_age])
            parent_alive[k] &= ~lost
            parent_lost[y] |= (lost.astype(np.int8) << k)
        E[y, alive & (parent_lost[y] > 0), EV["parent_death"]] = True

        snapshot = np.stack(
            [alive.astype(int), place, employment, band, relationship, housing,
             np.minimum(children, CHILD_CAP)],
            axis=1,
        )
        snapshot[~alive, 1:] = -1
        S[y] = snapshot

    # Medoid: the run that most often matches the per-year modal state.
    offset = S + 1  # shift the -1 "gone" marker to 0 for bincount
    score = np.zeros(N)
    for y in range(horizon):
        for d in range(len(DIMS)):
            col = offset[y, :, d]
            score += col == np.bincount(col).argmax()
    medoid = int(score.argmax())

    years, solidity, states, events, outlook = [], [], [], [], []
    kids = start.children
    for y in range(horizon):
        year = start.year + y + 1
        agree = (S[y] == S[y, medoid]).mean(axis=0)
        row = S[y, medoid]
        is_alive = bool(row[0])
        year_events = []
        for name in EVENT_TYPES:
            if not E[y, medoid, EV[name]]:
                continue
            payload: dict = {}
            if name == "birth":
                kids += 1
                payload = {"children": kids}
            elif name in ("city_move", "emigration"):
                payload = {"to": places[moved_to[y, medoid]]}
            elif name in ("income_up", "income_down"):
                payload = {"income_band": INCOME_BANDS[row[3]]}
            elif name == "parent_death":
                lost_bits = int(parent_lost[y, medoid])
                payload = {"who": " and ".join(w for bit, w in ((1, "mother"), (2, "father")) if lost_bits & bit)}
            year_events.append({"event_type": name, "domain": EVENT_DOMAIN[name], "payload": payload})
        if not is_alive and not year_events:
            break
        years.append(year)
        solidity.append(float(agree.mean()))
        prev = states[-1] if states else start
        states.append(
            StateVector(
                year=year,
                age=start.age + y + 1,
                city=places[row[1]] if is_alive else prev.city,
                education=start.education,
                field=start.field,
                employment=EMPLOYMENT[row[2]] if is_alive else prev.employment,
                income_band=INCOME_BANDS[row[3]] if is_alive else prev.income_band,
                relationship_status=RELATIONSHIP[row[4]] if is_alive else prev.relationship_status,
                housing=HOUSING[row[5]] if is_alive else prev.housing,
                activity_proxy=start.activity_proxy,
                children=kids,
                alive=is_alive,
            )
        )
        events.append(year_events)
        latest = states[-1]
        values = [
            "living" if is_alive else "gone", latest.city, latest.employment, latest.income_band,
            latest.relationship_status, latest.housing, CHILD_WORDS[min(max(int(row[6]), 0), CHILD_CAP)],
        ]
        outlook.append({
            aspect: {"share": round(float(agree[d]), 4), "words": likelihood_words(float(agree[d])), "value": value}
            for d, (aspect, value) in enumerate(zip(ASPECTS, values))
        })
        if not is_alive:
            break

    return SimResult(seed, N, years, solidity, states, events, medoid, outlook)


def _rank_from_salary(tables: Tables, field: str, age: int, salary: float, noise: np.ndarray):
    """Where a known salary sits in the published income distribution for that field and age:
    every run starts near that rank instead of inside a guessed band."""
    table = tables.income.get(field, tables.income["all"])[min(age, MAX_AGE)]
    centre = float(np.interp(salary, table, [0.10, 0.25, 0.50, 0.75, 0.90]))
    z = _norm_ppf(np.full(noise.shape, np.clip(centre, 0.03, 0.97))) + SALARY_RANK_SPREAD * noise
    return z, int(tables.band_of(np.array([salary]))[0])


def to_life_events(result: SimResult, person_id: str, branch_id: str, revision: int = 0,
                   commits: list[dict] | None = None) -> list[list[LifeEvent]]:
    """Simulated events as LifeEvents, with stable ids and LLM-free text. A commit shows up in
    its year as the person's own decision, ahead of what the simulator made of it."""
    out = []
    for year, sol, year_events in zip(result.years, result.solidity, result.events):
        decided = [
            {"event_type": "commit", "domain": "career", "text": c["message"],
             "payload": {"commit_id": c["id"], **c.get("patch", {})}}
            for c in (commits or []) if c["year"] == year
        ]
        row = []
        for ev in decided + year_events:
            key = f"{person_id}|{branch_id}|r{revision}|{year}|{ev['event_type']}|{ev['payload'].get('commit_id', '')}"
            h = hashlib.sha1(key.encode()).digest()
            row.append(
                LifeEvent(
                    id=h.hex()[:16],
                    person_id=person_id,
                    source="simulated",
                    branch_id=branch_id,
                    date=f"{year}-{h[0] % 12 + 1:02d}-{h[1] % 28 + 1:02d}",
                    domain=ev["domain"],
                    event_type=ev["event_type"],
                    payload={**ev["payload"], "revision": revision},
                    confidence=round(sol, 4),
                    text=ev.get("text") or plain_text(ev["event_type"], ev["payload"]),
                )
            )
        out.append(row)
    return out


PLAIN_LABELS = {"peer_wedding": "a close friend's wedding", "peer_child": "a close friend's first child",
                "parent_death": "a parent dies"}


def plain_text(event_type: str, payload: dict) -> str:
    """The raw structured rendering shown when narration is off or hasn't arrived."""
    label = PLAIN_LABELS.get(event_type, event_type.replace("_", " "))
    detail = payload.get("to") or payload.get("who") or payload.get("income_band", "").replace("_", " ")
    return f"{label} — {detail}" if detail else label


def _norm_cdf(x: np.ndarray) -> np.ndarray:
    # Abramowitz-Stegun 26.2.17; numpy has no erf and the spec rules out scipy.
    t = 1.0 / (1.0 + 0.2316419 * np.abs(x))
    poly = t * (0.319381530 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))))
    tail = np.exp(-0.5 * x * x) / np.sqrt(2 * np.pi) * poly
    return np.where(x >= 0, 1.0 - tail, tail)


def _norm_ppf(p: np.ndarray) -> np.ndarray:
    # Inverse by interpolation over the same approximation, so cdf(ppf(p)) round-trips.
    grid = np.linspace(-4, 4, 1601)
    return np.interp(p, _norm_cdf(grid), grid)
