"""A demo person so the page is never empty, and so the demo survives bad wifi. Everything
here is marked as seeded; none of it was researched live."""

from __future__ import annotations

import copy
import json
import uuid
from datetime import date, datetime
from hashlib import sha1
from pathlib import Path

from . import branches, db, llm, outcome_model
from .models import Evidence, Horizon, LifeEvent, Option, Person, Scenario
from .state import build_state

DEMO_ID = "demo"

def _ev(key, label, domain, kind, window, bin_, depends_on=(), ref=None, query=None, follow=False):
    return {"key": key, "label": label, "domain": domain, "kind": kind, "window": list(window), "bin": bin_,
            "probability": None, "basis": "estimated", "evidence_id": None, "words": bin_, "band": 0.0,
            "depends_on": [{"key": k, "relation": r} for k, r in depends_on],
            "reference_class": ref, "search_query": query, "follow_through": follow}


# (date, domain, event_type, text, payload)
DEMO_TRUNK = [
    ("2022-09-06", "career", "education", "began a computer science degree at Waterloo",
     {"city": "Waterloo", "education": "bachelor's in progress", "field": "math_cs", "employment": "student"}),
    ("2022-09-03", "housing", "city_move", "moved from Mississauga to Waterloo",
     {"to": "Waterloo", "housing": "renting"}),
    ("2023-05-08", "career", "job_start", "first co-op term, a payments startup in Toronto", {}),
    ("2024-01-15", "career", "project", "first open-source project to find strangers", {}),
    ("2024-09-04", "career", "job_start", "co-op term at a robotics lab", {"employment": "student"}),
    ("2025-06-21", "relationship", "social_activity", "stood up at a cousin's wedding", {"relationship_status": "single"}),
    ("2026-05-04", "career", "job_start", "final co-op term, infrastructure team, San Francisco",
     {"employment": "student"}),
    ("2026-09-12", "career", "decision_pending", "a return offer arrived from San Francisco", {}),
]
# The big scenario's own plot, also a stored fixture of honest "estimated" bins (steps are years).
OFFER_EVENTS = [
    _ev("room_on_a_train_line", "you find a room on a train line, with two strangers", "home", "one_time", (0, 0), "usually"),
    _ev("visa_paperwork_drags", "the visa paperwork drags and your start date moves", "work", "one_time", (0, 0), "sometimes"),
    _ev("on_call_burnout", "a long on-call stretch leaves you flat for months", "mind", "one_time", (0, 4), "as often as not",
        ref="burnout prevalence among software engineers", query="software developer burnout prevalence survey percent"),
    _ev("layoff_round", "a layoff round reaches your team", "work", "one_time", (0, 6), "sometimes",
        ref="annual layoff and discharge rates among US information-sector workers",
        query="BLS JOLTS layoffs and discharges rate information sector annual percent"),
    _ev("promoted_to_senior", "you are promoted to senior", "work", "one_time", (2, 6), "as often as not",
        [("layoff_round", "less_likely")]),
    _ev("miss_home_badly", "you miss home badly enough to price flights most weeks", "family", "recurring", (0, 2), "sometimes"),
    _ev("friends_outside_work", "you have friends who are not from work", "friends", "state", (1, 5), "as often as not"),
    _ev("move_back_to_canada", "you move back to Canada", "home", "one_time", (3, 12), "sometimes", [("layoff_round", "likelier")],
        ref="return migration rates among Canadian emigrants", query="Statistics Canada returning emigrants share return within years"),
    _ev("start_something", "you leave to start something with a colleague", "work", "one_time", (4, 12), "rare",
        [("promoted_to_senior", "likelier")]),
    _ev("wonder_about_the_masters", "you catch yourself wondering about the master's you did not do", "mind", "recurring", (0, 8), "sometimes"),
]
MASTERS_EVENTS = [
    _ev("keep_the_apartment", "you keep the apartment and the same roommates", "home", "one_time", (0, 0), "usually"),
    _ev("ta_covers_rent", "the TA money covers rent, barely", "money", "state", (0, 1), "usually"),
    _ev("thesis_topic_changes", "your thesis topic changes under you", "learning", "one_time", (0, 1), "as often as not"),
    _ev("paper_accepted", "a paper with your name on it is accepted", "learning", "one_time", (1, 2), "sometimes"),
    _ev("finish_on_time", "you finish in the two years", "learning", "one_time", (1, 2), "usually", follow=True,
        ref="completion rates and times for Canadian master's students", query="master's degree completion rate Canada universities percent time to completion"),
    _ev("offer_comes_back", "the San Francisco team asks again when you graduate", "work", "one_time", (1, 2), "sometimes"),
    _ev("stay_for_the_phd", "you stay on for the PhD", "learning", "one_time", (2, 3), "rare", [("paper_accepted", "likelier")],
        ref="share of master's graduates who go on to doctoral study", query="percentage of master's graduates who pursue a doctorate Canada National Graduates Survey"),
    _ev("job_in_toronto", "you take a job in Toronto and move down the highway", "work", "one_time", (2, 4), "as often as not",
        [("stay_for_the_phd", "prevents")]),
    _ev("friends_leave_town", "most of your year has left Waterloo", "friends", "state", (0, 2), "usually"),
    _ev("wonder_about_the_offer", "you catch yourself wondering about the offer you turned down", "mind", "recurring", (0, 8), "sometimes"),
]


DEMO_SITUATION = ("A return offer arrived from San Francisco, from the infrastructure team I spent the summer with. "
                  "I could also stay in Waterloo for the master's. They want an answer within two weeks.")
DEMO_OPTIONS = [
    # (title, details, deadline, assumption, params)
    ("Take the offer",
     "Move to San Francisco in the new year and join the infrastructure team full time. US$165,000 base. "
     "Find a room somewhere on a train line.",
     "2026-09-26",
     {"city": "San Francisco", "country": "United States", "employment": "employed", "field": "math_cs",
      "occupation": "software engineer", "salary": 165000, "currency": "USD"},
     {"salary": 226050, "salary_source": "the offer as you described it", "housing_cost_ratio": 1.9}, OFFER_EVENTS),
    ("Stay for the master's",
     "Stay in Waterloo for the two-year MMath, keep the apartment with the same roommates, TA to cover rent.",
     None,
     {"city": "Waterloo", "country": "Canada", "employment": "student", "field": "math_cs",
      "program": "MMath, computer science", "institution": "University of Waterloo", "graduates_in": 2},
     {"graduates_in": 2}, MASTERS_EVENTS),
]
# Canned, clearly marked: used only so the demo has margin notes without touching the network.
DEMO_EVIDENCE = [
    (0, "The offer you described: a base salary of US$165,000.", "165,000", "USD per year",
     "your own description of the offer", None,
     "starting income: placed at this pay within the published income spread for your field and age"),
    (0, "Seeded placeholder: homes in San Francisco cost roughly twice the Canadian national picture.", None, None,
     "seeded for the demo — not researched", None,
     "how hard buying a home is here, relative to the national picture behind the ownership table"),
    (1, "The program you described runs two years.", "2", "years",
     "your own description of the program", None, "how many years of study come before work begins"),
]


# The second demo scenario is deliberately small. Its outcome model is a stored fixture: every
# likelihood is an honest "estimated" bin, because none of it was researched.
SMALL_SITUATION = ("There's a housewarming across town tonight and everyone from first year will be there. "
                   "My algorithms problem set is due at nine tomorrow morning and I've done one question of five.")
SMALL_HORIZON = Horizon(unit="days", count=7, tonight=True)


SMALL_OPTIONS = [
    ("Go to the housewarming", "Go for a couple of hours, come back by eleven, finish the set after.", [
        _ev("home_by_eleven", "you are home by eleven, as planned", "play", "one_time", (0, 0), "sometimes"),
        _ev("sleep_under_five_hours", "you sleep under five hours", "body", "one_time", (0, 0), "usually",
        ref="short sleep among university students on nights out or before deadlines", query="percent of university students sleeping less than 5 hours survey"),
        _ev("problem_set_on_time", "the problem set goes in on time", "learning", "one_time", (1, 1), "as often as not",
            [("home_by_eleven", "likelier")], ref="on-time assignment submission rates among undergraduates",
            query="proportion of university students who submit assignments late procrastination study percent"),
        _ev("problem_set_full_marks", "you get full marks on it", "learning", "one_time", (5, 6), "rare",
            [("problem_set_on_time", "requires")]),
        _ev("regret_next_morning", "you wake up wishing you had chosen differently", "mind", "one_time", (1, 1), "as often as not",
            [("problem_set_on_time", "less_likely")]),
        _ev("reconnect_with_old_friend", "someone you had lost touch with asks for your number", "friends", "one_time", (0, 0), "sometimes"),
        _ev("plans_next_weekend", "the night turns into plans for next weekend", "friends", "one_time", (1, 6), "sometimes",
            [("reconnect_with_old_friend", "likelier")]),
        _ev("ask_for_extension", "you email to ask for an extension", "learning", "one_time", (1, 1), "sometimes",
            [("problem_set_on_time", "prevents")], ref="share of undergraduates who request assignment extensions",
            query="how many university students request assignment deadline extensions percent study"),
        _ev("meet_someone", "you talk to a stranger in the kitchen for an hour", "love", "one_time", (0, 0), "rare"),
    ]),
    ("Stay in and finish the problem set", "Phone in the other room, tea, the whole set done properly tonight.", [
        _ev("problem_set_on_time", "the problem set goes in on time", "learning", "one_time", (0, 1), "usually", follow=True,
        ref="on-time assignment submission rates among undergraduates", query="percentage of undergraduate assignments submitted on time study"),
        _ev("problem_set_full_marks", "you get full marks on it", "learning", "one_time", (5, 6), "sometimes",
            [("problem_set_on_time", "requires")]),
        _ev("sleep_under_five_hours", "you sleep under five hours", "body", "one_time", (0, 0), "sometimes"),
        _ev("regret_next_morning", "you wake up wishing you had chosen differently", "mind", "one_time", (1, 1), "sometimes"),
        _ev("watch_the_stories", "you watch the party happen on your phone anyway", "mind", "one_time", (0, 0), "as often as not",
        ref="fear of missing out among university students on social media", query="fear of missing out prevalence university students percent survey"),
        _ev("photos_without_you", "the group photo goes up without you in it", "friends", "one_time", (1, 2), "usually"),
        _ev("plans_next_weekend", "someone messages to say you were missed, and makes a plan", "friends", "one_time", (1, 6), "sometimes"),
        _ev("finish_early_go_late", "you finish by ten and go for the last hour after all", "play", "one_time", (0, 0), "rare",
            [("problem_set_on_time", "requires")]),
    ]),
]


SEED_DATA = Path(__file__).parent / "seed_data" / "demo_research.json"


def _stored(scenario_id: str, title: str) -> dict:
    """Research that was really run once for the demo (scripts in seed_research.py) and kept, so a
    fresh database shows real sources without crawling again. Absent file = nothing researched."""
    if not SEED_DATA.exists():
        return {}
    return json.loads(SEED_DATA.read_text()).get("branches", {}).get(f"{scenario_id}|{title}", {})


def _researched(person_id: str, stored: dict, events: list[dict], unit: str):
    """extra_evidence hook: re-applies each stored published rate through outcome_model.apply_rate,
    so the figure-in-snippet check runs again at seed time, and returns the evidence documents."""
    def build(branch_id: str) -> list[Evidence]:
        out = []
        by_key = {e["key"]: e for e in events}
        for r in stored.get("rates", []):
            event = by_key.get(r["event_key"])
            if event is None:
                continue
            eid = "ev_" + sha1(f"{branch_id}|{r['source_url']}|{r['claim']}".encode()).hexdigest()[:14]
            rate = llm.PublishedRate(claim=r["claim"], figure_as_written=r["figure"], span_days=r.get("span_days"),
                                     snippet=r["snippet"], gap=r.get("gap") or "", gap_is_large=r.get("gap_is_large", True))
            arithmetic = outcome_model.apply_rate(event, rate, eid, unit)
            if arithmetic is None:
                continue
            out.append(Evidence(id=eid, person_id=person_id, branch_id=branch_id, kind="researched", claim=r["claim"],
                                value=r["figure"], source_title=r["source_title"], source_url=r["source_url"],
                                retrieved_at=r["retrieved_at"], snippet=r["snippet"], used_for=arithmetic,
                                question=r.get("reference_class"), figure=r["figure"], span_days=r.get("span_days"),
                                reference_class=r.get("reference_class"), gap=r.get("gap")))
        for f in stored.get("facts", []):
            eid = "ev_" + sha1(f"{branch_id}|{f['source_url']}|{f['claim']}".encode()).hexdigest()[:14]
            out.append(Evidence(id=eid, person_id=person_id, branch_id=branch_id, kind="researched", **f))
        return out
    return build


def _seed_small(person, fork, store) -> None:
    scenario = Scenario(id="demo-tonight", person_id=DEMO_ID, situation=SMALL_SITUATION, horizon=SMALL_HORIZON,
                        created_at=datetime.now().isoformat(timespec="seconds"),
                        options=[Option(id=uuid.uuid4().hex[:8], title=t, details=d) for t, d, _ in SMALL_OPTIONS])
    for option, (title, _, events) in zip(scenario.options, SMALL_OPTIONS):
        events = copy.deepcopy(events)
        stored = _stored(scenario.id, title)
        view = branches.create_branch(person, fork, title, {}, None, scenario_id=scenario.id, option_id=option.id,
                                      span=SMALL_HORIZON, events=events, research="done" if stored.get("rates") or stored.get("facts") else "none",
                                      extra_evidence=_researched(DEMO_ID, stored, events, SMALL_HORIZON.unit))
        scenario.branch_ids.append(view.branch.id)
    db.save_scenario(scenario)


def ensure_demo(store) -> None:
    if db.list_scenarios(DEMO_ID):  # event ids are deterministic, so a half-finished seed can simply rerun
        return
    store.erase(DEMO_ID)  # a fresh database: clear what earlier seeds of this synthetic person left in the indices
    person = db.upsert_person(Person(id=DEMO_ID, display_name="Demo", birth_year=2004))
    today = date.today().isoformat()
    events = [
        LifeEvent(id=sha1(f"demo|{when}|{kind}".encode()).hexdigest()[:16], person_id=DEMO_ID, source="scraped",
                  branch_id="main", date=when, domain=domain, event_type=kind, payload=payload,
                  confidence=0.9, text=text)
        for when, domain, kind, text, payload in DEMO_TRUNK if when <= today
    ]
    store.append(events)
    fork, _, _ = build_state(store, person, len(events))

    scenario = Scenario(id="demo-offer", person_id=DEMO_ID, situation=DEMO_SITUATION,
                        horizon=Horizon(unit="years", count=40), created_at=datetime.now().isoformat(timespec="seconds"),
                        options=[Option(id=uuid.uuid4().hex[:8], title=t, details=d, deadline=dl)
                                 for t, d, dl, _, _, _ in DEMO_OPTIONS])
    seeded = []
    for i, (option, (title, _, deadline, assumption, params, events)) in enumerate(zip(scenario.options, DEMO_OPTIONS)):
        events = copy.deepcopy(events)
        stored = _stored(scenario.id, title)
        params = {**params, **stored.get("params", {})}
        view = branches.create_branch(person, fork, title, assumption, f"decide_by: {deadline}" if deadline else None,
                                      scenario_id=scenario.id, option_id=option.id, params=params,
                                      span=Horizon(unit="years", count=40), events=events,
                                      research="done" if stored.get("rates") or stored.get("facts") else "none", script={"partner": False, "children": False, "home": False},
                                      extra_evidence=_researched(DEMO_ID, stored, events, "years"))
        scenario.branch_ids.append(view.branch.id)
        seeded += [
            Evidence(id=f"ev_demo_{i}_{n}", person_id=DEMO_ID, branch_id=view.branch.id, kind="researched",
                     claim=claim, value=value, unit=unit, source_title=source, source_url=url,
                     retrieved_at=today, snippet=None, used_for=used_for)
            for n, (which, claim, value, unit, source, url, used_for) in enumerate(DEMO_EVIDENCE)
            if which == i and not (claim.startswith("Seeded placeholder") and "housing_cost_ratio" in stored.get("params", {}))
        ]
    store.add_evidence(seeded)
    db.save_scenario(scenario)
    _seed_small(person, fork, store)
