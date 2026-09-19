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
    # Merge into what is already stored: earlier, hand-reviewed results are kept; this run only adds.
    out: dict = json.loads(seed.SEED_DATA.read_text()) if seed.SEED_DATA.exists() else {"branches": {}}
    out["researched_on"] = date.today().isoformat()
    for branch, _ in db.list_branches(seed.DEMO_ID):  # let research replace the seeded placeholder if it can
        if branch.params.pop("housing_cost_ratio", None):
            db.save_branch(branch)
    for scenario in db.list_scenarios(seed.DEMO_ID):
        if scenario.status != "open":
            continue
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
            kept = out["branches"].setdefault(f"{scenario.id}|{branch.label}", {"params": {}, "rates": [], "facts": []})
            new_rates = [r for r in rates if r["event_key"] not in {k["event_key"] for k in kept["rates"]}]
            new_facts = [f for f in facts if (f["source_url"], f["claim"]) not in {(k["source_url"], k["claim"]) for k in kept["facts"]}]
            kept["rates"] += new_rates
            kept["facts"] += new_facts
            kept["params"] = {**researched, **kept["params"]}
            print(scenario.id, "|", branch.label, "| new:", len(new_rates), "rates,", len(new_facts), "facts | total:",
                  len(kept["rates"]), "rates,", len(kept["facts"]), "facts")
            for r in new_rates:
                print("    NEW RATE", r["event_key"], r["figure"], r["source_url"], "|", r["claim"][:110], "| gap:", (r["gap"] or "")[:90])
    seed.SEED_DATA.parent.mkdir(exist_ok=True)
    seed.SEED_DATA.write_text(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
