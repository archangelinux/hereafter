"""What the agent knows about the person: a numbered list of things, each with a source.

Two ways in:
  * a fixture, a JSON file under `agent/fixtures/`, so runs are repeatable;
  * a person already in the app's store (Elastic, or the local SQLite stand-in), whose events came
    from LinkedIn, GitHub, Instagram, chat exports or their own words.

Numbers never change once given, so a question can point at "item 4" and a saved session stays
readable. Answers the person gives are appended as new items with source "told".
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Optional

from .model import ContextItem

FIXTURES = Path(__file__).parent / "fixtures"
SKIP_TYPES = {"breadcrumb", "social_connectedness", "state_fact"}
STOP = set("the and for with that this from have has had was were are you your our their they them what when who how why not but can will would could should into about over than then also just more most some any".split())


def fixture_names() -> list[str]:
    return sorted(p.stem for p in FIXTURES.glob("*.json"))


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9+#]{3,}", text.lower()) if t not in STOP}


class Context:
    def __init__(self, items: list[ContextItem], about: str = ""):
        self.items = items
        self.about = about

    # --- loading ---

    @classmethod
    def from_fixture(cls, name: str) -> "Context":
        path = FIXTURES / f"{name}.json"
        if not path.exists():
            raise SystemExit(f"no fixture called '{name}'. Available: {', '.join(fixture_names())}")
        raw = json.loads(path.read_text())
        items = [ContextItem(id=i + 1, source=it["source"], date=it.get("date", ""), text=it["text"].strip(),
                             confidence=float(it.get("confidence", 1.0))) for i, it in enumerate(raw["items"])]
        return cls(items, raw.get("about", ""))

    @classmethod
    def from_person(cls, person_id: str) -> "Context":
        from ..store import get_store

        rows = [e for e in get_store().events(person_id) if e.source != "simulated" and e.event_type not in SKIP_TYPES and e.text]
        items = []
        for i, e in enumerate(sorted(rows, key=lambda e: e.date)):
            origin = (getattr(e, "origin", "") or "").lower()
            src = "told" if e.source == "told" else next((s for s in ("linkedin", "github", "instagram") if s in origin), "other")
            items.append(ContextItem(id=i + 1, source=src, date=e.date[:10], text=e.text, confidence=e.confidence))
        if not items:
            raise SystemExit(f"no context found for person '{person_id}'. Ingest something first, or use --fixture.")
        return cls(items)

    # --- reading ---

    def by_id(self) -> dict[int, ContextItem]:
        return {i.id: i for i in self.items}

    def add_told(self, text: str) -> ContextItem:
        item = ContextItem(id=max((i.id for i in self.items), default=0) + 1, source="told", date=date.today().isoformat(), text=text.strip())
        self.items.append(item)
        return item

    def relevant(self, query: str, k: int = 30) -> list[ContextItem]:
        """The items that bear most on `query` (word overlap), plus everything the person told us
        directly. With a small context this is simply all of it. Returned in numbered order."""
        if len(self.items) <= k:
            return list(self.items)
        want = _tokens(query)
        told = [i for i in self.items if i.source == "told"]
        rest = sorted((i for i in self.items if i.source != "told"),
                      key=lambda i: (len(want & _tokens(i.text)) / (len(_tokens(i.text)) ** 0.5 or 1), i.date), reverse=True)
        return sorted(told + rest[: max(0, k - len(told))], key=lambda i: i.id)


def numbered(items: list[ContextItem]) -> str:
    """The context as the model sees it: '[3] (github, 2026-01) text'."""
    return "\n".join(f"[{i.id}] ({i.source}{', ' + i.date if i.date else ''}) {i.text}" for i in items) or "(nothing is known about this person yet)"


def load(fixture: Optional[str], person: Optional[str]) -> tuple["Context", str]:
    if fixture:
        return Context.from_fixture(fixture), f"fixture:{fixture}"
    if person:
        return Context.from_person(person), f"person:{person}"
    raise SystemExit("choose who this is about: --fixture NAME or --person ID")
