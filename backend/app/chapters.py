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
from .branches import has_background
from .sim.outcomes import is_long
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
LONG_CHAPTERS = [(0, 4), (4, 15)]  # the first month (weekly steps), the rest of year one (monthly); then a year at a time


def era_bounds(years: list[BranchYear], i: int, unit: str = "years", count: int = 3) -> tuple[int, int]:
    """Indices [lo, hi) of the chapter containing step i. A night or a week can be one chapter; a
    long path is read as its first month, the rest of its first year, then a year at a time."""
    i = min(max(i, 0), len(years) - 1)
    if not is_long(unit, count):
        size = SPAN_STEPS.get(unit, 6)
        lo = (i // size) * size
        return lo, min(lo + size, len(years))
    for lo, hi in LONG_CHAPTERS:
        if i < hi:
            return lo, min(hi, len(years))
    lo = 15 + ((i - 15) // 4) * 4
    return lo, min(lo + 4, len(years))


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
    long_view = has_background(branch.span)
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


def _doing(delta: float) -> str:
    steps = [(-3, "much worse"), (-1.5, "worse"), (-0.5, "a little worse"), (0.5, "about the same"), (1.5, "a little better"), (3, "better")]
    return next((words for ceiling, words in steps if delta < ceiling), "much better")


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
    lines.append("\nTHE SKELETON (fixed; every event must appear, in its step, in this order; nothing else may happen):")
    for y in era:
        lines.append(f"  {y.label} ({y.at})" + (f" — state: {_state_line(y)}" if has_background(branch.span) else ""))
        for e in y.events:
            own = " [the person's own commit — a choice they make]" if e.event_type == "commit" else ""
            if e.payload.get("head"):
                own = " [STEP ZERO: the choice itself. The chapter opens here.]"
            detail = {k: v for k, v in e.payload.items() if k in ("to", "who", "income_band", "children")}
            lines.append(f"      event: {e.text}{own} {detail if detail else ''}")
        if not y.events:
            lines.append("      (nothing happens here: ordinary time)")
    last = era[-1]
    labels = {e["key"]: e["label"] for e in branch.model.get("events", [])}
    lines.append("\nHOW SETTLED THINGS ARE by the end of this chapter (for tone only, never as odds): "
                 + "; ".join(f"{labels.get(a, a)}: {o.value} — {o.words}" for a, o in last.outlook.items()))
    if branch.measures and branch.measures.get("series"):
        doing = []
        for m, points in branch.measures["series"].items():
            at_end = next((p for p in reversed(points) if p["at"] <= last.at), points[0])
            doing.append(f"{m}: {_doing(at_end['mean'])}")
        lines.append("\nHOW THEY ARE DOING by the end of this chapter, relative to now (colour only; never a number or a list): "
                     + "; ".join(doing))
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


def bible_for(branch: Branch) -> dict:
    """The fixed invented texture of this path — made once, stored, and handed to every chapter so
    they never contradict each other. Real facts come from main; the named people are invented."""
    stored = db.get_bible(branch.id)
    if stored:
        return stored
    person = db.get_person(branch.person_id)
    scenario = db.get_scenario(branch.scenario_id) if branch.scenario_id else None
    option = next((o for o in scenario.options if o.id == branch.option_id), None) if scenario else None
    facts = [e.text for e in get_store().events(branch.person_id)
             if e.event_type not in ("breadcrumb", "social_connectedness", "answer", "note")][-8:]
    said = f"{scenario.situation} {option.title}. {option.details}" if scenario and option else branch.label
    draft = llm.write_bible(f"The person: {person.display_name or 'unnamed'}. Real facts from their log:\n- " + "\n- ".join(facts)
                            + f"\n\nThe decision and this option, in their own words:\n{said}")
    bible = {"facts": facts, "setting": draft.setting if draft else "", "neighbourhood": draft.neighbourhood if draft else "",
             "people": [p.model_dump() for p in draft.people[:3]] if draft else []}
    if draft:
        db.save_bible(branch.id, bible)
    return bible


def _continuity(branch: Branch, years: list[BranchYear], lo: int, which: str) -> str:
    bible = bible_for(branch)
    lines = ["\nSTORY BIBLE (fixed for this whole path; never contradict it):"]
    lines += [f"  real, from their log: {f}" for f in bible["facts"]]
    if bible["setting"]:
        lines += [f"  setting: {bible['setting']}", f"  neighbourhood: {bible['neighbourhood']}"]
        lines += [f"  recurring person (invented): {p['name']} — {p['role']}" for p in bible["people"]]
    if lo == 0:
        lines.append("\nTHE STORY SO FAR: nothing yet. This is the first chapter: open on step zero.")
    else:
        earlier = db.chapter_before(branch.id, branch.revision, which, years[lo].at)
        so_far = earlier.recap if earlier and earlier.recap else \
            "; ".join(f"{y.label}: {e.text}" for y in years[:lo] for e in y.events)[-600:]
        lines.append(f"\nTHE STORY SO FAR: {so_far or 'nothing of note yet.'}")
    return "\n".join(lines)


def _write(branch: Branch, years: list[BranchYear], lo: int, hi: int, which: str) -> None:
    key = (branch.id, branch.revision, which, years[lo].at)
    try:
        store = get_store()
        known = [e for e in store.evidence(branch.person_id, branch.id) if e.kind != "personal"]
        known += _callbacks(branch, years[lo:hi])
        context = _context(branch, years, lo, hi, known) + _continuity(branch, years, lo, which)
        if which == "rare":
            context += ("\n\nTHIS IS THE RAREST LIFE among the thousand simulated ones: the improbable version. "
                        "Tell it as plainly as any other; do not remark on its unlikeliness.")
        draft = llm.write_chapter(context)
        valid = {e.id for e in known}
        if draft and draft.paragraphs:
            chapter = Chapter(
                branch_id=branch.id, revision=branch.revision, from_year=years[lo].year, to_year=years[hi - 1].year,
                from_at=years[lo].at, to_at=years[hi - 1].at, which=which, title=draft.title.strip(), status="ready",
                recap=draft.recap.strip(),
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
    lo, hi = era_bounds(years, i, branch.span.unit, branch.span.count)
    # Chapters are written in order so that each can pick up from the one before: the next one is
    # only started ahead of time once this one is ready.
    chapter = _ensure(branch, years, lo, hi, which)
    if chapter.status == "ready" and hi < len(years) and llm.enabled():
        _ensure(branch, years, *era_bounds(years, hi, branch.span.unit, branch.span.count), which)
    return chapter
