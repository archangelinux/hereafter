"""A scenario: something the person is deliberating, its options, and the branches they become.

One sentence and the option names are enough. Hereafter fills in from what main already says
(a logged hybrid search), then from live research, and only then asks — at most three questions,
never blocking. While a question is open the affected branches are simply simulated wider.
"""

from __future__ import annotations

import logging
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from hashlib import sha1
from typing import Optional

from . import branches as branch_ops
from . import config, db, llm, outcome_model
from .models import Branch, Evidence, Horizon, LifeEvent, Option, Person, Question, ResearchStep, Scenario, StateVector
from .sim.outcomes import UNANSWERED_WIDEN
from .store import get_store

log = logging.getLogger("hereafter.scenarios")
MIN_TRACK_RECORD = 5
TRACK_RECORD_BAND = 0.10


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{3,}", text.lower()))


def same_question(a: str, b: str) -> bool:
    ta, tb = _tokens(a), _tokens(b)
    return bool(ta and tb) and len(ta & tb) / len(ta | tb) >= 0.6


def known_from_main(person: Person, situation: str, options: list[Option]) -> tuple[str, list[LifeEvent]]:
    """What the log already says that bears on this decision — looked up before anything is asked."""
    store = get_store()
    probe = situation + " " + " ".join(f"{o.title} {o.details}" for o in options)
    found = {e.id: e for e in store.hybrid_search(person.id, probe[:600], size=8)}
    answers = [e for e in store.events(person.id) if e.event_type == "answer"]
    found.update({e.id: e for e in answers})
    events = sorted(found.values(), key=lambda e: e.date)
    return "\n".join(f"- {e.date[:10]}: {e.text}" for e in events), events


def _questions(scenario: Scenario, proposed, answered: list[LifeEvent]) -> list[Question]:
    """At most three, and never one main can already answer."""
    out = []
    for q in (proposed.questions if proposed else [])[:3]:
        if any(same_question(q.text, a.payload.get("question", "")) for a in answered):
            continue
        ids = [scenario.options[i].id for i in q.applies_to_options if 0 <= i < len(scenario.options)]
        out.append(Question(id=uuid.uuid4().hex[:8], scenario_id=scenario.id, text=q.text.strip(), why=q.why.strip(),
                            choices=[c.strip() for c in q.choices[:5]], applies_to=ids))
    return out


def _widen(scenario: Scenario, option_id: str) -> float:
    open_here = [q for q in scenario.questions if q.answer is None and (not q.applies_to or option_id in q.applies_to)]
    return UNANSWERED_WIDEN * min(len(open_here), 2)


def _track_record(person: Person, branch_id: str, events: list[dict]) -> list[Evidence]:
    """A personal reference class: how often this person has kept the commitments in their own
    log. Used only when there are enough of them to mean something."""
    kept, total = get_store().track_record(person.id)
    if total < MIN_TRACK_RECORD:
        return []
    from .sim.engine import likelihood_words

    share = kept / total
    evidence_id = "ev_" + sha1(f"{branch_id}|track".encode()).hexdigest()[:14]
    touched = False
    for e in events:
        if e.get("follow_through") and e["basis"] == "estimated":
            e.update({"basis": "personal", "probability": round(min(max(share, 0.02), 0.98), 4),
                      "band": TRACK_RECORD_BAND, "evidence_id": evidence_id, "words": likelihood_words(share)})
            touched = True
    if not touched:
        return []
    return [Evidence(id=evidence_id, person_id=person.id, branch_id=branch_id, kind="personal",
                     claim=f"Of {total} commitments recorded in your own log, {kept} were later marked kept.",
                     value=f"{kept} of {total}", source_title="your own track record", retrieved_at=date.today().isoformat(),
                     reference_class="commitments you set yourself, from your log",
                     gap="Past commitments were about other things; this only says how you have tended to follow through.",
                     used_for="likelihood of the events on this path that are you keeping your own commitment")]


SCRIPT_PROBES = {
    "partner": ("partner girlfriend boyfriend wife husband married engaged dating relationship wedding of my own",
                r"\b(my (partner|girlfriend|boyfriend|wife|husband|fianc\w+)|we got (married|engaged)|want to (get married|settle down|find (a|someone)))"),
    "children": ("children kids baby pregnant want a family of my own",
                 r"\b(my (son|daughter|kids?|child(ren)?|baby)|want (kids|children|a family)|pregnan\w+|trying for a baby)"),
    "home": ("buy a home house condo mortgage down payment saving to own",
             r"\b(down ?payment|mortgage|(buy|buying|bought|own|owning) (a |our |my )?(home|house|condo|place)|saving for a (home|house|place))"),
}


def life_script(person: Person, fork: StateVector, text: str) -> tuple[dict, str]:
    """Marriage, children and buying a home appear on a branch only if the person's own log or
    words show they are wanted or already theirs. Retrieval, then extraction; default is no."""
    store = get_store()
    found: dict[str, LifeEvent] = {}
    for probe, _ in SCRIPT_PROBES.values():
        found.update({e.id: e for e in store.hybrid_search(person.id, probe, size=4)})
    excerpts = "\n".join(f"- {e.text}" for e in found.values() if e.event_type not in ("breadcrumb", "social_connectedness"))
    parsed = llm.extract_life_script(text, excerpts)
    if parsed is not None:
        script, because = {"partner": parsed.partner, "children": parsed.children, "home": parsed.home}, parsed.because
    else:
        haystack = f"{text}\n{excerpts}".lower()
        script = {k: bool(re.search(pattern, haystack)) for k, (_, pattern) in SCRIPT_PROBES.items()}
        because = "matched their own words" if any(script.values()) else "nothing in their log or words"
    script["partner"] = script["partner"] or fork.relationship_status == "married"
    script["children"] = script["children"] or fork.children > 0
    script["home"] = script["home"] or fork.housing == "owning"
    return script, because


def _about(fork: StateVector, assumed) -> str:
    about = (f"age {fork.age}, lives in {fork.city}, {fork.employment}, {fork.relationship_status}, "
             f"{fork.housing.replace('_', ' ')}")
    if assumed:
        about += f". They are deliberating this ASSUMING they have already chosen: {assumed.label}"
    return about


def propose(person: Person, fork: StateVector, scenario: Scenario, fixed: Optional[Horizon], assumed=None):
    known, events = known_from_main(person, scenario.situation, scenario.options)
    proposed = llm.propose_scenario_model(
        scenario.situation, [{"title": o.title, "details": o.details} for o in scenario.options],
        fixed.model_dump() if fixed else None, _about(fork, assumed), known,
    )
    if proposed is None:
        horizon = outcome_model.clamp(fixed or outcome_model.rules_horizon(scenario.situation, scenario.options))
        return horizon, [[] for _ in scenario.options], [], len(events)
    horizon = outcome_model.clamp(fixed or Horizon(unit=proposed.horizon_unit, count=proposed.horizon_count,
                                                   tonight=proposed.starts_tonight))
    by_index = {o.option_index: o for o in proposed.options}
    models = [outcome_model.from_proposal(by_index[i], horizon.count) if i in by_index else []
              for i in range(len(scenario.options))]
    answered = [e for e in events if e.event_type == "answer"]
    return horizon, models, _questions(scenario, proposed, answered), len(events)


def _say(branch_id: str, state: str, message: str) -> None:
    db.add_research_step(branch_id, ResearchStep(at=datetime.now().isoformat(timespec="seconds"), state=state, message=message))


def _branches_of(scenario: Scenario) -> dict[str, Branch]:
    return {b.option_id: b for b, _ in db.list_branches(scenario.person_id) if b.scenario_id == scenario.id}


def create(person: Person, fork: StateVector, situation: str, options: list[Option], fixed: Optional[Horizon],
           assuming_branch_id: Optional[str] = None) -> tuple[Scenario, list]:
    """Returns at once: the scenario and one placeholder branch per option, still forming.
    `form` (a background task) does the imagining, the first simulation and the research."""
    scenario = Scenario(id=uuid.uuid4().hex[:12], person_id=person.id, situation=situation,
                        created_at=datetime.now().isoformat(timespec="seconds"), options=options,
                        assuming_branch_id=assuming_branch_id,
                        horizon=outcome_model.clamp(fixed or outcome_model.rules_horizon(situation, options)))
    if assuming_branch_id:
        found = db.get_branch(assuming_branch_id)
        if found and found[0].person_id == person.id and found[1]:
            fork = found[1][0].state  # fork from that branch's simulated state, not from now
    views = []
    for option in options:
        branch = Branch(id=uuid.uuid4().hex[:12], person_id=person.id, label=option.title,
                        forked_at=date.today().isoformat(), scenario_id=scenario.id, option_id=option.id,
                        precondition=f"decide_by: {option.deadline}" if option.deadline else None,
                        research="pending", forming=True, model=None, fork=fork.model_dump(),
                        span=scenario.horizon, horizon=scenario.horizon.count)
        db.save_branch(branch, [])
        _say(branch.id, "searching", f"Imagining what could happen if you choose: {option.title}…")
        scenario.branch_ids.append(branch.id)
        views.append(branch_ops.view(branch.id))
    db.save_scenario(scenario)
    return scenario, views


def _shape(person: Person, scenario: Scenario, fixed: Optional[Horizon], only: Optional[set[str]] = None) -> list[str]:
    """Propose -> per-option models -> first (or next) simulation. Returns the branch ids it rebuilt."""
    mine = _branches_of(scenario)
    first = next(iter(mine.values()))
    fork = StateVector(**first.fork)
    assumed = db.get_branch(scenario.assuming_branch_id)[0] if scenario.assuming_branch_id and db.get_branch(scenario.assuming_branch_id) else None
    horizon, models, questions, looked_at = propose(person, fork, scenario, fixed, assumed)
    if only is None:  # first forming: the horizon and the questions are settled here
        scenario.horizon, scenario.questions = horizon, questions
        db.save_scenario(scenario)
    background = branch_ops.has_background(scenario.horizon)
    text = scenario.situation + " " + " ".join(f"{o.title} {o.details}" for o in scenario.options)
    with ThreadPoolExecutor(max_workers=4) as pool:  # the remaining extraction calls, side by side
        script_job = pool.submit(life_script, person, fork, text) if background else None
        read = list(pool.map(lambda o: branch_ops.assumption_from_option(scenario.situation, o) if background else ({}, {}),
                             scenario.options))
    script, because = script_job.result() if script_job else ({}, "")

    rebuilt = []
    for option, events, (assumption, params) in zip(scenario.options, models, read):
        with branch_ops.lock:
            branch = _branches_of(scenario).get(option.id)
            if branch is None or branch.status != "open":
                continue
            widen = _widen(scenario, option.id)
            if only is not None and option.id not in only:  # untouched by the answers: only its ranges tighten
                branch.model = {**(branch.model or {"events": []}), "widen": widen}
            else:
                if assumed and background:
                    assumption = {**{k: v for k, v in assumed.assumption.items() if k in branch_ops.STATE_FIELDS}, **assumption}
                deadline = option.deadline or assumption.get("deadline")
                branch.assumption, branch.params = assumption, {**params, **{k: v for k, v in branch.params.items() if k not in params}}
                branch.precondition = f"decide_by: {deadline}" if deadline else None
                branch.span, branch.horizon = scenario.horizon, scenario.horizon.count
                branch.model = {**outcome_model.public_model(events), "widen": widen, "life_script": script}
                get_store().add_evidence(_track_record(person, branch.id, events))
                rebuilt.append(branch.id)
            branch.forming = False
            branch.revision += 1
            branch_ops.resimulate(person, branch)
        if branch.id in rebuilt:
            _say(branch.id, "found" if looked_at else "skipped",
                 f"Looked in your own log first: {looked_at} thing{'s' if looked_at != 1 else ''} that bear on this.")
            _say(branch.id, "found", f"{len(events)} things that could happen here; a thousand lives simulated from them.")
            if background:
                wanted = [k for k, v in script.items() if v]
                _say(branch.id, "found" if wanted else "skipped",
                     f"Looked for signs that a partner, children or a home of your own are wanted or already yours: "
                     f"{', '.join(wanted) if wanted else 'none shown'} ({because}). Only those may appear on this path.")
    return rebuilt


def form(scenario_id: str, fixed: Optional[Horizon] = None, only: Optional[list[str]] = None) -> None:
    """Background task: shape the branches, then research them. Never leaves a branch forming."""
    from . import research

    scenario = db.get_scenario(scenario_id)
    person = db.get_person(scenario.person_id)
    rebuilt: list[str] = []
    try:
        rebuilt = _shape(person, scenario, fixed or (scenario.horizon if only is not None else None),
                         set(only) if only is not None else None)
    except Exception:
        log.exception("forming failed; branches fall back to the statistics alone")
    will_research = bool(config.RESEARCH_ENABLED and llm.enabled() and config.BROWSERBASE_API_KEY)
    for branch in _branches_of(scenario).values():
        if branch.forming or (not will_research and branch.research == "pending"):
            with branch_ops.lock:
                failed = branch.forming
                branch.forming = False
                branch.research = "failed" if failed else "none"
                if failed:
                    branch.model = branch.model or {"events": []}
                    branch.revision += 1
                    branch_ops.resimulate(person, branch)
                else:
                    db.save_branch(branch)
    if will_research and rebuilt:
        research.research_scenario(db.get_scenario(scenario_id), rebuilt)


def answer(person: Person, scenario: Scenario, answers: dict[str, str]) -> tuple[Scenario, list, list[str]]:
    """Answers go onto main at once (so they are never asked again). The affected branches are
    marked forming and rebuilt in the background by `form(..., only=affected option ids)`."""
    affected: set[str] = set()
    told = []
    for q in scenario.questions:
        given = (answers.get(q.id) or "").strip()
        if not given or q.answer is not None:
            continue
        q.answer = given
        affected |= set(q.applies_to or [o.id for o in scenario.options])
        told.append(LifeEvent(
            id=sha1(f"{person.id}|answer|{q.text}".encode()).hexdigest()[:16], person_id=person.id, source="told",
            branch_id="main", date=date.today().isoformat(), domain="growth", event_type="answer",
            payload={"question": q.text, "answer": given}, confidence=1.0, text=f"{q.text} — {given}"))
    get_store().append(told)
    db.save_scenario(scenario)
    if told:
        with branch_ops.lock:
            for option_id, branch in _branches_of(scenario).items():
                if option_id in affected and branch.status == "open":
                    branch.forming = True
                    if branch.research != "none":
                        branch.research = "pending"
                    db.save_branch(branch)
                    _say(branch.id, "searching", "Folding your answer in: imagining this path again…")
    return scenario, [branch_ops.view(bid) for bid in scenario.branch_ids], sorted(affected) if told else []


def listed(person_id: str) -> list[Scenario]:
    """Open decisions first, soonest deadline first; decided ones after."""
    found = db.list_scenarios(person_id)
    for s in found:
        deadlines = [o.deadline for o in s.options if o.deadline]
        s.nearest_deadline = min(deadlines) if deadlines and s.status == "open" else None
    return sorted(found, key=lambda s: (s.status != "open", s.nearest_deadline or "9999", s.created_at))
