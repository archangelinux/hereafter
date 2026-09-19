"""Evidence: what a branch rests on. Three kinds —
  researched  a fact about the option read from the live web (written by research.py)
  statistic   the published table behind a simulated event, and how the thousand runs spread
  personal    a real event on main that the narrative calls back to
"""

from __future__ import annotations

import re
from datetime import date
from functools import lru_cache
from hashlib import sha1

from . import config
from .models import Branch, BranchYear, Evidence, LifeEvent
from .sim.engine import CITY_PROVINCE as _CANADIAN

EVENT_TABLE = {
    "death": "mortality.csv", "widowed": "mortality.csv", "parent_death": "mortality.csv",
    "marriage": "first_marriage.csv", "peer_wedding": "first_marriage.csv", "divorce": "divorce.csv",
    "birth": "fertility.csv", "peer_child": "fertility.csv", "job_change": "job_tenure.csv",
    "income_up": "income.csv", "income_down": "income.csv", "home_purchase": "homeownership.csv",
    "city_move": "migration.csv", "emigration": "migration.csv",
}
EVENT_ASPECT = {
    "death": "alive", "marriage": "relationship", "divorce": "relationship", "widowed": "relationship",
    "birth": "children", "job_change": "employment", "income_up": "income_band", "income_down": "income_band",
    "home_purchase": "housing", "city_move": "city", "emigration": "city",
}
TABLE_MEANING = {
    "mortality.csv": "the chance of dying at each age",
    "first_marriage.csv": "how often unmarried people of each age marry in a year",
    "divorce.csv": "how often marriages of each length end in a year",
    "fertility.csv": "births per woman at each age",
    "job_tenure.csv": "how long people of each age have held their job, which gives the yearly rate of starting a new one",
    "income.csv": "the spread of employment income by field of study and age",
    "homeownership.csv": "the share of households that own their home, by age and income",
    "migration.csv": "how often people of each age move province or leave the country in a year",
}


@lru_cache(maxsize=1)
def sources() -> dict[str, dict[str, str]]:
    """data/SOURCES.md, parsed: file -> {title, pid, url, period}."""
    path = config.DATA_DIR / "SOURCES.md"
    out: dict[str, dict[str, str]] = {}
    if not path.exists():
        return out
    for section in re.split(r"^## ", path.read_text(), flags=re.M)[1:]:
        m = re.match(r"\d+\.\s+(\S+\.csv)", section)
        if not m:
            continue
        flat = re.sub(r"\s+", " ", section)
        pid = re.search(r"\*\*(\d{2}-\d{2}-\d{4}(?:-\d{2})?)\*\*", flat)
        title = re.search(r'"([^"]{10,300})"', flat)
        url = re.search(r"https?://\S+", flat)
        period = re.search(r"Reference period:\s*\*\*([^*]+)\*\*", flat)
        out[m.group(1)] = {
            "pid": pid.group(1) if pid else "", "title": title.group(1) if title else m.group(1),
            "url": url.group(0).rstrip(".,)") if url else "", "period": period.group(1) if period else "",
        }
    return out


def _id(*parts: str) -> str:
    return "ev_" + sha1("|".join(parts).encode()).hexdigest()[:14]


def statistic_id(branch: Branch, event_type: str):
    table = EVENT_TABLE.get(event_type)
    return _id(branch.id, str(branch.revision), table) if table else None


POPULATION = "Canadians of this age, national average"
GAP_HERE = ("A national average for everyone of this age: it knows nothing about this person beyond age "
            "(and, for income and housing, field and income band), and it reads today's cross-section as if it were a future.")
GAP_ABROAD = ("A Canadian national average applied to a life outside Canada, because no equivalent table is loaded; "
              "treat it as the loosest kind of guide. It is sampled from the widest band.")


def statistic_evidence(branch: Branch, years: list[BranchYear]) -> list[Evidence]:
    """One document per published table that the branch's visible events rest on."""
    by_table: dict[str, list[tuple[LifeEvent, BranchYear]]] = {}
    for y in years:
        for e in y.events:
            table = EVENT_TABLE.get(e.event_type)
            if table:
                by_table.setdefault(table, []).append((e, y))
    out = []
    for table, uses in by_table.items():
        src = sources().get(table, {})
        event, year = uses[0]
        aspect = EVENT_ASPECT.get(event.event_type)
        spread = year.outlook.get(aspect) if aspect else None
        kinds = sorted({e.event_type.replace("_", " ") for e, _ in uses})
        claim = f"Behind {', '.join(kinds)} on this path: {TABLE_MEANING[table]}."
        out.append(Evidence(
            id=_id(branch.id, str(branch.revision), table), person_id=branch.person_id, branch_id=branch.id,
            kind="statistic", claim=claim,
            value=f"{spread.share:.0%} of the simulated lives agree on “{spread.value}” in {year.year}" if spread else None,
            unit=None,
            source_title=f"Statistics Canada, table {src.get('pid', '')}: {src.get('title', table)}"
                         + (f" ({src['period']})" if src.get("period") else ""),
            source_url=src.get("url") or None, retrieved_at="2026-09-19",
            snippet=None, used_for=f"yearly chances sampled from data/{table}",
            reference_class=POPULATION,
            gap=GAP_HERE if (branch.assumption.get("city") or branch.fork.get("city", "")).lower() in _CANADIAN else GAP_ABROAD,
        ))
    return out


def personal_evidence(branch: Branch, event: LifeEvent) -> Evidence:
    return Evidence(
        id=_id(branch.id, "personal", event.id), person_id=branch.person_id, branch_id=branch.id, kind="personal",
        claim=event.text, value=None, unit=None,
        source_title={"scraped": "your public footprint", "told": "something you told Hereafter",
                      "passive": "your calendar"}.get(event.source, "your life so far"),
        source_url=None, retrieved_at=event.date[:10] or date.today().isoformat(), snippet=None, used_for=None,
    )
