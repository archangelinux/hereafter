"""A branch, read as chapters: years one and two, then five-year eras.

The simulator's events for the era are the fixed skeleton. The LLM writes the life around them
and must tie factual claims to evidence ids; with the LLM off a chapter is the skeleton itself,
set out as structured text. Chapters are cached per (branch, revision, era) and written in the
background — a request never waits on prose.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from . import db, evidence, llm
from .models import Branch, BranchYear, Chapter, Evidence, Paragraph
from .store import get_store

log = logging.getLogger("hereafter.chapters")
_writers = ThreadPoolExecutor(max_workers=3, thread_name_prefix="hereafter-chapter")
_in_flight: set[tuple] = set()
_in_flight_lock = threading.Lock()

TRAIT_WORDS = {
    "O": ("drawn to the new and the odd", "fond of the familiar"),
    "C": ("orderly, a keeper of lists", "loose with plans"),
    "E": ("fed by company", "restored by quiet"),
    "A": ("quick to accommodate", "unbothered by friction"),
    "N": ("prone to worry", "hard to rattle"),
}


SPAN_STEPS = {"days": 7, "weeks": 4, "months": 6}


def era_bounds(years: list[BranchYear], i: int, unit: str = "years") -> tuple[int, int]:
    """Indices [lo, hi) of the chapter containing step i. A night or a week can be one chapter;
    years are read as the first two, then fives."""
    i = min(max(i, 0), len(years) - 1)
    if unit != "years":
        size = SPAN_STEPS[unit]
        lo = (i // size) * size
        return lo, min(lo + size, len(years))
    if i < 2:
        return 0, min(2, len(years))
    lo = 2 + ((i - 2) // 5) * 5
    return lo, min(lo + 5, len(years))


def step_index(years: list[BranchYear], at: str | None, year: int | None) -> int:
    if at:
        hits = [i for i, y in enumerate(years) if y.at[:10] <= at[:10]]
        return hits[-1] if hits else 0
    hits = [i for i, y in enumerate(years) if y.year == year]
    return hits[0] if hits else (0 if not year or year < years[0].year else len(years) - 1)


def _state_line(y: BranchYear) -> str:
    s = y.state
    if not s.alive:
        return "gone"
    kids = y.outlook["children"].value if "children" in y.outlook else ""
    return " · ".join(x for x in (s.city, s.housing.replace("_", " "), s.relationship_status, s.employment,
                                  f"{s.income_band.replace('_', ' ')} income", kids) if x)


def plain_chapter(branch: Branch, era: list[BranchYear], known: list[Evidence], status: str,
                  which: str = "typical") -> Chapter:
    by_table = {e.used_for: e.id for e in known if e.kind == "statistic"}
    long_view = branch.span.unit == "years"
    paragraphs = []
    for y in era:
        happened = "; ".join(e.text for e in y.events) or ("a quiet year" if long_view else "nothing of note")
        cites = {by_table.get(f"yearly chances sampled from data/{evidence.EVENT_TABLE.get(e.event_type)}") for e in y.events}
        cites |= {e.payload.get("evidence_id") for e in y.events}
        tail = f" {_state_line(y)}." if long_view else ""
        paragraphs.append(Paragraph(text=f"{y.label or y.year} — {happened}.{tail}",
                                    evidence_ids=sorted(c for c in cites if c)))
    first, last = era[0], era[-1]
    title = first.label if len(era) == 1 else f"{first.label} – {last.label}"
    return Chapter(branch_id=branch.id, revision=branch.revision, from_year=first.year, to_year=last.year,
                   from_at=first.at, to_at=last.at, which=which, title=title, status=status, paragraphs=paragraphs)


def _personality_words(traits: dict | None) -> str:
    if not traits:
        return ""
    words = [hi if traits.get(t, 0) > 0.4 else lo for t, (hi, lo) in TRAIT_WORDS.items() if abs(traits.get(t, 0)) > 0.4]
    return "; ".join(words)


def _context(branch: Branch, years: list[BranchYear], lo: int, hi: int, known: list[Evidence]) -> str:
    person = db.get_person(branch.person_id)
    scenario = db.get_scenario(branch.scenario_id) if branch.scenario_id else None
    option = next((o for o in scenario.options if o.id == branch.option_id), None) if scenario else None
    era = years[lo:hi]
    before = years[lo - 1] if lo else None
    lines = [
        f"THE PERSON: {person.display_name or 'unnamed'}, age {era[0].state.age} as this chapter opens."
        + (f" Temperament: {_personality_words(person.personality)}." if _personality_words(person.personality) else ""),
        f"THE DECISION, in their words: {scenario.situation}" if scenario else f"THE PATH: {branch.label}",
    ]
    if option:
        lines.append(f"THE OPTION THIS LIFE FOLLOWS: {option.title}. {option.details}")
    lines.append(f"WHERE THINGS STOOD JUST BEFORE: {_state_line(before) if before else 'the present day: ' + str({k: v for k, v in branch.fork.items() if k in ('city', 'employment', 'housing', 'relationship_status')})}")
    unit = branch.span.unit
    lines.append(f"\nTHE SCALE OF THIS CHAPTER: steps are {unit}. "
                 + ("Stay inside these hours and days: rooms, phones, light, food, sleep." if unit in ("days", "weeks")
                    else "Let time pass between events the way it does."))
    lines.append("\nTHE SKELETON (fixed; every event must appear, in its step; nothing else may happen):")
    for y in era:
        stamp = f"{y.label} ({y.at})" if unit != "years" else f"{y.year} (age {y.state.age})"
        lines.append(f"  {stamp}" + (f" — state: {_state_line(y)}" if unit == "years" else ""))
        for e in y.events:
            own = " [the person's own commit — a choice they make]" if e.event_type == "commit" else ""
            detail = {k: v for k, v in e.payload.items() if k in ("to", "who", "income_band", "children")}
            lines.append(f"      event: {e.text}{own} {detail if detail else ''}")
        if not y.events:
            lines.append("      (nothing happens here: ordinary time)")
    last = era[-1]
    labels = {e["key"]: e["label"] for e in branch.model.get("events", [])}
    lines.append("\nHOW SETTLED THINGS ARE by the end of this chapter (for tone only, never as odds): "
                 + "; ".join(f"{labels.get(a, a)}: {o.value} — {o.words}" for a, o in last.outlook.items()))
    lines.append("\nEVIDENCE you may use and must cite by id:")
    for e in known:
        figure = f" [{e.value}{' ' + e.unit if e.unit else ''}]" if e.value and e.kind == "researched" else ""
        lines.append(f"  {e.id} ({e.kind}): {e.claim}{figure}")
    return "\n".join(lines)


def _callbacks(branch: Branch, era: list[BranchYear]) -> list[Evidence]:
    """A few real moments from main worth calling back to, found by hybrid search."""
    store = get_store()
    probe = " ".join({e.event_type.replace("_", " ") for y in era for e in y.events} | {era[0].state.city, "home friends work"})
    found = store.hybrid_search(branch.person_id, probe, size=5)
    items = [evidence.personal_evidence(branch, e) for e in found if e.event_type not in ("breadcrumb", "state_fact")]
    store.add_evidence(items)
    return items


def _write(branch: Branch, years: list[BranchYear], lo: int, hi: int, which: str) -> None:
    key = (branch.id, branch.revision, which, years[lo].at)
    try:
        store = get_store()
        known = [e for e in store.evidence(branch.person_id, branch.id) if e.kind != "personal"]
        known += _callbacks(branch, years[lo:hi])
        context = _context(branch, years, lo, hi, known)
        if which == "rare":
            context += ("\n\nTHIS IS THE RAREST LIFE among the thousand simulated ones: the improbable version. "
                        "Tell it as plainly as any other; do not remark on its unlikeliness.")
        draft = llm.write_chapter(context)
        valid = {e.id for e in known}
        if draft and draft.paragraphs:
            chapter = Chapter(
                branch_id=branch.id, revision=branch.revision, from_year=years[lo].year, to_year=years[hi - 1].year,
                from_at=years[lo].at, to_at=years[hi - 1].at, which=which, title=draft.title.strip(), status="ready",
                paragraphs=[Paragraph(text=p.text.strip(), evidence_ids=[i for i in p.evidence_ids if i in valid])
                            for p in draft.paragraphs],
            )
        else:
            chapter = plain_chapter(branch, years[lo:hi], known, "ready", which)
        db.save_chapter(chapter)
    except Exception:
        log.exception("chapter writing failed")
        db.save_chapter(plain_chapter(branch, years[lo:hi], [], "ready", which))
    finally:
        with _in_flight_lock:
            _in_flight.discard(key)


def _ensure(branch: Branch, years: list[BranchYear], lo: int, hi: int, which: str) -> Chapter:
    cached = db.get_chapter(branch.id, branch.revision, which, years[lo].at)
    if cached and cached.status == "ready":
        return cached
    known = [e for e in get_store().evidence(branch.person_id, branch.id) if e.kind != "personal"]
    if not llm.enabled():
        chapter = plain_chapter(branch, years[lo:hi], known, "ready", which)
        db.save_chapter(chapter)
        return chapter
    key = (branch.id, branch.revision, which, years[lo].at)
    with _in_flight_lock:
        start = key not in _in_flight
        _in_flight.add(key)
    if start:
        _writers.submit(_write, branch, years, lo, hi, which)
    return cached or plain_chapter(branch, years[lo:hi], known, "writing", which)


def chapter_for(branch: Branch, years: list[BranchYear], i: int, which: str = "typical") -> Chapter:
    lo, hi = era_bounds(years, i, branch.span.unit)
    chapter = _ensure(branch, years, lo, hi, which)
    if hi < len(years) and llm.enabled():  # start on the next chapter while this one is being read
        _ensure(branch, years, *era_bounds(years, hi, branch.span.unit), which)
    return chapter
