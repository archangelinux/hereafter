"""Exports of conversations with an AI assistant (Claude's `conversations.json`, ChatGPT's
`conversations.json`). These are often the richest record of what someone is turning over.

Only the person's OWN messages are read — the assistant's replies say nothing about their life
and are most of the bulk. Like other chat exports, the raw file is parsed in memory and dropped;
only structured events extracted from it are stored.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

CHUNK_CHARS = 40_000
MAX_CHUNKS = 6
MAX_MESSAGE_CHARS = 2_000   # a pasted document inside a message is not the person talking


@dataclass
class Conversation:
    title: str
    when: str               # ISO date of the last activity
    said: list[str]         # the person's messages only, in order


def _iso(value) -> str:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).date().isoformat()
    return str(value or "")[:10]


HUMAN = {"human", "user"}
MESSAGE_LISTS = ("chat_messages", "messages", "turns", "chat", "history")
CONVERSATION_LISTS = ("conversations", "chats", "data", "items", "threads")


def _text_of(message: dict) -> str:
    """The words of one message, across the shapes different exports use."""
    for key in ("text", "body"):
        if isinstance(message.get(key), str) and message[key].strip():
            return message[key].strip()
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, dict):
        content = content.get("parts") or content.get("text") or []
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and part.get("type", "text") == "text" and isinstance(part.get("text"), str):
                parts.append(part["text"])
        return " ".join(parts).strip()
    return ""


def _role_of(message: dict) -> str:
    author = message.get("author")
    role = message.get("sender") or message.get("role") or (author.get("role") if isinstance(author, dict) else author) or ""
    return str(role).lower()


def _conversation(conv: dict) -> Conversation | None:
    messages = next((conv[k] for k in MESSAGE_LISTS if isinstance(conv.get(k), list)), None)
    if messages is None and isinstance(conv.get("mapping"), dict):  # ChatGPT: a tree of nodes
        nodes = [n.get("message") for n in conv["mapping"].values() if isinstance(n, dict) and n.get("message")]
        messages = sorted(nodes, key=lambda m: m.get("create_time") or 0)
    if messages is None:
        return None
    said = [t[:MAX_MESSAGE_CHARS] for m in messages if isinstance(m, dict) and _role_of(m) in HUMAN and (t := _text_of(m))]
    when = _iso(conv.get("updated_at") or conv.get("update_time") or conv.get("created_at") or conv.get("create_time"))
    return Conversation(str(conv.get("name") or conv.get("title") or conv.get("summary") or ""), when, said)


def _load(raw: str):
    try:
        return json.loads(raw)
    except ValueError:
        pass
    rows = []  # JSON Lines: one conversation (or message) per line
    for line in raw.splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except ValueError:
                return None
    return rows or None


def parse(raw: str) -> list[Conversation] | None:
    """Conversations, newest first, or None if this is not an assistant-chat export. Tolerant of
    the shapes in use: Claude's and ChatGPT's conversations files, JSON or JSON Lines, a bare list
    or one wrapped in an object."""
    data = _load(raw)
    if isinstance(data, dict):
        data = next((data[k] for k in CONVERSATION_LISTS if isinstance(data.get(k), list)), [data])
    if not isinstance(data, list) or not data:
        return None
    found = [c for c in (_conversation(c) for c in data if isinstance(c, dict)) if c is not None]
    if not found:
        return None
    conversations = [c for c in found if c.said]
    conversations.sort(key=lambda c: c.when, reverse=True)
    return conversations


def is_manifest(raw: str) -> bool:
    """An export's index file: it names the other files of the download and holds no messages."""
    data = _load(raw)
    if not isinstance(data, dict):
        return False
    listing = next((data[k] for k in ("files", "parts", "entries", "contents", "artifacts") if isinstance(data.get(k), (list, dict))), None)
    return listing is not None and parse(raw) is None


def shape(raw: str, depth: int = 3) -> str:
    """Field names only, never values: what is logged when a JSON upload is not recognised, so the
    parser can be taught a new export format without anyone reading the person's data."""
    def walk(node, d):
        if d == 0:
            return "…"
        if isinstance(node, dict):
            return {k: walk(v, d - 1) for k, v in list(node.items())[:25]}
        if isinstance(node, list):
            return [walk(node[0], d - 1)] if node else []
        return type(node).__name__
    data = _load(raw)
    return json.dumps(walk(data, depth))[:1500] if data is not None else "not JSON"


def flatten(raw: str, limit: int = 60_000) -> str:
    """Every string value in a JSON document, in order — for files such as an assistant's saved
    memories about the person, whose exact layout does not matter."""
    out: list[str] = []
    def walk(node):
        if isinstance(node, str):
            if len(node.strip()) > 3:
                out.append(node.strip())
        elif isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(_load(raw))
    return "\n".join(out)[:limit]


def chunks_for_extraction(conversations: list[Conversation]) -> tuple[list[str], int]:
    """Newest conversations first, packed into a few chunks. Returns (chunks, conversations left
    unread) so the outcome can say plainly how much was read."""
    chunks, current, size, read = [], [], 0, 0
    for conv in conversations:
        block = f"## {conv.when} — {conv.title or 'untitled'}\n" + "\n".join(f"- {line}" for line in conv.said)
        if size + len(block) > CHUNK_CHARS and current:
            chunks.append("\n\n".join(current))
            current, size = [], 0
            if len(chunks) == MAX_CHUNKS:
                return chunks, len(conversations) - read
        current.append(block[:CHUNK_CHARS])
        size += len(block)
        read += 1
    if current:
        chunks.append("\n\n".join(current))
    return chunks, len(conversations) - read
