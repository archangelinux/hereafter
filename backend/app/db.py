"""SQLite: people, the handles they submitted, scenarios, branch metadata, chapters, research
feeds. Life events never live here — those belong to the event store (Elastic). Name, birth
year, personality and chapter prose are encrypted at rest (see security.py)."""

from __future__ import annotations

import json
import sqlite3
import threading
from typing import Optional

from . import config, security
from .models import Branch, BranchYear, Chapter, Commit, Paragraph, Person, ResearchStep, Scenario

_lock = threading.Lock()
# One connection per thread: FastAPI serves sync routes from a thread pool, and a sqlite3
# connection shared across threads fails under concurrent reads.
_local = threading.local()
_generation = 0

SCHEMA = """
CREATE TABLE IF NOT EXISTS people (
  id TEXT PRIMARY KEY, display_name TEXT, birth_year TEXT, sex TEXT, personality TEXT, token_hash TEXT
);
CREATE TABLE IF NOT EXISTS handles (
  person_id TEXT NOT NULL, submitted_by TEXT NOT NULL, source TEXT NOT NULL, handle TEXT NOT NULL,
  submitted_at TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (person_id, source)
);
CREATE TABLE IF NOT EXISTS scenarios (
  id TEXT PRIMARY KEY, person_id TEXT NOT NULL, doc TEXT NOT NULL, created_at TEXT
);
CREATE TABLE IF NOT EXISTS branches (
  id TEXT PRIMARY KEY, person_id TEXT NOT NULL, forked_at TEXT, doc TEXT NOT NULL, years TEXT, rare TEXT
);
CREATE TABLE IF NOT EXISTS chapters (
  branch_id TEXT NOT NULL, revision INTEGER NOT NULL, which TEXT NOT NULL, from_at TEXT NOT NULL,
  status TEXT, doc TEXT, PRIMARY KEY (branch_id, revision, which, from_at)
);
CREATE TABLE IF NOT EXISTS research_steps (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, branch_id TEXT NOT NULL, doc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS narration (
  event_id TEXT PRIMARY KEY, branch_id TEXT NOT NULL, line TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS narration_status (branch_id TEXT PRIMARY KEY, complete INTEGER);
CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY, person_id TEXT, branch_id TEXT, date TEXT, domain TEXT, doc TEXT
);
CREATE TABLE IF NOT EXISTS evidence (
  id TEXT PRIMARY KEY, person_id TEXT, branch_id TEXT, doc TEXT
);
"""


def conn() -> sqlite3.Connection:
    if getattr(_local, "generation", None) != _generation:
        config.SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(config.SQLITE_PATH, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA)
        _local.conn, _local.generation = c, _generation
    return _local.conn


def reset(path=None) -> None:
    """Point at a fresh database (tests). Every thread reconnects on its next use."""
    global _generation
    _generation += 1
    if path is not None:
        config.SQLITE_PATH = path


def _exec(sql: str, args: tuple = ()) -> None:
    with _lock:
        conn().execute(sql, args)
        conn().commit()


# --- people & handles ---


def upsert_person(p: Person, token_hash: Optional[str] = None) -> Person:
    """Fills in what is new and never blanks what is already known, in one statement."""
    _exec(
        "INSERT INTO people (id, display_name, birth_year, sex, personality, token_hash) VALUES (?,?,?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET "
        "display_name=COALESCE(excluded.display_name, display_name), "
        "birth_year=COALESCE(excluded.birth_year, birth_year), sex=COALESCE(excluded.sex, sex), "
        "personality=COALESCE(excluded.personality, personality), "
        "token_hash=COALESCE(token_hash, excluded.token_hash)",
        (
            p.id, security.seal(p.display_name) if p.display_name else None,
            security.seal(str(p.birth_year)) if p.birth_year else None, p.sex,
            security.seal(json.dumps(p.personality)) if p.personality else None, token_hash,
        ),
    )
    return get_person(p.id)


def get_person(person_id: str) -> Optional[Person]:
    row = conn().execute("SELECT * FROM people WHERE id=?", (person_id,)).fetchone()
    if not row:
        return None
    born = security.unseal(row["birth_year"])
    traits = security.unseal(row["personality"])
    return Person(id=row["id"], display_name=security.unseal(row["display_name"]) or "",
                  birth_year=int(born) if born else None, sex=row["sex"],
                  personality=json.loads(traits) if traits else None)


def person_token_hash(person_id: str) -> Optional[str]:
    row = conn().execute("SELECT token_hash FROM people WHERE id=?", (person_id,)).fetchone()
    return row["token_hash"] if row else None


def record_handle(person_id: str, submitted_by: str, source: str, handle: str) -> None:
    _exec(
        "INSERT OR REPLACE INTO handles (person_id, submitted_by, source, handle) VALUES (?,?,?,?)",
        (person_id, submitted_by, source, handle),
    )


def submitted_handles(person_id: str) -> dict[str, str]:
    """Only handles the person submitted for themselves."""
    rows = conn().execute(
        "SELECT source, handle FROM handles WHERE person_id=? AND submitted_by=person_id",
        (person_id,),
    ).fetchall()
    return {r["source"]: r["handle"] for r in rows}


# --- scenarios ---


def save_scenario(s: Scenario) -> None:
    _exec("INSERT OR REPLACE INTO scenarios VALUES (?,?,?,?)", (s.id, s.person_id, s.model_dump_json(), s.created_at))


def get_scenario(scenario_id: str) -> Optional[Scenario]:
    row = conn().execute("SELECT doc FROM scenarios WHERE id=?", (scenario_id,)).fetchone()
    return Scenario(**json.loads(row["doc"])) if row else None


def list_scenarios(person_id: str) -> list[Scenario]:
    rows = conn().execute("SELECT doc FROM scenarios WHERE person_id=? ORDER BY created_at, id", (person_id,))
    return [Scenario(**json.loads(r["doc"])) for r in rows.fetchall()]


# --- branches ---


def save_branch(b: Branch, years: Optional[list[BranchYear]] = None, rare: Optional[list[BranchYear]] = None) -> None:
    if years is None:
        _exec("UPDATE branches SET doc=? WHERE id=?", (b.model_dump_json(), b.id))
        return
    _exec(
        "INSERT OR REPLACE INTO branches VALUES (?,?,?,?,?,?)",
        (b.id, b.person_id, b.forked_at, b.model_dump_json(), json.dumps([y.model_dump() for y in years]),
         json.dumps([y.model_dump() for y in rare or []])),
    )


def rare_life(branch_id: str) -> list[BranchYear]:
    row = conn().execute("SELECT rare FROM branches WHERE id=?", (branch_id,)).fetchone()
    return [BranchYear(**y) for y in json.loads(row["rare"] or "[]")] if row else []


def _branch(row: sqlite3.Row) -> tuple[Branch, list[BranchYear]]:
    branch = Branch(**json.loads(row["doc"]))
    if branch.status == "expired":  # rows written before "stale" replaced it
        branch.status = "stale"
    return branch, [BranchYear(**y) for y in json.loads(row["years"] or "[]")]


def get_branch(branch_id: str) -> Optional[tuple[Branch, list[BranchYear]]]:
    row = conn().execute("SELECT * FROM branches WHERE id=?", (branch_id,)).fetchone()
    return _branch(row) if row else None


def list_branches(person_id: str) -> list[tuple[Branch, list[BranchYear]]]:
    rows = conn().execute(
        "SELECT * FROM branches WHERE person_id=? ORDER BY forked_at, rowid", (person_id,)
    ).fetchall()
    return [_branch(r) for r in rows]


# --- chapters (prose encrypted at rest) ---


def save_chapter(ch: Chapter) -> None:
    _exec(
        "INSERT OR REPLACE INTO chapters VALUES (?,?,?,?,?,?)",
        (ch.branch_id, ch.revision, ch.which, ch.from_at, ch.status, security.seal(ch.model_dump_json())),
    )


def get_chapter(branch_id: str, revision: int, which: str, from_at: str) -> Optional[Chapter]:
    row = conn().execute(
        "SELECT doc FROM chapters WHERE branch_id=? AND revision=? AND which=? AND from_at=?",
        (branch_id, revision, which, from_at),
    ).fetchone()
    doc = security.unseal(row["doc"]) if row else None
    return Chapter(**json.loads(doc)) if doc else None


# --- research feed ---


def add_research_step(branch_id: str, step: ResearchStep) -> None:
    _exec("INSERT INTO research_steps (branch_id, doc) VALUES (?,?)", (branch_id, step.model_dump_json()))


def research_steps(branch_id: str) -> list[ResearchStep]:
    rows = conn().execute("SELECT doc FROM research_steps WHERE branch_id=? ORDER BY seq", (branch_id,))
    return [ResearchStep(**json.loads(r["doc"])) for r in rows.fetchall()]


# --- narration cache ---


def save_lines(branch_id: str, lines: dict[str, str], complete: bool) -> None:
    with _lock:
        c = conn()
        c.executemany(
            "INSERT OR REPLACE INTO narration (event_id, branch_id, line) VALUES (?,?,?)",
            [(eid, branch_id, line) for eid, line in lines.items()],
        )
        c.execute("INSERT OR REPLACE INTO narration_status VALUES (?,?)", (branch_id, int(complete)))
        c.commit()


def get_lines(branch_id: str) -> tuple[dict[str, str], bool]:
    rows = conn().execute(
        "SELECT event_id, line FROM narration WHERE branch_id=?", (branch_id,)
    ).fetchall()
    status = conn().execute(
        "SELECT complete FROM narration_status WHERE branch_id=?", (branch_id,)
    ).fetchone()
    return {r["event_id"]: r["line"] for r in rows}, bool(status and status["complete"])


# --- erase: the only deletion ---


def erase_person(person_id: str) -> dict[str, int]:
    counts = {}
    with _lock:
        c = conn()
        branch_ids = [r["id"] for r in c.execute("SELECT id FROM branches WHERE person_id=?", (person_id,))]
        for bid in branch_ids:
            for table in ("chapters", "research_steps", "narration", "narration_status"):
                c.execute(f"DELETE FROM {table} WHERE branch_id=?", (bid,))
        counts["branches"] = len(branch_ids)
        for table in ("branches", "scenarios", "handles", "events", "evidence"):
            c.execute(f"DELETE FROM {table} WHERE person_id=?", (person_id,))
        c.execute("DELETE FROM people WHERE id=?", (person_id,))
        c.commit()
    return counts
