"""Checks that keep the agent honest. Pure functions, no model.

Two ideas:

  * **Receipts.** Whenever the model claims something about the person (a score, a probability, a
    requirement it thinks is met), it must point at a context item and copy a phrase from it. Code
    checks the item exists and the phrase is really in it. No valid receipt, no claim: the number
    falls back to "cannot tell".
  * **Nothing new in the question.** A question may only mention numbers and names that already
    appear in the context, the decision, or the routes being compared.
"""

from __future__ import annotations

import re
from typing import Iterable

from .model import Choice, Cite, ContextItem

MIN_QUOTE_WORDS = 3
MAX_QUESTION_WORDS = 30
MAX_CHOICE_WORDS = 10
BANNED = re.compile(r"%|\bprobab|\blikelihood\b|\bodds\b|\bscore\b|\bjev\b", re.I)
NUMBER = re.compile(r"\d[\d,.]*")
CAPITALISED = re.compile(r"\b[A-Z][A-Za-z0-9+#.&'-]*[A-Za-z0-9+#]\b")
ALWAYS_OK = {"I", "I'm", "I've", "I'd", "I'll", "OK", "AI", "US", "UK", "CV"}


def norm(text: str) -> str:
    """Lower-case, letters and digits only, single spaces: so quoting survives punctuation and case."""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def valid_cites(cites: Iterable[Cite], items: dict[int, ContextItem]) -> list[Cite]:
    """The cites whose item exists and whose quote (three or more words) is literally in it."""
    good = []
    for c in cites:
        item = items.get(c.item)
        q = norm(c.quote)
        if item and len(q.split()) >= MIN_QUOTE_WORDS and q in norm(item.text):
            good.append(c)
    return good


def _sentence_starts(text: str) -> set[int]:
    starts, at_start = set(), True
    for m in re.finditer(r"\S+", text):
        if at_start:
            starts.add(m.start())
        at_start = m.group().endswith(("?", ".", "!", ":"))
    return starts


def unknown_mentions(question: str, allowed_text: str) -> list[str]:
    """Numbers and mid-sentence capitalised names in the question that appear nowhere in `allowed_text`."""
    haystack = norm(allowed_text)
    starts = _sentence_starts(question)
    missing = []
    for m in NUMBER.finditer(question):
        n = m.group().strip(".,")
        if n and n.replace(",", "") not in haystack.replace(",", ""):
            missing.append(n)
    for m in CAPITALISED.finditer(question):
        word = m.group()
        if m.start() in starts or word in ALWAYS_OK:
            continue
        if norm(word) not in haystack:
            missing.append(word)
    return sorted(set(missing))


def check_question(question: str, choices: list[Choice], grounding: list[Cite], items: dict[int, ContextItem],
                   allowed_text: str) -> list[str]:
    """Everything wrong with a written question, as short reasons. Empty means it may be asked."""
    problems = []
    words = question.split()
    if not words or len(words) > MAX_QUESTION_WORDS:
        problems.append(f"the question must be 1-{MAX_QUESTION_WORDS} words (it is {len(words)})")
    if question.count("?") != 1 or not question.strip().endswith("?"):
        problems.append("ask exactly one question, ending in a single question mark")
    if BANNED.search(question):
        problems.append("do not mention probabilities, percentages, odds or scores")
    if items and not valid_cites(grounding, items):
        problems.append("ground the question: cite at least one context item with a phrase copied exactly from it")
    invented = unknown_mentions(question, allowed_text)
    if invented:
        problems.append("these appear nowhere in the context or decision, so remove them: " + ", ".join(invented))
    if not 2 <= len(choices) <= 4:
        problems.append("give 2 to 4 answer choices")
    texts = [norm(c.text) for c in choices]
    if len(set(texts)) != len(texts):
        problems.append("answer choices must be different from each other")
    if any(len(c.text.split()) > MAX_CHOICE_WORDS or not c.text.strip() for c in choices):
        problems.append(f"each choice must be 1-{MAX_CHOICE_WORDS} words")
    return problems
