"""Chat exports: parsed in memory, measured, summarised into structured events, discarded.
Nothing in this module writes to disk, the cache, or the event store, and nothing it returns
for storage contains a message, a name, or a number that identifies a contact."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

# WhatsApp: "[2024-03-01, 9:15:02 PM] Name: text"  or  "3/1/24, 21:15 - Name: text"
LINE_RE = re.compile(
    r"^‎?\[?(\d{1,4}[/.-]\d{1,2}[/.-]\d{1,4}),?\s+(\d{1,2}:\d{2}(?::\d{2})?(?:\s?[APap]\.?[Mm]\.?)?)\]?"
    r"\s*(?:-\s*)?([^:]{1,60}):\s(.*)$"
)
DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%y", "%m/%d/%Y", "%d/%m/%y", "%d/%m/%Y", "%d.%m.%y", "%d.%m.%Y", "%Y/%m/%d")
CHUNK_CHARS = 40_000
MAX_CHUNKS = 3


@dataclass
class Message:
    when: datetime | None
    sender: str
    text: str


def looks_like_chat(text: str) -> bool:
    lines = text.splitlines()[:200]
    return len(lines) >= 5 and sum(bool(LINE_RE.match(l)) for l in lines) >= 0.4 * len(lines)


def _date(raw: str) -> datetime | None:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            pass
    return None


def parse(text: str) -> list[Message]:
    messages: list[Message] = []
    for line in text.splitlines():
        m = LINE_RE.match(line)
        if m:
            messages.append(Message(_date(m.group(1)), m.group(3).strip(), m.group(4)))
        elif messages:
            messages[-1].text += "\n" + line
    return messages


def owner_of(messages: list[Message], display_name: str) -> str:
    senders = {m.sender for m in messages}
    first = display_name.split()[0].lower() if display_name.strip() else ""
    for s in senders:
        if first and first in s.lower():
            return s
    return ""


def connectedness(messages: list[Message], owner: str) -> float:
    """0..1 social-connectedness signal: how many people, how often, lately. A proxy with
    hand-set scales — it feeds `activity_proxy` and tilts no simulated hazard."""
    dated = [m.when for m in messages if m.when]
    if not dated:
        return 0.0
    end = max(dated)
    recent = [m for m in messages if m.when and (end - m.when).days <= 84]
    contacts = {m.sender for m in recent if m.sender != owner}
    per_week = len(recent) / 12
    return round(min(1.0, 0.5 * min(1.0, per_week / 150) + 0.5 * min(1.0, len(contacts) / 8)), 3)


def _aliases(messages: list[Message], owner: str) -> dict[str, str]:
    """Everyone but the owner becomes Person A, Person B… before anything leaves this process."""
    others = list(dict.fromkeys(m.sender for m in messages if m.sender != owner))
    names = {s: f"Person {chr(65 + i % 26)}{i // 26 or ''}" for i, s in enumerate(others)}
    if owner:
        names[owner] = "Me"
    return names


def _scrub(text: str, names: dict[str, str]) -> str:
    for real, alias in names.items():
        for part in {real, *[w for w in real.split() if len(w) > 2]}:
            text = re.sub(rf"\b{re.escape(part)}\b", alias, text, flags=re.I)
    return text


def chunks_for_extraction(messages: list[Message], owner: str = "") -> tuple[list[str], bool]:
    """Most recent first, with other people's names replaced. Returns (chunks, whether older
    messages were left unread)."""
    names = _aliases(messages, owner)
    chunks, current, size = [], [], 0
    for m in reversed(messages):
        line = f"{m.when.date() if m.when else '?'} {names.get(m.sender, 'Person')}: {_scrub(m.text, names)}"
        if size + len(line) > CHUNK_CHARS and current:
            chunks.append("\n".join(reversed(current)))
            current, size = [], 0
            if len(chunks) == MAX_CHUNKS:
                return chunks, True
        current.append(line)
        size += len(line) + 1
    if current:
        chunks.append("\n".join(reversed(current)))
    return chunks, False
