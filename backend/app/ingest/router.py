"""Step 1 of the universal pipeline: look at each thing offered and give it one label.

    handles | link | freeform | chat_export | resume | personality | unknown

Classification is rule-based, so routing works with the LLM off. A new source type is a new
label here; nothing downstream changes, because every label ends in the same extraction call.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field

from .. import personality
from . import chat

URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")
RESUME_HEADINGS = re.compile(
    r"^\s*(experience|work experience|employment|education|skills|projects|summary|objective)\s*:?\s*$",
    re.I | re.M,
)
MAX_ZIP_MEMBERS = 40
MAX_MEMBER_BYTES = 20_000_000


@dataclass
class Offered:
    name: str
    kind: str                      # one of the labels above
    text: str = ""                 # decoded content (never persisted for chat exports)
    url: str = ""
    source: str = ""               # for handles: github | linkedin | site | instagram
    notes: list[str] = field(default_factory=list)


def classify_text(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return "unknown"
    if chat.looks_like_chat(stripped):
        return "chat_export"
    # Only a bare result is 'personality'; a life story that mentions a type is still a story.
    has_type = personality.from_mbti(stripped) is not None and len(stripped) < 80
    if has_type or personality.from_big_five(stripped) is not None:
        return "personality"
    if len(RESUME_HEADINGS.findall(stripped)) >= 2:
        return "resume"
    return "freeform"


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            text = data.decode(enc)
        except UnicodeDecodeError:
            continue
        # Binary decoded as latin-1 is mostly control characters; treat that as unreadable.
        printable = sum(ch.isprintable() or ch in "\n\r\t" for ch in text[:4000])
        if printable >= 0.9 * max(1, len(text[:4000])):
            return text
    return ""


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def route_file(name: str, data: bytes) -> list[Offered]:
    lower = name.lower()
    try:
        if lower.endswith(".zip") or data[:4] == b"PK\x03\x04":
            out: list[Offered] = []
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                members = [m for m in z.infolist() if not m.is_dir()]
                readable = [m for m in members if m.filename.lower().endswith((".txt", ".json", ".html", ".md", ".pdf"))]
                for m in readable[:MAX_ZIP_MEMBERS]:
                    if m.file_size <= MAX_MEMBER_BYTES:
                        out += route_file(f"{name}/{m.filename}", z.read(m))
            return out or [Offered(name, "unknown", notes=["an archive with nothing readable inside"])]
        if lower.endswith(".pdf") or data[:5] == b"%PDF-":
            text = _pdf_text(data)
            kind = classify_text(text)
            return [Offered(name, "resume" if kind == "freeform" else kind, text)]
        text = _decode(data)
    except Exception:
        text = ""
    if not text.strip():
        return [Offered(name, "unknown")]
    return [Offered(name, classify_text(text), text)]


def route(text: str, handles: dict[str, str], links: list[str], files: list[tuple[str, bytes]]) -> list[Offered]:
    offered: list[Offered] = []
    for source, handle in handles.items():
        if handle and handle.strip():
            offered.append(Offered(f"{source}: {handle.strip()}", "handles", url=handle.strip(), source=source))
    seen = set()
    for url in [*links, *URL_RE.findall(text or "")]:
        url = url.rstrip(".,;")
        if url not in seen:
            seen.add(url)
            offered.append(Offered(url, "link", url=url))
    words = URL_RE.sub("", text or "").strip()
    if words:
        offered.append(Offered("your words", classify_text(words), words))
    for name, data in files:
        offered += route_file(name, data)
    return offered
