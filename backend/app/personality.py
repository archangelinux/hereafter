"""Personality estimates. Everything downstream works in Big Five z-scores; an MBTI type is
mapped onto them (low confidence) and kept only so it can be shown back to the person."""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel

MBTI_RE = re.compile(r"\b([EI])([NS])([TF])([JP])(?:-[AT])?\b")

# MBTI scale -> Big Five factor, with the scale/factor correlation reported by McCrae & Costa
# (1989). A letter says which side of the scale someone falls on, not how far, so each letter
# moves the matching trait by one SD scaled by that correlation. Neuroticism has no MBTI
# counterpart and stays at the mean. The four figures were checked against a secondary citation
# of the paper, not the paper itself (paywalled); see data/PERSONALITY_SOURCES.md.
MBTI_MAP = [
    # (position, letter that raises the trait, trait, |r|)
    (0, "E", "E", 0.74),
    (1, "N", "O", 0.72),
    (2, "F", "A", 0.44),
    (3, "J", "C", 0.49),
]
MBTI_CONFIDENCE = 0.3


class Personality(BaseModel):
    O: float = 0.0
    C: float = 0.0
    E: float = 0.0
    A: float = 0.0
    N: float = 0.0
    confidence: float = 0.0
    mbti: Optional[str] = None


def from_mbti(text: str) -> Optional[Personality]:
    m = MBTI_RE.search(text.upper())
    if not m:
        return None
    letters = m.groups()
    traits = {trait: (r if letters[pos] == up else -r) for pos, up, trait, r in MBTI_MAP}
    return Personality(**traits, confidence=MBTI_CONFIDENCE, mbti="".join(letters))


BIG5_NAMES = {
    "O": r"open(?:ness)?(?: to experience)?", "C": r"conscientious(?:ness)?",
    "E": r"extr[ao]ver(?:sion|ted|t)", "A": r"agreeable(?:ness)?",
    "N": r"neurotic(?:ism)?|emotional(?:ity| instability)",
}
BIG5_CONFIDENCE = 0.7


def from_big_five(text: str) -> Optional[Personality]:
    """Typed or pasted percentile results, e.g. 'Openness: 82, Conscientiousness 40%...'.
    Percentiles (0-100) become z-scores through a linear stand-in clipped to two SDs."""
    found = {}
    for trait, name in BIG5_NAMES.items():
        m = re.search(rf"(?:{name})\W{{0,12}}(\d{{1,3}})(?:\s*(?:%|/\s*100|th))?", text, re.I)
        if m and 0 <= int(m.group(1)) <= 100:
            found[trait] = max(-2.0, min(2.0, (int(m.group(1)) - 50) / 25))
    if len(found) < 3:
        return None
    return Personality(**found, confidence=BIG5_CONFIDENCE * len(found) / 5)


def merge(current: Optional[Personality], new: Optional[Personality]) -> Optional[Personality]:
    """Higher confidence wins the trait scores; an MBTI type, once given, is remembered."""
    if new is None:
        return current
    if current is None:
        return new
    best = new if new.confidence >= current.confidence else current
    return best.model_copy(update={"mbti": new.mbti or current.mbti})
