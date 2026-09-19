"""Live smoke test for Jev + the probability logic, using your OPENAI_API_KEY from .env.

No Elastic, no Browserbase, no database: it judges a handful of hand-written events twice, once
with no personal record and once with a small one, and prints what changed.

    cd backend && .venv/bin/python scripts/try_jev.py
"""

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config, jev, llm, probability  # noqa: E402

EVENTS = [
    {"key": "admitted", "label": "you are admitted to the computer science program", "domain": "learning",
     "kind": "one_time", "window": [0, 0], "basis": "estimated", "bin": "sometimes",
     "reference_class": "admission rate for that program", "depends_on": [], "probability": None, "band": 0.0},
    {"key": "coop_term", "label": "you land a paid co-op term in second year", "domain": "work",
     "kind": "one_time", "window": [1, 2], "basis": "estimated", "bin": "as often as not",
     "reference_class": "co-op placement rate", "depends_on": [], "probability": None, "band": 0.0},
    {"key": "research_paper", "label": "you are a listed author on a research paper", "domain": "research",
     "kind": "one_time", "window": [2, 3], "basis": "estimated", "bin": "rare",
     "reference_class": "undergraduate authorship rates", "depends_on": [], "probability": None, "band": 0.0},
    {"key": "start_company", "label": "you start a company before graduating", "domain": "startup",
     "kind": "one_time", "window": [1, 3], "basis": "estimated", "bin": "rare",
     "reference_class": None, "depends_on": [], "probability": None, "band": 0.0},
    {"key": "afford_rent", "label": "you can comfortably afford rent without a loan", "domain": "money",
     "kind": "state", "window": [0, 3], "basis": "estimated", "bin": "sometimes",
     "reference_class": None, "depends_on": [], "probability": None, "band": 0.0},
]

RECORD = """- 2024-06-01: Graduated high school with a 94% average, Grade 12 calculus 96%.
- 2024-09-15: Built a Python web scraper and a small React app; both on GitHub with a few stars.
- 2025-01-10: Won second place at a regional hackathon.
- 2025-03-02: Told a friend they want to start a company someday but have never sold anything.
- 2025-05-20: Working part time at a grocery store, saving for tuition; parents cannot help with rent.
- 2025-06-11: Has never published anything or worked in a lab."""

ABOUT = "age 18, lives in Toronto, student, single, with family"
OPTION = "Waterloo. Computer science with co-op."


def run(record: str) -> list[dict]:
    events = copy.deepcopy(EVENTS)
    judged = jev.judge(events, ABOUT, OPTION, record)
    probability.assess_events(events)
    print(f"  Jev judged {judged}/{len(events)} events with the model")
    return events


def show(events: list[dict]) -> None:
    print(f"  {'event':<48} {'category':<17} {'fit':>4} {'exp':>4} {'diff':>4} {'acc':>4} {'ev':>3}  "
          f"{'base':>5} -> {'likely':>6}  {'range':<11} {'hard':<9} {'conf':>4}")
    for e in events:
        j, s = e["jev"], e["estimate"]
        rng = f"{s['low']:.0%}-{s['high']:.0%}"
        print(f"  {e['label'][:48]:<48} {s['category']:<17} {j['personal_fit']:>4} {j['experience_fit']:>4} "
              f"{j['difficulty']:>4} {j['accessibility']:>4} {j['evidence_strength']:>3}  "
              f"{s['base']['probability']:>5.0%} -> {s['likelihood']:>6.1%}  {rng:<11} {s['difficulty_label']:<9} {s['confidence']:>4.2f}")
        for p in j["prerequisites"]:
            print(f"      requires: {p['requirement']}  [{p['met']}] {p['basis']}")


if not (llm.enabled() and config.LLM_PROVIDER == "openai"):
    sys.exit("Set OPENAI_API_KEY in .env (and leave HEREAFTER_LLM=on) so this uses the live API.")

print(f"model: {config.LLM_FAST_MODEL} (effort {config.LLM_FAST_EFFORT or 'default'})\n")
print("1) Jev with NO personal record")
before = run("")
show(before)
print("\n2) Jev WITH a personal record")
after = run(RECORD)
show(after)

print("\nWhat the record changed (likelihood, before -> after):")
for b, a in zip(before, after):
    print(f"  {b['label'][:60]:<60} {b['estimate']['likelihood']:.1%} -> {a['estimate']['likelihood']:.1%}")
if all(e["jev"]["judged_by"] == "rules" for e in after):
    print("\nEvery event fell back to the neutral rules judgement: the API call failed. Re-run with "
          "  HEREAFTER_LLM_MODEL=<a model your key can use>  and check the warning above.")
