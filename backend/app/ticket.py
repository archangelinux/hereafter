"""A decision is written the way a commit message or a ticket is: one plain line, as the
person would say it. This module finds the situation and the things they could do inside it.

    Noor texted for the first time since March. Answer tonight, in the morning, or not at all?
    McMaster vs Waterloo vs UofT
    Lend my brother the money?            (the alternative is implied: don't)
    Friday                                 (a title line, then one option per line)
    - the party
    - the problem set

Plain rules first, so it works instantly and with the LLM off; a small extraction call only when
the rules cannot find two options (an implied yes/no, or prose that does not split cleanly).
"""

from __future__ import annotations

import re

from . import llm

BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.*\S)\s*$")
SPLIT = re.compile(r"\s+(?:vs\.?|versus)\s+|\s*/\s*|\s*;\s*|,?\s+or\s+|,\s+", re.I)
LEADS = re.compile(r"^(?:should i|do i|shall i|whether to|either|i could|i can)\s+", re.I)
MAX_OPTIONS = 4


def _clean(option: str) -> str:
    option = LEADS.sub("", option.strip().strip("?.!,;:").strip())
    return option[:1].upper() + option[1:] if option else ""


def _from_rules(text: str) -> tuple[str, list[str]]:
    lines = [l for l in text.strip().splitlines() if l.strip()]
    bullets = [m.group(1) for l in lines[1:] if (m := BULLET.match(l))]
    if len(bullets) >= 2:
        return lines[0].strip(), [_clean(b) for b in bullets][:MAX_OPTIONS]
    if len(lines) >= 3 and not bullets:  # a title line, then one option per line
        return lines[0].strip(), [_clean(l) for l in lines[1:]][:MAX_OPTIONS]

    flat = " ".join(lines)
    # the options are in the last sentence; whatever comes before it is the situation
    sentences = [s for s in re.split(r"(?<=[.!?:])\s+", flat) if s.strip()]
    last = sentences[-1] if sentences else flat
    if ":" in last and not sentences[:-1]:
        head, last = last.split(":", 1)
        sentences = [head + ":", last]
    parts = [_clean(p) for p in SPLIT.split(last) if _clean(p)]
    if 2 <= len(parts) <= 6:
        return flat.strip(), parts[:MAX_OPTIONS]
    return flat.strip(), []


def parse(text: str) -> tuple[str, list[str]]:
    """(situation, option titles). Always returns at least two options."""
    situation, options = _from_rules(text)
    if len(options) < 2:
        found = llm.extract_ticket(text)
        if found and len(found.options) >= 2:
            return found.situation or situation, [o.strip() for o in found.options][:MAX_OPTIONS]
    if len(options) < 2:
        # an implied yes/no: the thing itself, and not doing it
        action = _clean(situation) or "Do it"
        options = [action, "Leave it"]
    return situation, options
