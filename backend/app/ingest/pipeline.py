"""The universal ingestion pipeline. One path for everything offered:

    ROUTER -> EXTRACT (one schema) -> INDEX -> RECONCILE

Every source only ever produces the same three outputs — events, state facts (stored as
`state_fact` events), and a personality estimate — so nothing past `_extract` knows or cares
what kind of input it came from. Nothing here raises to the caller.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from hashlib import sha1
from typing import Optional

from .. import db, llm, personality
from ..models import LifeEvent
from ..personality import Personality
from ..store import EventStore
from . import chat, links
from .router import Offered, route

log = logging.getLogger("hereafter.ingest")

STATE_KEYS = ("city", "education", "field", "employment", "income_band", "relationship_status", "housing")
FACT_DOMAINS = {
    "housing": ("city", "housing"), "career": ("education", "field", "employment"),
    "money": ("income_band",), "relationship": ("relationship_status",),
}
UNDATED_DISCOUNT = 0.7
THIN_CONFIDENCE_CAP = 0.35
MAX_TEXT_CHARS = 120_000


@dataclass
class Produced:
    events: list[LifeEvent] = field(default_factory=list)
    personality: Optional[Personality] = None
    birth_year: Optional[int] = None
    outcome: str = ""


def _event(person_id: str, source: str, origin: str, *, domain: str, event_type: str, text: str,
           when: Optional[str], confidence: float, payload: Optional[dict] = None) -> LifeEvent:
    today = date.today().isoformat()
    payload = dict(payload or {})
    if not when:
        payload["undated"] = True
        confidence *= UNDATED_DISCOUNT
    when = min(when or today, today)  # main holds the past; nothing lands ahead of now
    key = f"{person_id}|{origin}|{when}|{event_type}|{text}"
    return LifeEvent(
        id=sha1(key.encode()).hexdigest()[:16], person_id=person_id, source=source, branch_id="main",
        date=when, domain=domain, event_type=event_type, payload=payload,
        confidence=round(max(0.0, min(1.0, confidence)), 3), text=text,
    )


def _freeform(person_id: str, source: str, origin: str, text: str, confidence: float = 0.5) -> LifeEvent:
    """Step 5: anything unparseable is still indexed, as texture for retrieval."""
    return _event(person_id, source, origin, domain="career", event_type="note",
                  text=text[:2000], when=None, confidence=confidence)


def _extract(person_id: str, source: str, item: Offered, text: str, owner: str,
             confidence_cap: float = 1.0) -> Produced:
    """The single extraction call every input kind goes through."""
    out = Produced()
    result = llm.extract(item.kind, item.name, text[:MAX_TEXT_CHARS], date.today().isoformat(), owner)
    if result is None:
        return out
    for e in result.events:
        payload = {k: getattr(e, k) for k in STATE_KEYS if getattr(e, k)}
        out.events.append(_event(person_id, source, item.name, domain=e.domain, event_type=e.event_type,
                                 text=e.text, when=e.date, payload=payload,
                                 confidence=min(e.confidence, confidence_cap)))
    if result.facts:
        # One state_fact event per domain, so a domain listing surfaces the facts it needs.
        for domain, keys in FACT_DOMAINS.items():
            facts = {k: getattr(result.facts, k) for k in keys if getattr(result.facts, k)}
            if facts:
                summary = ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in facts.items())
                out.events.append(_event(person_id, source, item.name, domain=domain, event_type="state_fact",
                                         text=summary, when=result.facts.as_of, payload=facts,
                                         confidence=min(result.facts.confidence, confidence_cap)))
        out.birth_year = result.facts.birth_year
    if result.personality:
        out.personality = Personality(**result.personality.model_dump())
    return out


def _from_pages(person_id: str, item: Offered, pages: list[links.Page], owner: str) -> Produced:
    out = Produced()
    tiers = []
    for page in pages:
        tiers.append(page.tier)
        if page.tier == "substantial":
            got = _extract(person_id, "scraped", item, page.text, owner)
            out.events += got.events or [_freeform(person_id, "scraped", page.url, page.surfaced or page.text[:600], 0.4)]
            out.personality = personality.merge(out.personality, got.personality)
        elif page.tier == "thin":
            got = _extract(person_id, "scraped", item, page.surfaced, owner, THIN_CONFIDENCE_CAP)
            out.events += got.events or [_event(person_id, "scraped", page.url, domain="career",
                                                event_type="profile_glimpse", text=page.surfaced,
                                                when=None, confidence=THIN_CONFIDENCE_CAP)]
        else:
            out.events.append(_event(person_id, "scraped", page.url, domain="career", event_type="breadcrumb",
                                     text=page.url, when=None, confidence=0.15, payload={"url": page.url}))
    if "substantial" in tiers:
        out.outcome = "Read, and folded in."
    elif "thin" in tiers:
        out.outcome = "Only a glimpse came through. Hereafter kept what it could see."
    else:
        out.outcome = "The door was closed. Hereafter will remember the address."
    return out


def _from_chat(person_id: str, item: Offered, display_name: str) -> Produced:
    messages = chat.parse(item.text)
    owner = chat.owner_of(messages, display_name)
    signal = chat.connectedness(messages, owner)
    out = Produced()
    last = max((m.when for m in messages if m.when), default=None)
    out.events.append(_event(person_id, "told", item.name, domain="relationship",
                             event_type="social_connectedness", when=last.date().isoformat() if last else None,
                             text="social connectedness, measured from a chat export",
                             confidence=0.6, payload={"activity_proxy": signal}))
    chunks, truncated = chat.chunks_for_extraction(messages, owner)
    for chunk in chunks:
        got = _extract(person_id, "told", item, chunk, "the sender labelled Me" if owner else display_name)
        out.events += got.events
        out.personality = personality.merge(out.personality, got.personality)
    # `messages`, `chunks` and `item.text` go out of scope here; none of it was stored.
    item.text = ""
    out.outcome = "Conversations read for their shape, then let go. Only what happened was kept."
    if truncated:
        out.outcome += " The most recent stretch was read; the older pages were left closed."
    return out


def _process(person_id: str, item: Offered, display_name: str, live_source: Optional[str],
             allowed: dict[str, str]) -> Produced:
    if item.kind in ("handles", "link"):
        source = item.source or "link"
        key = source if item.kind == "handles" else f"link:{item.url}"
        if allowed.get(key) != item.url:  # consent gate: not a self-submitted row, not crawled
            return Produced(outcome="Set aside.")
        live = item.kind == "link" or live_source in (None, source)
        return _from_pages(person_id, item, links.load(person_id, source, item.url, live), display_name)

    if item.kind == "chat_export":
        return _from_chat(person_id, item, display_name)

    if item.kind == "personality":
        found = personality.from_big_five(item.text) or personality.from_mbti(item.text)
        out = _extract(person_id, "told", item, item.text, display_name) if len(item.text) > 400 else Produced()
        out.personality = personality.merge(out.personality, found)
        out.outcome = (f"{found.mbti}. Hereafter will keep that in mind." if found and found.mbti
                       else "A sense of your temperament, kept.")
        return out

    if item.kind == "unknown" and not item.text:
        return Produced(events=[_freeform(person_id, "told", item.name, f"offered: {item.name}", 0.15)],
                        outcome="Hereafter could not read this one, but it remembers that you brought it.")

    # freeform, resume, and unknown-with-text share the plain path
    out = _extract(person_id, "told", item, item.text, display_name)
    if not out.events:
        out.events.append(_freeform(person_id, "told", item.name, item.text))
    out.outcome = {"resume": "Your working life, read and set along the trunk."}.get(item.kind, "Heard, and kept.")
    typed = personality.from_big_five(item.text) or personality.from_mbti(item.text)
    if typed:  # a type or trait scores mentioned in passing still count
        out.personality = personality.merge(out.personality, typed)
    if len(item.text) > MAX_TEXT_CHARS:
        out.outcome += " It was long; Hereafter read the opening stretch and stopped there."
    return out


def ingest(store: EventStore, person_id: str, display_name: str, text: str, handles: dict[str, str],
           link_list: list[str], files: list[tuple[str, bytes]], live_source: Optional[str]) -> dict:
    offered = route(text, handles, link_list, files)

    # Record what this person submitted about themselves, then read the allow-list back from
    # the same table the crawler is gated on.
    for item in offered:
        if item.kind == "handles":
            db.record_handle(person_id, person_id, item.source, item.url)
        elif item.kind == "link":
            db.record_handle(person_id, person_id, f"link:{item.url}", item.url)
    allowed = db.submitted_handles(person_id)

    added: list[LifeEvent] = []
    inputs = []
    estimate: Optional[Personality] = None
    birth_year = None
    for item in offered:
        try:
            produced = _process(person_id, item, display_name, live_source, allowed)
        except Exception:
            log.exception("ingest of %s failed; keeping it as freeform", item.name)
            produced = Produced(events=[_freeform(person_id, "told", item.name, item.text or item.name, 0.2)],
                                outcome="Kept as it came.")
        added += store.append(produced.events)  # INDEX
        estimate = personality.merge(estimate, produced.personality)
        birth_year = birth_year or produced.birth_year
        inputs.append({"name": item.name, "kind": item.kind, "outcome": produced.outcome})

    return {"events_added": added, "inputs": inputs, "personality": estimate, "birth_year": birth_year}
