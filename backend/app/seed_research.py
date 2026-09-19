"""Run real research once for the demo's two scenarios and keep what survives the checks.

    cd backend && .venv/bin/python -m app.seed_research

Needs the LLM, Browserbase and a seeded `demo` in the configured database. Writes
app/seed_data/demo_research.json, which `seed.ensure_demo` loads on a fresh database so the
demo shows real, dated sources without crawling again.
"""

from __future__ import annotations

import json
from datetime import date

from . import db, research, seed
from .store import get_store


def main() -> None:
    store = get_store()
    seed.ensure_demo(store)
    out: dict = {"researched_on": date.today().isoformat(), "branches": {}}
    for branch, _ in db.list_branches(seed.DEMO_ID):  # let research replace the seeded placeholder if it can
        if branch.params.pop("housing_cost_ratio", None):
            db.save_branch(branch)
    for scenario in db.list_scenarios(seed.DEMO_ID):
        research.research_scenario(scenario)
        for branch, _ in db.list_branches(seed.DEMO_ID):
            if branch.scenario_id != scenario.id:
                continue
            large = {e["evidence_id"]: e.get("band", 0) > 0 for e in branch.model["events"] if e.get("evidence_id")}
            keys = {e["evidence_id"]: e["key"] for e in branch.model["events"] if e.get("evidence_id")}
            rates, facts = [], []
            for ev in store.evidence(seed.DEMO_ID, branch.id):
                if ev.kind != "researched" or ev.id.startswith("ev_demo_"):
                    continue
                if ev.figure and ev.id in keys:
                    rates.append({"event_key": keys[ev.id], "claim": ev.claim, "figure": ev.figure, "span_days": ev.span_days,
                                  "snippet": ev.snippet, "gap": ev.gap, "gap_is_large": large.get(ev.id, True),
                                  "reference_class": ev.reference_class, "source_title": ev.source_title,
                                  "source_url": ev.source_url, "retrieved_at": ev.retrieved_at})
                elif not ev.figure:
                    facts.append({k: getattr(ev, k) for k in ("claim", "value", "unit", "source_title", "source_url",
                                                              "retrieved_at", "snippet", "used_for")})
            researched = {k: v for k, v in branch.params.items() if k in ("housing_cost_ratio",) and any(f["used_for"] for f in facts)}
            out["branches"][f"{scenario.id}|{branch.label}"] = {"params": researched, "rates": rates, "facts": facts}
            print(scenario.id, "|", branch.label, "|", len(rates), "published rates,", len(facts), "facts, params", researched)
    seed.SEED_DATA.parent.mkdir(exist_ok=True)
    seed.SEED_DATA.write_text(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
