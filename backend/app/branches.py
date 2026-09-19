"""A branch's life cycle: made from an option the person described, simulated, re-simulated
when research lands or when they commit (or undo) a what-if inside it.

The fork state is frozen on the branch when it is created, so every re-simulation starts from
the same present and the same inputs always give back the same future — which is what makes
undo exact.
"""

from __future__ import annotations

import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from hashlib import sha1
from typing import Optional

from . import config, db, evidence, llm
from .models import Branch, BranchView, BranchYear, Commit, Horizon, LifeEvent, Option, Person, StateVector
from .outcome_model import choice_label, ensure_head, model_patch, normalize, public_model, resolve_terms
from .sim.engine import BAND_ELSEWHERE, BAND_IN_CANADA, CITY_PROVINCE, USD_TO_CAD, simulate, to_life_events
from .sim.outcomes import BIG_DEFAULT_YEARS, MAX_STEPS, window_from_days, describe, measures, simulate_outcomes, step_dates, step_labels, step_offsets
from .sim.tables import load_tables
from .store import get_store

STATE_FIELDS = ("city", "education", "field", "employment", "income_band", "relationship_status", "housing")
WORLD_CITIES = ["San Francisco", "New York", "Seattle", "Boston", "Los Angeles", "Austin", "Chicago",
                "London", "Berlin", "Paris", "Singapore", "Tokyo", "Sydney", "Dublin", "Amsterdam"]
SALARY_RE = re.compile(r"(?:(US|CA|C)?\$\s?)(\d{2,3})(?:[,.]?(\d{3})|\s?k)\b|\b(\d{2,3})\s?k\b", re.I)
STUDY_RE = re.compile(r"\b(master'?s?|mmath|msc|m\.sc|mba|phd|ph\.d|doctorate|grad(?:uate)? school|degree|bootcamp)\b", re.I)
WORK_RE = re.compile(r"\b(offer|job|role|position|work(?:ing)? (?:at|for)|join|startup|company|hired)\b", re.I)

# Which background events give way to the option's own events (same part of life, same step), and
# which are kept first when background has to be trimmed.
DOMAIN_FAMILY = {"work": "career", "career": "career", "learning": "career", "money": "money", "home": "housing",
                 "housing": "housing", "love": "relationship", "relationship": "relationship", "family": "relationship"}
ALWAYS_SHOWN = {"death", "parent_death"}
BACKGROUND_PRIORITY = {"death": 0, "parent_death": 1, "retirement": 2, "graduation": 2, "marriage": 3, "birth": 3,
                       "home_purchase": 3, "divorce": 3, "widowed": 3, "emigration": 4, "city_move": 4,
                       "peer_wedding": 5, "peer_child": 5, "job_change": 6, "income_up": 7, "income_down": 7}

# One worker, so indexing is strictly ordered and `flush` really is a drain.
_io = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hereafter-io")


def flush() -> None:
    """Wait until every queued index write has landed (used by /erase, so nothing is written after the burn)."""
    _io.submit(lambda: None).result(timeout=600)
# Research lands in the background while the person may be committing: one writer at a time.
lock = threading.RLock()


def _known_cities() -> list[str]:
    return [c.title() for c in CITY_PROVINCE] + WORLD_CITIES


def rules_assumption(text: str) -> dict:
    """LLM-off fallback: the few things plain pattern matching can safely read."""
    found: dict = {}
    lowered = text.lower()
    for city in sorted(_known_cities(), key=len, reverse=True):
        if re.search(rf"\b{re.escape(city.lower())}\b", lowered):
            found["city"] = "Montréal" if city.lower() == "montreal" else city
            break
    if STUDY_RE.search(text):
        found["employment"] = "student"
        years = re.search(r"(\d|one|two|three|four)[- ]year", lowered)
        if years:
            found["graduates_in"] = {"one": 1, "two": 2, "three": 3, "four": 4}.get(years.group(1)) or int(years.group(1))
    elif WORK_RE.search(text):
        found["employment"] = "employed"
    m = SALARY_RE.search(text)
    if m:
        found["salary"] = float(f"{m.group(2)}{m.group(3)}") if m.group(3) else float(m.group(2) or m.group(4)) * 1000
        if (m.group(1) or "").upper() == "US" or "usd" in lowered:
            found["currency"] = "USD"
    return found


def in_canada(city: Optional[str]) -> bool:
    return bool(city) and city.lower() in CITY_PROVINCE


def to_cad(amount: float, currency: Optional[str], city: Optional[str]) -> float:
    is_usd = currency == "USD" or (currency is None and city is not None and not in_canada(city))
    return amount * USD_TO_CAD if is_usd else amount


def assumption_from_option(situation: str, option: Option) -> tuple[dict, dict]:
    """(assumption, params). Extraction only: what the person wrote, in structured form."""
    parsed = llm.extract_assumption(situation, option.title, option.details, date.today().isoformat())
    raw = parsed.model_dump(exclude_none=True) if parsed else rules_assumption(f"{option.title}. {option.details}")
    if (raw.get("institution") or raw.get("program")) and not raw.get("employment"):
        raw["employment"] = "student"  # naming a school or a program is enrolling in it
    params: dict = {}
    if raw.get("salary"):
        params["salary"] = round(to_cad(float(raw["salary"]), raw.get("currency"), raw.get("city")))
        params["salary_source"] = "the offer as you described it"
    if raw.get("graduates_in"):
        params["graduates_in"] = int(raw["graduates_in"])
    return raw, params


def is_long(span: Horizon) -> bool:
    """A year or more is in play: worth researching pay, rent and program facts for the narrative."""
    return span.unit == "years" or (span.unit == "months" and span.count >= 12)


def has_background(span: Horizon) -> bool:
    """The life-table background runs underneath long horizons only, and only when switched on
    (HEREAFTER_BACKGROUND=on). It is off by default: people found it noise."""
    return config.BACKGROUND and is_long(span)


def _steps(branch: Branch) -> tuple[list[date], list[str]]:
    start = date.fromisoformat(branch.forked_at)
    dates = step_dates(branch.span.unit, branch.span.count, start)
    return dates, step_labels(branch.span.unit, dates, branch.span.tonight)


def step_of(branch: Branch, at: Optional[str], year: Optional[int]) -> Optional[int]:
    """The step a commit lands on: the last step beginning on or before `at`, or the first in `year`."""
    dates, _ = _steps(branch)
    if at:
        day = date.fromisoformat(at[:10])
        hits = [i for i, d in enumerate(dates) if d <= day]
        return hits[-1] if hits and day <= dates[-1] + timedelta(days=366) else None
    hits = [i for i, d in enumerate(dates) if d.year == year]
    return hits[0] if hits else None


def _event_id(person_id: str, branch: Branch, which: str, step: int, key: str) -> str:
    return sha1(f"{person_id}|{branch.id}|r{branch.revision}|{which}|{step}|{key}".encode()).hexdigest()[:16]


def _life(person: Person, branch: Branch, which: str, run: int, outcome, background, dates, labels) -> list[BranchYear]:
    """One simulated life as dated steps: the person's commits, the option's own events, and
    (on long horizons) the life-course background underneath."""
    by_key = {e["key"]: e for e in branch.model.get("events", [])}
    fork = StateVector(**branch.fork)
    bg_events = to_life_events(background, person.id, branch.id, branch.revision) if background else []
    start = dates[0]
    rank = {k: i for i, k in enumerate(_story_order(branch.model.get("events", [])))}
    fired = outcome.life(run)
    horizon_ends = start + timedelta(days=step_offsets(branch.span.unit, branch.span.count, start)[-1])
    happened_on: dict[str, date] = {}

    def dated(e: dict, s: int) -> date:
        """The day this moment falls on: inside its step AND inside its own window of days, fixed by a
        hash so it never moves, and never before whatever it follows."""
        lo = max(dates[s], start + timedelta(days=(e.get("days") or [0, 0])[0])) if e.get("days") else dates[s]
        hi = min((dates[s + 1] if s + 1 < len(dates) else horizon_ends) - timedelta(days=1),
                 start + timedelta(days=e["days"][1]) if e.get("days") else date.max)
        lo = min(lo, max(hi, dates[s]))
        spread = max(0, (hi - lo).days)
        pick = int(sha1(f"{branch.id}|{e['key']}|{s}".encode()).hexdigest()[:8], 16) % (spread + 1)
        day = lo + timedelta(days=pick)
        for k in [*(e.get("requires") or []), *(e.get("after") or [])]:
            if k in happened_on:
                day = max(day, happened_on[k])
        happened_on.setdefault(e["key"], day)
        return day
    outlooks = outcome.outlook(run)
    years = []
    for s, (at, label) in enumerate(zip(dates, labels)):
        y = int((at - start).days // 365.25)  # which background year this step falls in
        if background and y >= len(background.years):
            break  # the background life ended
        until = dates[s + 1] if s + 1 < len(dates) else None
        events = [
            LifeEvent(id=_event_id(person.id, branch, which, s, f"commit:{c.id}"), person_id=person.id,
                      source="simulated", branch_id=branch.id, date=at.isoformat(), domain="growth",
                      event_type="commit", payload={"commit_id": c.id, "revision": branch.revision},
                      confidence=1.0, text=c.message)
            for c in branch.commits if c.patch.get("step") == s
        ]
        own = []
        for key in sorted(fired[s], key=lambda k: rank.get(k, 99)):  # causes before their consequences, the choice first
            e = by_key[key]
            if e["kind"] == "recurring" and s and key in fired[s - 1]:
                continue  # a recurring thing is shown when it starts up again, not every step it lasts
            own.append(LifeEvent(
                id=_event_id(person.id, branch, which, s, key), person_id=person.id, source="simulated",
                branch_id=branch.id, date=dated(e, s).isoformat(), domain=e["domain"], event_type=key,
                payload={"basis": e["basis"], "evidence_id": e.get("evidence_id"), "revision": branch.revision,
                         **({"head": True} if e.get("head") else {})},
                confidence=round(float(outcome.shares[s, outcome.keys.index(key)]), 4), text=e["label"],
            ))
        heads = [e for e in own if e.payload.get("head")]
        rest = sorted((e for e in own if not e.payload.get("head")), key=lambda e: (e.date, rank.get(e.event_type, 99)))
        events = heads + events + rest  # step zero, then the person's own commits, then what follows, in date order
        outlook = dict(outlooks[s])
        solidity = outcome.solidity[s]
        state = fork.model_copy(update={"year": at.year, "age": fork.age + (at.year - fork.year)})
        if background:
            own_families = {DOMAIN_FAMILY.get(e.domain, e.domain) for e in events if e.event_type != "commit"}
            for ev in bg_events[y]:
                # a background year's events land on the step that covers their own month of that year
                lands = start + timedelta(days=365.25 * y + 30.4 * (int(ev.date[5:7]) - 1))
                if lands < at or (until is not None and lands >= until):
                    continue
                ev = ev.model_copy(update={"date": at.isoformat()})
                # the person's own decision is the plot: where it already speaks to this part of
                # life in this step, the national-average version of the same thing stays out
                if ev.event_type not in ALWAYS_SHOWN and DOMAIN_FAMILY.get(ev.domain, ev.domain) in own_families:
                    continue
                ev.payload.update({"basis": "background", "evidence_id": evidence.statistic_id(branch, ev.event_type)})
                events.append(ev)
            outlook.update(background.outlook[y])
            solidity = (solidity + background.solidity[y]) / 2 if outcome.keys else background.solidity[y]
            state = background.states[y]
        # An open clarifying question means the ranges themselves are less certain. Agreement between
        # runs cannot show that, so the line is drawn fainter by the same amount the ranges were widened.
        solidity *= 1.0 - float(branch.model.get("widen", 0.0))
        years.append(BranchYear(year=at.year, at=at.isoformat(), label=label, solidity=round(solidity, 4),
                                state=state, events=events, outlook=outlook))
    return _cap_background(years)


def _story_order(events: list[dict]) -> list[str]:
    """Keys in the order a story tells them: the choice, then each event after what it follows or requires."""
    by_key = {e["key"]: e for e in events}
    out: list[str] = []

    def visit(key: str, trail: tuple = ()) -> None:
        if key in out or key in trail or key not in by_key:
            return
        for k in [*(by_key[key].get("requires") or []), *(by_key[key].get("after") or [])]:
            visit(k, trail + (key,))
        out.append(key)

    for e in sorted(events, key=lambda e: (not e.get("head"), e["window"][0], e["window"][1], e["key"])):
        visit(e["key"])
    return out


def _cap_background(years: list[BranchYear]) -> list[BranchYear]:
    """Background is weather, not plot: at most about a quarter of a branch's visible events.
    (A branch with no outcome model of its own is all background and is left alone.)"""
    own = sum(1 for y in years for e in y.events if e.payload.get("basis") != "background")
    if own == 0:
        return years
    allowed = max(2, -(-own // 3))
    ranked = sorted(((BACKGROUND_PRIORITY.get(e.event_type, 9), i, e.id) for i, y in enumerate(years)
                     for e in y.events if e.payload.get("basis") == "background"))
    keep = {eid for _, _, eid in ranked[:allowed]}
    for y in years:
        y.events = [e for e in y.events if e.payload.get("basis") != "background" or e.id in keep]
    return years


def resimulate(person: Person, branch: Branch) -> BranchView:
    dates, labels = _steps(branch)
    patches = [{"step": c.patch.get("step", 0), **c.patch.get("model", {})} for c in branch.commits]
    events = ensure_head(normalize(branch.model.get("events", [])), choice_label(branch.label))
    resolve_terms(events, load_tables(str(config.DATA_DIR)).trait_effects)
    widen = branch.model.get("widen", 0.0)
    offsets = step_offsets(branch.span.unit, branch.span.count, dates[0])
    durations = [float(b - a) for a, b in zip(offsets, offsets[1:])]
    outcome = simulate_outcomes(person.id, events, len(dates), config.SIM_RUNS, patches, widen, person.personality, durations)
    describe(events, outcome, person.personality, widen)
    branch.measures = measures(outcome, events, offsets, [d.isoformat() for d in dates],
                               (person.money or {}).get("currency"), person.money)
    events.sort(key=lambda e: (-e["probability"], e["key"]))  # most likely first
    branch.model = {**public_model(events), "widen": widen, "life_script": branch.model.get("life_script", {})}

    background = None
    if has_background(branch.span):
        tables = load_tables(str(config.DATA_DIR))
        engine_year = lambda step: branch.fork["year"] + int((dates[step] - dates[0]).days // 365.25) + 1
        commits = [(engine_year(c.patch.get("step", 0)), {k: v for k, v in c.patch.items() if k not in ("model", "step")})
                   for c in branch.commits]
        sim_params = {k: v for k, v in branch.params.items() if k in ("salary", "graduates_in", "housing_cost_ratio")}
        assumption = {k: v for k, v in branch.assumption.items() if k in STATE_FIELDS or k == "graduates_in"}
        here = branch.assumption.get("city") or branch.fork.get("city")
        background = simulate(tables, person.id, StateVector(**branch.fork), assumption, person.sex,
                              max(1, -(-offsets[-1] // 366)),
                              config.SIM_RUNS, person.personality, commits, sim_params,
                              script={k: bool(branch.model.get("life_script", {}).get(k)) for k in ("partner", "children", "home")},
                              fit_band=BAND_IN_CANADA if in_canada(here) else BAND_ELSEWHERE)

    years = _life(person, branch, "typical", outcome.typical, outcome, background, dates, labels)
    rare = _life(person, branch, "rare", outcome.rare, outcome, background, dates, labels)
    db.save_branch(branch, years, rare)

    def index() -> None:
        store = get_store()
        store.append([e for y in years for e in y.events])
        store.add_evidence(evidence.statistic_evidence(branch, years))
        store.index_runs(branch, outcome, [d.isoformat() for d in dates])

    if get_store().kind == "local":
        index()
    else:
        _io.submit(index)
    return BranchView(branch=branch, years=years)


def create_branch(person: Person, fork: StateVector, label: str, assumption: dict, precondition: Optional[str],
                  horizon: Optional[int] = None, *, scenario_id: Optional[str] = None,
                  option_id: Optional[str] = None, params: Optional[dict] = None, research: str = "none",
                  span: Optional[Horizon] = None, events: Optional[list[dict]] = None, widen: float = 0.0,
                  extra_evidence=None, script: Optional[dict] = None, forked_at: Optional[str] = None) -> BranchView:
    span = span or Horizon(unit="years", count=min(horizon or BIG_DEFAULT_YEARS, MAX_STEPS["years"]))
    branch = Branch(
        id=uuid.uuid4().hex[:12], person_id=person.id, label=label, forked_at=forked_at or date.today().isoformat(),
        assumption=assumption, precondition=precondition, scenario_id=scenario_id, option_id=option_id,
        params=params or {}, research=research, fork=fork.model_dump(), horizon=span.count, span=span,
        model={"events": events or [], "widen": widen, "life_script": script or {}},
    )
    if extra_evidence:  # e.g. the person's own track record, which may re-base some events before the first run
        get_store().add_evidence(extra_evidence(branch.id))
    return resimulate(person, branch)


OLD_STEP_DAYS = {"days": 1, "weeks": 7, "months": 30.4375, "years": 365.25}


def _to_new_layout(branch: Branch) -> None:
    """A branch made before steps were graded and step zero was the choice: keep what could happen,
    re-express each window in days, and lay it out again on a horizon that makes sense (no forty-year paths)."""
    from .outcome_model import clamp

    per = OLD_STEP_DAYS[branch.span.unit]
    events = [e for e in (branch.model or {}).get("events", []) if not e.get("head")]
    for e in events:
        lo, hi = e.get("window") or [0, 0]
        e.setdefault("days", [int(lo * per), int((hi + 1) * per) - 1])
    branch.span = clamp(Horizon(unit=branch.span.unit, count=min(branch.span.count, BIG_DEFAULT_YEARS)
                                if branch.span.unit == "years" and branch.span.count > 5 else branch.span.count))
    branch.horizon = branch.span.count
    offsets = step_offsets(branch.span.unit, branch.span.count, date.fromisoformat(branch.forked_at))
    events = [e for e in events if e["days"][0] < offsets[-1]]
    for e in events:
        e["window"] = window_from_days(offsets, *e["days"])
    branch.model = {**(branch.model or {}), "events": events}
    kept = []
    for c in branch.commits:
        step = step_of(branch, c.at or None, c.year)
        if step is not None:
            c.patch["step"] = step
            kept.append(c)
    branch.commits = kept


def migrate() -> int:
    """Branches simulated under an older model are laid out and simulated again, once. Main is never touched."""
    from .outcome_model import LAYOUT

    rows = db.conn().execute("SELECT id, person_id FROM branches").fetchall()
    done = 0
    for row in rows:
        with lock:
            branch, _ = db.get_branch(row["id"])
            person = db.get_person(row["person_id"])
            model = branch.model or {}
            current = model.get("layout") == LAYOUT and all("breakdown" in e for e in model.get("events", []))
            if branch.forming or person is None or current:
                continue
            if model.get("layout") != LAYOUT:
                _to_new_layout(branch)
            branch.revision += 1
            resimulate(person, branch)
            done += 1
    return done


def view(branch_id: str) -> BranchView:
    branch, years = db.get_branch(branch_id)
    return BranchView(branch=branch, years=years)


def add_commit(person: Person, branch: Branch, step: int, message: str, event_key: Optional[str] = None) -> BranchView:
    """One more step on the path you are on. Either the person's own words (structure is extracted),
    or `event_key`: "assume this possibility happens" — that event is forced, no LLM involved."""
    dates, _ = _steps(branch)
    if event_key:
        event = next(e for e in branch.model["events"] if e["key"] == event_key)
        step = max(step, event["window"][0])  # not before its own moment can come
        message = f"{event['label']} happens"
        patch: dict = {"step": step, "event_key": event_key, "model": {"force": [event_key], "prevent": [], "likelier": [], "less_likely": []}}
    else:
        patch = {"step": step, "model": model_patch(message, branch.model.get("events", []))}
    if has_background(branch.span) and not event_key:  # a what-if may also change the life-course underneath
        parsed = llm.extract_patch(branch.label, dates[step].year, message)
        background = parsed.model_dump(exclude_none=True) if parsed else rules_assumption(message)
        if background.get("salary"):
            background["salary"] = round(to_cad(float(background["salary"]), background.get("currency"), background.get("city")))
        background.pop("currency", None)
        patch.update(background)
    branch.commits.append(Commit(id=uuid.uuid4().hex[:10], branch_id=branch.id, year=dates[step].year,
                                 at=dates[step].isoformat(), message=message, patch=patch,
                                 created_at=datetime.now().isoformat(timespec="seconds")))
    branch.revision += 1
    return resimulate(person, branch)


def undo_commit(person: Person, branch: Branch, commit_id: Optional[str]) -> BranchView:
    target = commit_id or (branch.commits[-1].id if branch.commits else None)
    branch.commits = [c for c in branch.commits if c.id != target]
    branch.revision += 1
    return resimulate(person, branch)
