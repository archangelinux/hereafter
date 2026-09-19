"""Hereafter API. See docs/API.md for the contract and docs/PRODUCT.md for what it means.

Invariants that live at this layer: "now" is always the server clock (no route accepts one);
main is append-only (nothing but /erase removes a main event, and nothing edits one); commits
on a branch can be undone, a merge cannot; every route but /health and /people needs the
person's own bearer token.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime
from hashlib import sha1
from typing import Optional

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from . import branches as branch_ops
from . import chapters, config, db, llm, research, security, seed
from . import scenarios as scenarios_ops
from .ingest import links, pipeline
from .models import (AnswersRequest, Branch, BranchView, CarryRequest, CommitRequest, EraseRequest, LifeEvent, MergeRequest,
                     Option, Person, PersonRequest, Scenario, ScenarioRequest, SimulateRequest, StateVector,
                     UndoRequest)
from .personality import Personality, merge as merge_personality
from .state import build_state
from .store import get_store

log = logging.getLogger("hereafter")
NARRATION_BATCH = 25
DATE_PRECONDITION = re.compile(r"^\s*([\w ]+?)\s*:\s*(\d{4}-\d{2}-\d{2})\s*$")
STATE_PRECONDITION = re.compile(r"^\s*(\w+)\s*:\s*(.+?)\s*$")
COMPARE_EVERY = 5


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.conn()
    security.fernet()
    try:
        seed.ensure_demo(get_store())
    except Exception:
        log.exception("could not seed the demo person")
    yield


app = FastAPI(title="Hereafter", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=config.FRONTEND_ORIGINS, allow_methods=["GET", "POST"],
                   allow_headers=["Authorization", "Content-Type"])


def today() -> str:
    return date.today().isoformat()


# --- auth ---


def bearer(authorization: Optional[str] = Header(None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "a bearer token is required")
    return authorization[7:].strip()


def owner(token: str, person_id: str) -> Person:
    """The person, if and only if the token is theirs."""
    person = db.get_person(person_id)
    if person is None:
        raise HTTPException(401, "unknown person")
    is_demo = person_id == security.DEMO_ID and token == security.DEMO_TOKEN
    if not is_demo and not security.token_matches(token, db.person_token_hash(person_id)):
        raise HTTPException(403, "this token does not belong to that person")
    return person


def owned_branch(token: str, branch_id: str):
    found = db.get_branch(branch_id)
    if not found:
        raise HTTPException(404, "no such branch")
    return owner(token, found[0].person_id), found[0], found[1]


def _present(person: Person):
    store = get_store()
    main = store.events(person.id)
    state, steps, decisions = build_state(store, person, len(main))
    return main, state, steps, decisions


# --- people ---


@app.get("/health")
def health():
    return {"ok": True, "llm_enabled": llm.enabled(), "llm_provider": config.LLM_PROVIDER if llm.enabled() else None,
            "store": get_store().kind, "research": bool(config.RESEARCH_ENABLED and config.BROWSERBASE_API_KEY),
            "now": today()}


@app.post("/people")
def create_person(req: PersonRequest):
    token = security.new_token()
    person = db.upsert_person(
        Person(id=security.new_person_id(), display_name=req.display_name or "", birth_year=req.birth_year, sex=req.sex),
        token_hash=security.token_hash(token),
    )
    return {"person_id": person.id, "token": token}


# --- main: ingest and trunk ---


@app.post("/ingest")
async def ingest(
    person_id: str = Form(...),
    display_name: Optional[str] = Form(None),
    birth_year: Optional[int] = Form(None),
    sex: Optional[str] = Form(None),
    text: str = Form(""),
    handles: str = Form("{}"),
    links: str = Form("[]"),
    live_source: Optional[str] = Form(None),
    files: list[UploadFile] = File(default=[]),
    token: str = Depends(bearer),
):
    def _json(raw: str, fallback):
        try:
            value = json.loads(raw or "null")
            return value if isinstance(value, type(fallback)) else fallback
        except ValueError:
            return fallback

    owner(token, person_id)
    person = db.upsert_person(Person(id=person_id, display_name=display_name or "", birth_year=birth_year,
                                     sex=sex if sex in ("M", "F") else None))
    uploads = [(f.filename or "a file", await f.read()) for f in files]
    handle_map = {k: str(v) for k, v in _json(handles, {}).items() if v}
    result = await run_in_threadpool(
        pipeline.ingest, get_store(), person.id, person.display_name, text, handle_map,
        [str(u) for u in _json(links, [])], uploads, live_source,
    )

    merged = merge_personality(
        Personality(**person.personality) if person.personality else None, result["personality"]
    )
    person = db.upsert_person(Person(id=person.id, birth_year=person.birth_year or result["birth_year"],
                                     personality=merged.model_dump() if merged else None))
    _, _, _, decisions = await run_in_threadpool(_present, person)  # RECONCILE across all sources
    return {
        "person_id": person.id,
        "events_added": result["events_added"],
        "inputs": result["inputs"],
        "personality": person.personality,
        "reconciliation": decisions,
    }


@app.get("/trunk")
def trunk(person_id: str, token: str = Depends(bearer)):
    person = owner(token, person_id)
    main, state, steps, decisions = _present(person)
    return {"person": person, "now": today(), "events": main, "state": state,
            "agent_log": steps, "reconciliation": decisions}


# --- scenarios and branches ---


@app.post("/scenarios")
def create_scenario(req: ScenarioRequest, background: BackgroundTasks, token: str = Depends(bearer)):
    """Returns at once with placeholder branches (`forming: true`); see scenarios.form."""
    person = owner(token, req.person_id)
    if req.assuming_branch_id:
        owned_branch(token, req.assuming_branch_id)
    _, fork, _, _ = _present(person)
    options = [Option(id=uuid.uuid4().hex[:8], title=o.title.strip(), details=o.details.strip(), deadline=o.deadline)
               for o in req.options]
    scenario, views = scenarios_ops.create(person, fork, req.situation.strip(), options, req.horizon, req.assuming_branch_id)
    background.add_task(scenarios_ops.form, scenario.id, req.horizon)
    return {"scenario": scenario, "branches": views, "questions": scenario.questions}


@app.get("/scenarios")
def scenarios(person_id: str, token: str = Depends(bearer)):
    owner(token, person_id)
    return {"scenarios": scenarios_ops.listed(person_id)}


@app.post("/scenarios/{scenario_id}/answers")
def answer_questions(scenario_id: str, req: AnswersRequest, background: BackgroundTasks, token: str = Depends(bearer)):
    scenario = db.get_scenario(scenario_id)
    if not scenario:
        raise HTTPException(404, "no such scenario")
    person = owner(token, scenario.person_id)
    if any(b.forming for b in scenarios_ops._branches_of(scenario).values()):
        raise HTTPException(409, "these paths are still forming; answer in a moment")
    scenario, views, affected = scenarios_ops.answer(person, scenario, req.answers)
    if affected:
        background.add_task(scenarios_ops.form, scenario.id, None, affected)
    return {"scenario": scenario, "branches": views}


@app.get("/research")
def research_feed(branch_id: str, token: str = Depends(bearer)):
    _, branch, _ = owned_branch(token, branch_id)
    return {"branch_id": branch_id, "research": branch.research, "steps": db.research_steps(branch_id)}


@app.post("/simulate")
def simulate_branch(req: SimulateRequest, background: BackgroundTasks, token: str = Depends(bearer)) -> BranchView:
    person = owner(token, req.person_id)
    _, fork, _, _ = _present(person)
    view = branch_ops.create_branch(person, fork, req.label, req.assumption, req.precondition, req.horizon_years)
    background.add_task(narrate_branch, view.branch.id)
    return view


def _stale(branch: Branch, present: StateVector) -> bool:
    """A precondition is either a dated deadline ("decide_by: 2026-09-26") or a fact that must
    still hold on main ("relationship_status: single")."""
    if not branch.precondition:
        return False
    m = DATE_PRECONDITION.match(branch.precondition)
    if m:
        return today() > m.group(2)
    m = STATE_PRECONDITION.match(branch.precondition)
    if m and m.group(1) in StateVector.model_fields:
        return str(getattr(present, m.group(1))).lower() != m.group(2).lower()
    return False


def _recheck(branch: Branch, present: StateVector) -> Branch:
    if branch.status == "open" and _stale(branch, present):
        with branch_ops.lock:
            branch.status = "stale"
            db.save_branch(branch)
    return branch


@app.get("/branches")
def branches(person_id: str, token: str = Depends(bearer)):
    person = owner(token, person_id)
    _, present, _, _ = _present(person)
    views = [BranchView(branch=_recheck(b, present), years=years) for b, years in db.list_branches(person_id)]
    return {"now": today(), "branches": views}


@app.post("/branches/{branch_id}/commits")
def commit(branch_id: str, req: CommitRequest, token: str = Depends(bearer)) -> BranchView:
    person, branch, years = owned_branch(token, branch_id)
    if branch.forming:
        raise HTTPException(409, "this path is still forming")
    if branch.status != "open":
        raise HTTPException(409, f"this path is {branch.status}; nothing more can be committed to it")
    step = branch_ops.step_of(branch, req.at, req.year) if (req.at or req.year) else None
    if step is None or step >= len(years):
        raise HTTPException(400, "that moment is not on this path")
    if not req.message.strip():
        raise HTTPException(400, "say what you would decide")
    with branch_ops.lock:
        branch = db.get_branch(branch_id)[0]
        return branch_ops.add_commit(person, branch, step, req.message.strip())


@app.post("/branches/{branch_id}/undo")
def undo(branch_id: str, req: UndoRequest, token: str = Depends(bearer)) -> BranchView:
    person, branch, _ = owned_branch(token, branch_id)
    if branch.status != "open":
        raise HTTPException(409, f"this path is {branch.status}")
    if not branch.commits or (req.commit_id and req.commit_id not in {c.id for c in branch.commits}):
        raise HTTPException(404, "there is no such commit to undo")
    with branch_ops.lock:
        branch = db.get_branch(branch_id)[0]
        return branch_ops.undo_commit(person, branch, req.commit_id)


def _distinctive(branch: Branch, years, siblings: list) -> list[dict]:
    """What is unusually common in this branch against its scenario: an Elastic significant_terms
    aggregation over every simulated life, with a numpy fallback while the index catches up."""
    events = {e["key"]: e for e in (branch.model or {}).get("events", [])}
    final = years[-1].outlook if years else {}
    found = get_store().distinctive(branch, [b for b, _ in siblings])
    if found is None:
        elsewhere = lambda key: max([ys[-1].outlook[key].share for _, ys in siblings if ys and key in ys[-1].outlook] or [0.0])
        ranked = sorted(events, key=lambda k: (final[k].share if k in final else 0) - elsewhere(k), reverse=True)
        found = [{"key": k} for k in ranked[:5] if k in final and final[k].share - elsewhere(k) > 0.1]
    return [{"branch_id": branch.id, "key": f["key"], "label": events[f["key"]]["label"],
             "words": final[f["key"]].words if f["key"] in final else events[f["key"]]["words"],
             "basis": events[f["key"]]["basis"]} for f in found if f["key"] in events]


@app.get("/compare")
def compare(a: str, b: str, c: Optional[str] = None, token: str = Depends(bearer)):
    picked = [owned_branch(token, bid) for bid in (a, b, c) if bid]
    span = min(len(years) for _, _, years in picked)
    if span == 0:  # at least one of them is still forming
        return {"branches": [branch for _, branch, _ in picked], "checkpoints": [], "distinctive": []}
    if picked[0][1].span.unit == "years":
        marks = list(range(COMPARE_EVERY - 1, span, COMPARE_EVERY))
    else:  # short horizons: a handful of evenly spaced moments, always including the last
        marks = sorted({round((span - 1) * f) for f in (0.0, 0.34, 0.67, 1.0)})
    shared = set.intersection(*[set(years[0].outlook) for _, _, years in picked]) if span else set()
    labels = {e["key"]: e["label"] for _, branch, _ in picked for e in (branch.model or {}).get("events", [])}
    checkpoints = []
    for i in marks:
        rows = []
        for aspect in (k for k in picked[0][2][i].outlook if k in shared):
            values = [{"branch_id": branch.id, **years[i].outlook[aspect].model_dump()} for _, branch, years in picked]
            differs = len({v["value"] for v in values}) > 1 or len({v["words"] for v in values}) > 1
            rows.append({"aspect": aspect, "label": labels.get(aspect, aspect.replace("_", " ")),
                         "differs": differs, "values": values})
        first = picked[0][2][i]
        checkpoints.append({"year": first.year, "at": first.at, "label": first.label, "age": first.state.age, "rows": rows})
    distinctive = []
    for _, branch, years in picked:
        siblings = [(o, ys) for _, o, ys in picked if o.id != branch.id]
        distinctive += _distinctive(branch, years, siblings)
    return {"branches": [branch for _, branch, _ in picked], "checkpoints": checkpoints, "distinctive": distinctive}


@app.get("/lives")
def lives(branch_id: str, which: str = "typical", token: str = Depends(bearer)):
    _, branch, years = owned_branch(token, branch_id)
    if which != "rare":
        return {"which": "typical", "rarity_words": "the most typical of the thousand simulated lives", "years": years}
    rare = db.rare_life(branch_id)
    happened = [e.event_type for y in rare for e in y.events if e.payload.get("basis") != "background"]
    labels = {e["key"]: e["label"] for e in (branch.model or {}).get("events", [])}
    rarest = next((k for k in (get_store().rarest_keys(branch) or []) if k in happened), None)
    if rarest is None and rare:  # numpy fallback: the least shared thing that happens in this life
        final = rare[-1].outlook
        rarest = min((k for k in happened if k in final), key=lambda k: final[k].share, default=None)
    words = "the rarest coherent life among the thousand"
    if rarest in labels:
        words += f" — the one where {labels[rarest][0].lower()}{labels[rarest][1:]}"
    return {"which": "rare", "rarity_words": words, "years": rare}


@app.get("/chapters")
def chapter(branch_id: str, at: Optional[str] = None, year: Optional[int] = None, which: str = "typical",
            token: str = Depends(bearer)):
    _, branch, years = owned_branch(token, branch_id)
    if which == "rare":
        years = db.rare_life(branch_id)
    if not years:
        raise HTTPException(404, "this path has no steps")
    return chapters.chapter_for(branch, years, chapters.step_index(years, at, year), "rare" if which == "rare" else "typical")


@app.get("/evidence")
def evidence_for(branch_id: Optional[str] = None, ids: Optional[str] = None, person_id: Optional[str] = None,
                 token: str = Depends(bearer)):
    if branch_id:
        person, _, _ = owned_branch(token, branch_id)
    elif person_id:
        person = owner(token, person_id)
    else:
        raise HTTPException(400, "give a branch_id, or ids with a person_id")
    wanted = [i for i in (ids or "").split(",") if i]
    return {"evidence": get_store().evidence(person.id, branch_id, wanted or None)}


@app.get("/assessment")
def assessment(branch_id: str, token: str = Depends(bearer)):
    """Jev's classification and the probability logic's estimate for every possible event on a branch."""
    _, branch, _ = owned_branch(token, branch_id)
    events = (branch.model or {}).get("events", [])
    rows = [{"key": e["key"], "label": e["label"], "estimate": e.get("estimate"), "jev": e.get("jev")} for e in events]
    by_category: dict[str, int] = {}
    for r in rows:
        if r["estimate"]:
            by_category[r["estimate"]["category"]] = by_category.get(r["estimate"]["category"], 0) + 1
    return {"branch_id": branch_id, "categories": by_category,
            "events": sorted(rows, key=lambda r: -(r["estimate"] or {}).get("likelihood", 0))}


# --- merge (permanent) and pick ---


@app.post("/merge")
def merge(req: MergeRequest, token: str = Depends(bearer)):
    person, branch, _ = owned_branch(token, req.branch_id)
    _, present, _, _ = _present(person)
    branch = _recheck(branch, present)
    if branch.forming:
        raise HTTPException(409, "this path is still forming")
    if branch.status != "open":
        raise HTTPException(409, f"this path is {branch.status}")
    if req.confirm != branch.label:
        raise HTTPException(400, "a merge cannot be undone: confirm it by giving this path's name exactly")

    told = LifeEvent(
        id=sha1(f"{branch.id}|decision".encode()).hexdigest()[:16], person_id=branch.person_id,
        source="told", branch_id="main", date=today(), domain="career", event_type="decision",
        payload={**{k: v for k, v in branch.assumption.items() if k in branch_ops.STATE_FIELDS},
                 "from_branch": branch.id}, confidence=1.0, text=f"chose: {branch.label}",
    )
    get_store().append([told])
    with branch_ops.lock:
        branch.status = "merged"
        db.save_branch(branch)
        faded = []
        for sibling, _ in db.list_branches(branch.person_id):
            # only the other options of the same decision become roads not taken
            if sibling.id != branch.id and sibling.status == "open" and sibling.scenario_id == branch.scenario_id:
                sibling.status = "faded"
                db.save_branch(sibling)
                faded.append(sibling)
        scenario = db.get_scenario(branch.scenario_id) if branch.scenario_id else None
        if scenario:
            scenario.status, scenario.decided_branch_id = "decided", branch.id
            db.save_scenario(scenario)
    return {"merged": branch, "faded": faded, "told_event": told}


@app.post("/carry")
def carry(req: CarryRequest, token: str = Depends(bearer)):
    _, branch, years = owned_branch(token, req.branch_id)
    if branch.status not in ("faded", "stale"):
        raise HTTPException(409, "only a road not taken can give something up")
    if branch.carried_event_id:
        raise HTTPException(409, "one thing has already been carried from this path")
    event = next((e for y in years for e in y.events if e.id == req.event_id), None)
    if not event:
        raise HTTPException(404, "that event is not on this path")

    goal = LifeEvent(
        id=sha1(f"{branch.id}|carry".encode()).hexdigest()[:16], person_id=branch.person_id,
        source="told", branch_id="main", date=today(), domain=event.domain, event_type="goal",
        payload={"from_branch": branch.id, "carried_event_id": event.id, "carried_event_type": event.event_type,
                 "target_date": event.date, **event.payload},
        confidence=1.0, text=event.text,
    )
    get_store().append([goal])
    with branch_ops.lock:
        branch.carried_event_id = event.id
        db.save_branch(branch)
    return {"goal_event": goal, "branch": branch}


# --- narration (one line per event; chapters are the richer form) ---


@app.get("/narration")
def narration(branch_id: str, token: str = Depends(bearer)):
    owned_branch(token, branch_id)
    lines, complete = db.get_lines(branch_id)
    return {"branch_id": branch_id, "complete": complete or not llm.enabled(), "lines": lines}


def narrate_branch(branch_id: str) -> None:
    """Background only. The UI has already rendered every event's plain `text`."""
    found = db.get_branch(branch_id)
    if not found or not llm.enabled():
        return
    events = [e for y in found[1] for e in y.events]
    for i in range(0, len(events), NARRATION_BATCH):
        batch = [{"event_id": e.id, "year": e.date[:4], "domain": e.domain, "event_type": e.event_type,
                  "details": e.payload} for e in events[i: i + NARRATION_BATCH]]
        lines = llm.narrate(batch)
        if lines:
            db.save_lines(branch_id, lines, complete=False)
    db.save_lines(branch_id, {}, complete=True)


# --- what is known, and burning the book ---


@app.get("/inventory")
def inventory(person_id: str, token: str = Depends(bearer)):
    owner(token, person_id)
    store = get_store()
    by_source: dict[str, list[LifeEvent]] = {}
    for e in store.events(person_id):
        by_source.setdefault(e.source, []).append(e)
    sources = [{"source": s, "count": len(evs), "newest": max(e.date for e in evs), "examples": evs[-3:]}
               for s, evs in by_source.items()]
    simulated = store.counts_by_source(person_id).get("simulated", 0)
    if simulated:
        sources.append({"source": "simulated", "count": simulated, "newest": today(), "examples": []})
    return {
        "sources": sources,
        "handles": [{"source": s, "handle": h} for s, h in db.submitted_handles(person_id).items()],
        "cached_pages": len(list(links.cache_dir(person_id).glob("*.json"))) if links.cache_dir(person_id).exists() else 0,
        "sent_to_llm": ["public pages you pointed Hereafter at", "your own words", "chat excerpts with other people's names replaced",
                        "simulated event logs, for narration"] if llm.enabled() else [],
        "stored_nowhere": ["raw chat exports", "uploaded files", "other people's names", "passwords or logins of any kind"],
    }


@app.post("/erase")
def erase(req: EraseRequest, token: str = Depends(bearer)):
    owner(token, req.person_id)
    if req.person_id == security.DEMO_ID:
        raise HTTPException(409, "the demo person reseeds itself and cannot be erased here")
    if req.confirm != "erase":
        raise HTTPException(400, 'confirm with the word "erase"')
    if any(b.forming or b.research in ("pending", "running") for b, _ in db.list_branches(req.person_id)):
        raise HTTPException(409, "some paths are still forming or being researched; erase again in a moment")
    branch_ops.flush()
    gone = get_store().erase(req.person_id)
    cache = links.cache_dir(req.person_id)
    gone["cached_pages"] = len(list(cache.glob("*.json"))) if cache.exists() else 0
    shutil.rmtree(cache, ignore_errors=True)
    gone["branches"] = db.erase_person(req.person_id)["branches"]
    return {"erased": gone}
