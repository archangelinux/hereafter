"""The demo person: one coherent, simple story, so the page is never empty and the demo survives
bad wifi. A main that leads plausibly to the present; one big decision with three paths; one
small decision with two; and one earlier small decision already merged, so a chosen path and a
road not taken exist. Everything is a stored fixture except the research in seed_data/, which was
really run once (seed_research.py) and is re-verified every time the demo is seeded."""

from __future__ import annotations

import copy
import json
import uuid
from datetime import date, datetime, timedelta
from hashlib import sha1
from pathlib import Path

from . import branches, db, llm, outcome_model
from .models import Evidence, Horizon, LifeEvent, Option, Person, Scenario
from .personality import from_mbti
from .sim.outcomes import step_offsets, window_from_days
from .state import build_state

DEMO_ID = "demo"
DEMO_MBTI = "ENFP"


def _ev(key, label, domain, phase, days, bin_, after=(), requires=(), links=(), ref=None, query=None, follow=False,
        traits=(), hazard=None, kind="one_time"):
    """One possible event, exactly as the proposal step would give it: a moment, a window in days
    after the decision, what it must follow, and a verbal bin. `traits` are directions only."""
    return {"key": key, "label": label, "domain": domain, "kind": kind, "phase": phase, "days": list(days), "window": [0, 0],
            "bin": bin_, "base_probability": None, "basis": "estimated", "evidence_id": None, "words": bin_, "band": 0.0,
            "after": list(after), "requires": list(requires), "depends_on": [{"key": k, "relation": r} for k, r in links],
            "reference_class": ref, "search_query": query, "follow_through": follow, "hazard": hazard,
            "traits": [{"trait": t, "direction": d} for t, d in traits]}


def _model(events: list[dict], choice: str, span: Horizon, start: date) -> list[dict]:
    events = copy.deepcopy(events)
    offsets = step_offsets(span.unit, span.count, start)
    for e in events:
        e["window"] = window_from_days(offsets, *e["days"])
    outcome_model.repair(events)
    return outcome_model.ensure_head(events, choice)


NOW, SOON, LATER = "right_away", "settling_in", "later"

# ---------------------------------------------------------------- the big decision: three paths, three years
BIG_SPAN = Horizon(unit="years", count=3)
BIG_SITUATION = ("A return offer arrived from San Francisco, from the infrastructure team I spent the summer with: US$165,000, "
                 "starting in January. The Toronto payments startup from my first co-op wants me back too. Or I stay in Waterloo "
                 "for the master's. I have a week to answer.")

OFFER = ("Take the offer", "You accept the San Francisco offer",
         "Move to San Francisco in January and join the infrastructure team full time. US$165,000 base.", [
    _ev("sign_offer", "you sign the offer and tell your parents that evening", "work", NOW, (0, 6), "almost certainly"),
    _ev("visa_delay", "the visa paperwork drags and your start date slips", "work", NOW, (40, 100), "sometimes", requires=["sign_offer"]),
    _ev("move_cities", "you land at SFO with two suitcases", "home", NOW, (95, 130), "almost certainly", requires=["sign_offer"]),
    _ev("first_day_at_work", "your first day: a badge, a laptop, the same team room as the summer", "work", NOW, (100, 140), "almost certainly",
        requires=["move_cities"]),
    _ev("sign_lease", "you sign a lease on a room near a train line, with two strangers", "home", NOW, (100, 170), "almost certainly",
        requires=["move_cities"]),
    _ev("first_oncall", "your first week carrying the pager", "work", SOON, (150, 270), "almost certainly", requires=["first_day_at_work"]),
    _ev("price_flights_home", "one Sunday you price flights home and close the tab", "family", SOON, (130, 320), "as often as not",
        requires=["move_cities"], traits=[("N", 1)]),
    _ev("first_real_friend_there", "you make your first friend who has nothing to do with work", "friends", SOON, (150, 460),
        "as often as not", requires=["move_cities"], traits=[("E", 1)]),
    _ev("home_for_the_holidays", "you fly home for the holidays and your old room feels smaller", "family", SOON, (455, 470), "usually",
        requires=["move_cities"]),
    _ev("on_call_burnout", "a long on-call stretch leaves you flat for weeks", "mind", LATER, (270, 800), "as often as not",
        requires=["first_oncall"], traits=[("N", 1)], ref="burnout prevalence among software engineers",
        query="software developer burnout prevalence survey percent"),
    _ev("layoff_round", "a layoff round reaches your team", "work", LATER, (200, 1050), "sometimes", requires=["first_day_at_work"],
        ref="annual layoff and discharge rates among US information-sector workers",
        query="BLS JOLTS layoffs and discharges rate information sector annual percent"),
    _ev("promoted", "you are promoted to the next level", "work", LATER, (500, 1050), "as often as not", requires=["first_day_at_work"],
        links=[("layoff_round", "less_likely")], traits=[("C", 1)]),
    _ev("regret_the_choice", "one bad week you catch yourself wondering about the paths you did not take", "mind", LATER, (200, 1050),
        "sometimes", after=["first_day_at_work"], traits=[("N", 1)]),
    _ev("move_back_to_canada", "you give notice and move back to Canada", "home", LATER, (500, 1090), "rare", requires=["move_cities"],
        links=[("layoff_round", "likelier")], hazard="migration", ref="return migration rates among Canadian emigrants",
        query="Statistics Canada returning emigrants share return within years"),
])

MASTERS = ("Stay for the master's", "You accept the master's place and turn both jobs down",
           "Two-year MMath at Waterloo starting in January. Keep the apartment and the same roommates; TA to cover rent.", [
    _ev("email_the_no", "you write the two emails saying no, and send them before you can reread them", "work", NOW, (0, 6), "almost certainly"),
    _ev("renew_the_lease", "you and your roommates renew the lease on the same apartment", "home", NOW, (10, 70), "usually"),
    _ev("first_term_starts", "the first term starts, and you TA a first-year course", "learning", NOW, (100, 125), "almost certainly"),
    _ev("ta_pay_covers_rent", "the first TA pay lands and covers the rent, barely", "money", NOW, (125, 175), "usually",
        requires=["first_term_starts"]),
    _ev("friends_leave_town", "most of your year leaves town for jobs within the same month", "friends", SOON, (200, 270), "usually"),
    _ev("settle_a_thesis_topic", "you settle on a thesis topic with your supervisor", "learning", SOON, (150, 340), "usually",
        requires=["first_term_starts"]),
    _ev("first_real_friend_there", "you make a close friend in the grad lab", "friends", SOON, (130, 460), "as often as not",
        after=["first_term_starts"], traits=[("E", 1)]),
    _ev("topic_changes", "your thesis topic changes under you", "learning", LATER, (300, 620), "as often as not",
        requires=["settle_a_thesis_topic"]),
    _ev("paper_accepted", "a paper with your name on it is accepted", "learning", LATER, (400, 800), "sometimes",
        requires=["settle_a_thesis_topic"], traits=[("C", 1), ("O", 1)]),
    _ev("regret_the_choice", "one bad week you catch yourself wondering about the paths you did not take", "mind", LATER, (150, 800),
        "sometimes", after=["first_term_starts"], traits=[("N", 1)]),
    _ev("offer_comes_back", "the San Francisco team writes again as you near the end", "work", LATER, (600, 770), "sometimes"),
    _ev("finish_on_time", "you defend, and finish inside the two years", "learning", LATER, (700, 800), "usually",
        requires=["settle_a_thesis_topic"], links=[("topic_changes", "less_likely")], follow=True, traits=[("C", 1)],
        ref="completion rates and times for Canadian master's students",
        query="master's degree completion rate Canada universities percent time to completion"),
    _ev("stay_for_the_phd", "you stay on for the PhD", "learning", LATER, (760, 900), "rare", requires=["finish_on_time"],
        links=[("paper_accepted", "likelier")], traits=[("O", 1)],
        ref="share of master's graduates who go on to doctoral study",
        query="percentage of master's graduates who pursue a doctorate Canada National Graduates Survey"),
    _ev("first_day_at_work", "your first day at a job, with the degree behind you", "work", LATER, (800, 1050), "almost certainly",
        requires=["finish_on_time"], links=[("stay_for_the_phd", "prevents")]),
])

TORONTO = ("Take the Toronto job", "You accept the Toronto startup's offer",
           "Go back to the payments startup full time from January. C$95,000 and a small equity grant. Live in Toronto.", [
    _ev("sign_offer", "you sign with the Toronto startup and tell your parents that evening", "work", NOW, (0, 6), "almost certainly"),
    _ev("sign_lease", "you sign a lease on a small place off College Street", "home", NOW, (40, 105), "almost certainly", requires=["sign_offer"]),
    _ev("move_cities", "you move down the 401 in a rented van", "home", NOW, (85, 118), "almost certainly", requires=["sign_lease"]),
    _ev("first_day_at_work", "your first day back: the same office, a new desk, people who remember you", "work", NOW, (100, 125),
        "almost certainly", requires=["sign_offer"]),
    _ev("sunday_dinner", "the first Sunday dinner back at your parents', forty minutes away", "family", NOW, (105, 165), "usually",
        requires=["move_cities"]),
    _ev("first_launch", "a feature you built ships to every merchant", "work", SOON, (200, 430), "usually", requires=["first_day_at_work"],
        traits=[("C", 1)]),
    _ev("first_real_friend_there", "you make your first new friend in the city, at a climbing gym", "friends", SOON, (150, 500), "usually",
        requires=["move_cities"], traits=[("E", 1)]),
    _ev("recruiter_checks_in", "a recruiter from the San Francisco team checks in, a year on", "work", SOON, (350, 430), "as often as not",
        after=["first_day_at_work"]),
    _ev("missed_quarter", "the startup misses a quarter and there is talk of cuts", "work", LATER, (300, 1000), "sometimes",
        requires=["first_day_at_work"]),
    _ev("layoff_round", "the cuts reach your team", "work", LATER, (400, 1090), "sometimes", requires=["missed_quarter"]),
    _ev("funding_round", "the startup raises a round and your equity is worth something on paper", "money", LATER, (300, 1000),
        "sometimes", requires=["first_day_at_work"], links=[("missed_quarter", "less_likely")]),
    _ev("promoted", "you are made a team lead", "work", LATER, (450, 1050), "as often as not", requires=["first_launch"],
        links=[("layoff_round", "less_likely")], traits=[("C", 1)]),
    _ev("regret_the_choice", "one bad week you catch yourself wondering about the paths you did not take", "mind", LATER, (200, 1050),
        "sometimes", after=["first_day_at_work"], traits=[("N", 1)]),
    _ev("leave_for_the_states", "you take a job in the States after all", "work", LATER, (700, 1090), "rare", requires=["first_day_at_work"],
        links=[("recruiter_checks_in", "likelier")], hazard="migration"),
])
BIG_ASSUMPTIONS = {
    "Take the offer": ({"city": "San Francisco", "country": "United States", "employment": "employed", "field": "math_cs",
                        "occupation": "software engineer", "salary": 165000, "currency": "USD"}, {"salary": 226050}),
    "Stay for the master's": ({"city": "Waterloo", "country": "Canada", "employment": "student", "field": "math_cs",
                               "program": "MMath, computer science", "institution": "University of Waterloo", "graduates_in": 2},
                              {"graduates_in": 2}),
    "Take the Toronto job": ({"city": "Toronto", "country": "Canada", "employment": "employed", "field": "math_cs",
                              "occupation": "software engineer", "salary": 95000, "currency": "CAD"}, {"salary": 95000}),
}
OWN_WORDS = {  # evidence that is simply what the person said
    "Take the offer": ("The offer you described: a base salary of US$165,000.", "165,000", "USD per year"),
    "Stay for the master's": ("The program you described runs two years.", "2", "years"),
    "Take the Toronto job": ("The offer you described: C$95,000 and a small equity grant.", "95,000", "CAD per year"),
}

# ---------------------------------------------------------------- the small decision: two paths, one week
SMALL_SPAN = Horizon(unit="days", count=7, tonight=True)
SMALL_SITUATION = ("There's a housewarming across town tonight and everyone from first year will be there. "
                   "My algorithms problem set is due at nine tomorrow morning and I've done one question of five.")
GO = ("Go to the housewarming", "You go to the housewarming", "Go for a couple of hours, come back by eleven, finish the set after.", [
    _ev("arrive_at_the_party", "you get there at nine with a bag of chips", "play", NOW, (0, 0), "almost certainly"),
    _ev("reconnect_with_old_friend", "someone you had lost touch with asks for your number", "friends", NOW, (0, 0), "sometimes",
        requires=["arrive_at_the_party"], traits=[("E", 1)]),
    _ev("kitchen_conversation", "you talk to a stranger in the kitchen for an hour", "love", NOW, (0, 0), "rare",
        requires=["arrive_at_the_party"], traits=[("E", 1)]),
    _ev("home_by_eleven", "you leave when you said you would, and are home by eleven", "play", NOW, (0, 0), "sometimes",
        requires=["arrive_at_the_party"], traits=[("C", 1)]),
    _ev("work_past_two", "you are still on question three at two in the morning", "learning", NOW, (0, 1), "usually",
        after=["arrive_at_the_party"], links=[("home_by_eleven", "less_likely")]),
    _ev("sleep_under_five_hours", "you sleep under five hours", "body", NOW, (0, 1), "usually", after=["work_past_two"],
        links=[("home_by_eleven", "less_likely")]),
    _ev("problem_set_on_time", "the problem set goes in before nine", "learning", SOON, (1, 1), "as often as not",
        links=[("home_by_eleven", "likelier")], traits=[("C", 1)]),
    _ev("ask_for_extension", "you email to ask for an extension", "learning", SOON, (1, 1), "sometimes", after=["work_past_two"],
        links=[("problem_set_on_time", "prevents")]),
    _ev("regret_next_morning", "you wake up wishing you had chosen differently", "mind", SOON, (1, 1), "as often as not",
        links=[("problem_set_on_time", "less_likely")], traits=[("N", 1)]),
    _ev("plans_next_weekend", "someone from the party messages to make a plan for the weekend", "friends", LATER, (1, 6), "sometimes",
        requires=["arrive_at_the_party"], links=[("reconnect_with_old_friend", "likelier")], traits=[("E", 1)]),
    _ev("problem_set_full_marks", "the set comes back with full marks", "learning", LATER, (5, 6), "rare", requires=["problem_set_on_time"]),
])
STAY_IN = ("Stay in and finish the problem set", "You stay in with the problem set",
           "Phone in the other room, tea, the whole set done properly tonight.", [
    _ev("phone_in_the_other_room", "you put the phone in the other room and make tea", "learning", NOW, (0, 0), "almost certainly"),
    _ev("watch_the_stories", "you fetch the phone and watch the party happen on it anyway", "mind", NOW, (0, 0), "as often as not",
        after=["phone_in_the_other_room"], traits=[("N", 1), ("E", 1)],
        ref="fear of missing out among university students on social media",
        query="fear of missing out prevalence university students percent survey"),
    _ev("finish_by_ten", "you finish the last question by ten", "learning", NOW, (0, 0), "sometimes", after=["phone_in_the_other_room"],
        links=[("watch_the_stories", "less_likely")], traits=[("C", 1)]),
    _ev("go_for_the_last_hour", "you go for the last hour after all", "play", NOW, (0, 0), "rare", requires=["finish_by_ten"],
        traits=[("E", 1)]),
    _ev("sleep_under_five_hours", "you sleep under five hours", "body", NOW, (0, 1), "sometimes", links=[("finish_by_ten", "less_likely")]),
    _ev("problem_set_on_time", "the problem set goes in before nine", "learning", SOON, (1, 1), "usually", follow=True, traits=[("C", 1)]),
    _ev("photos_without_you", "the group photo goes up without you in it", "friends", SOON, (1, 2), "usually"),
    _ev("regret_next_morning", "you wake up wishing you had chosen differently", "mind", SOON, (1, 1), "sometimes",
        links=[("watch_the_stories", "likelier")], traits=[("N", 1)]),
    _ev("plans_next_weekend", "someone messages to say you were missed, and makes a plan for the weekend", "friends", LATER, (1, 6),
        "sometimes", after=["photos_without_you"], traits=[("E", 1)]),
    _ev("problem_set_full_marks", "the set comes back with full marks", "learning", LATER, (5, 6), "sometimes",
        requires=["problem_set_on_time"]),
])

# ---------------------------------------------------------------- an earlier small decision, already made
EARLIER_DAYS_AGO = 23
EARLIER_SPAN = Horizon(unit="days", count=5)
EARLIER_SITUATION = "Last night in San Francisco: the team's farewell dinner, or pack and sleep before the 6 a.m. flight home?"
DINNER = ("Go to the farewell dinner", "You go to the team's farewell dinner", "", [
    _ev("stay_until_closing", "you stay until the restaurant stacks the chairs", "friends", NOW, (0, 0), "as often as not"),
    _ev("manager_hints_at_offer", "over dessert your manager says an offer is coming", "work", NOW, (0, 0), "sometimes"),
    _ev("pack_at_two", "you pack at two in the morning, badly", "home", NOW, (0, 1), "usually"),
    _ev("sleep_under_four_hours", "you sleep under four hours", "body", NOW, (0, 1), "usually", after=["pack_at_two"]),
    _ev("make_the_flight", "you make the flight", "home", SOON, (1, 1), "almost certainly"),
    _ev("swap_numbers", "a teammate you barely knew swaps numbers with you on the way out", "friends", NOW, (0, 0), "as often as not"),
    _ev("feel_you_missed_goodbye", "on the plane you feel you left something unsaid", "mind", SOON, (1, 2), "rare"),
])
PACK = ("Pack and sleep", "You skip the dinner, pack and sleep", "", [
    _ev("packed_by_ten", "you are packed by ten", "home", NOW, (0, 0), "almost certainly"),
    _ev("full_night", "you sleep a full night before the flight", "body", NOW, (0, 1), "usually", after=["packed_by_ten"]),
    _ev("photos_from_dinner", "the team sends photos from the dinner", "friends", NOW, (0, 1), "usually"),
    _ev("make_the_flight", "you make the flight", "home", SOON, (1, 1), "almost certainly"),
    _ev("feel_you_missed_goodbye", "on the plane you feel you left something unsaid", "mind", SOON, (1, 2), "as often as not",
        after=["photos_from_dinner"]),
])


# What each moment means, as change from now: (health, joy, fulfilment, money), each -2..+2. Judgements, like the
# proposal step would make; zero for anything not listed. Keyed by event key; a path may override with (title, key).
EFFECTS = {
    "sign_offer": (0, 2, 0, 0), "move_cities": (0, 1, 0, 0), "first_day_at_work": (0, 1, 1, 2), "sign_lease": (0, 0, 0, 0),
    "first_oncall": (-1, -1, 0, 0), "price_flights_home": (0, -1, 0, 0), "first_real_friend_there": (0, 2, 1, 0),
    "home_for_the_holidays": (0, 1, 0, 0), "on_call_burnout": (-2, -2, -1, 0), "layoff_round": (-1, -2, -1, -1),
    "promoted": (0, 2, 1, 1), "regret_the_choice": (0, -1, -1, 0), "move_back_to_canada": (0, 0, 0, -1), "visa_delay": (0, -1, 0, -1),
    "email_the_no": (0, -1, 0, 0), "renew_the_lease": (0, 0, 0, 0), "first_term_starts": (0, 1, 1, 0), "ta_pay_covers_rent": (0, 0, 0, 0),
    "friends_leave_town": (0, -2, 0, 0), "settle_a_thesis_topic": (0, 1, 0, 0), "topic_changes": (0, -1, -1, 0),
    "paper_accepted": (0, 2, 2, 0), "offer_comes_back": (0, 1, 0, 0), "finish_on_time": (0, 2, 2, 0), "stay_for_the_phd": (0, 0, 1, -1),
    "sunday_dinner": (0, 1, 0, 0), "first_launch": (0, 2, 1, 0), "recruiter_checks_in": (0, 1, 0, 0), "missed_quarter": (-1, -1, 0, 0),
    "funding_round": (0, 1, 0, 1), "leave_for_the_states": (0, 1, 0, 1),
    "arrive_at_the_party": (0, 1, 0, 0), "reconnect_with_old_friend": (0, 2, 1, 0), "kitchen_conversation": (0, 2, 0, 0),
    "home_by_eleven": (1, 0, 0, 0), "work_past_two": (-1, -1, 0, 0), "sleep_under_five_hours": (-1, -1, 0, 0),
    "problem_set_on_time": (0, 1, 1, 0), "ask_for_extension": (0, -1, 0, 0), "regret_next_morning": (0, -2, 0, 0),
    "plans_next_weekend": (0, 1, 1, 0), "problem_set_full_marks": (0, 2, 1, 0), "phone_in_the_other_room": (0, 0, 0, 0),
    "watch_the_stories": (0, -1, 0, 0), "finish_by_ten": (0, 1, 1, 0), "go_for_the_last_hour": (0, 2, 0, 0), "photos_without_you": (0, -1, 0, 0),
    "stay_until_closing": (0, 2, 1, 0), "manager_hints_at_offer": (0, 2, 0, 0), "pack_at_two": (-1, -1, 0, 0),
    "sleep_under_four_hours": (-1, -1, 0, 0), "make_the_flight": (0, 0, 0, 0), "swap_numbers": (0, 1, 1, 0),
    "feel_you_missed_goodbye": (0, -1, -1, 0), "packed_by_ten": (0, 0, 0, 0), "full_night": (1, 0, 0, 0), "photos_from_dinner": (0, -1, 0, 0),
}
# The same moment can mean different things on different paths: (path title, event key) overrides the table above.
EFFECTS_ON_PATH = {("Stay for the master's", "first_day_at_work"): (0, 1, 1, 1), ("Take the Toronto job", "first_day_at_work"): (0, 1, 1, 1)}
CHOICE_EFFECTS = {"Take the offer": (0, 1, 0, 0), "Stay for the master's": (0, 0, 1, 0), "Take the Toronto job": (0, 1, 0, 0),
                  "Go to the housewarming": (0, 1, 0, 0), "Stay in and finish the problem set": (0, -1, 1, 0),
                  "Go to the farewell dinner": (0, 1, 0, 0), "Pack and sleep": (0, -1, 0, 0)}
# Real figures in the person's own words, attached to the moment they start: (title, event key) -> (value, currency, per)
OWN_AMOUNTS = {("Take the offer", "first_day_at_work"): (165000, "USD", "year"),
               ("Take the Toronto job", "first_day_at_work"): (95000, "CAD", "year")}
MEASURE_NAMES = ("health", "joy", "fulfilment", "money")


def trunk(today: date) -> list[tuple]:
    """(date, domain, event_type, text, payload): a past that leads plausibly to now."""
    ago = lambda days: (today - timedelta(days=days)).isoformat()
    return [
        ("2022-09-03", "housing", "city_move", "moved from Mississauga to Waterloo for university", {"to": "Waterloo", "housing": "renting"}),
        ("2022-09-06", "career", "education", "began a computer science degree at Waterloo",
         {"city": "Waterloo", "education": "bachelor's in progress", "field": "math_cs", "employment": "student"}),
        ("2023-05-08", "career", "job_start", "first co-op term, at a payments startup in Toronto", {}),
        ("2024-01-15", "career", "project", "an open-source scheduling library found its first strangers", {}),
        ("2025-01-06", "career", "job_start", "co-op term at a robotics lab on campus", {"employment": "student"}),
        ("2026-05-04", "career", "job_start", "final co-op term: the infrastructure team at a company in San Francisco",
         {"employment": "student", "relationship_status": "single"}),
        (ago(7), "career", "decision_pending", "a return offer arrived from San Francisco, with two weeks to answer", {}),
        (ago(4), "career", "decision_pending", "the Toronto payments startup wrote to ask if you would come back full time", {}),
    ]


SEED_DATA = Path(__file__).parent / "seed_data" / "demo_research.json"


def _stored(scenario_id: str, title: str) -> dict:
    """Research that was really run once for the demo (scripts in seed_research.py) and kept, so a
    fresh database shows real sources without crawling again. Absent file = nothing researched."""
    if not SEED_DATA.exists():
        return {}
    return json.loads(SEED_DATA.read_text()).get("branches", {}).get(f"{scenario_id}|{title}", {})


def _researched(person_id: str, stored: dict, events: list[dict], span):
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
            arithmetic = outcome_model.apply_rate(event, rate, eid, span)
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



def _scenario(person, fork, store, sid: str, situation: str, span: Horizon, scale: str, paths: list, start: date,
              deadline: str | None = None) -> tuple[Scenario, list]:
    scenario = Scenario(id=sid, person_id=DEMO_ID, situation=situation, horizon=span, scale=scale,
                        created_at=datetime.combine(start, datetime.min.time()).isoformat(timespec="seconds"),
                        options=[Option(id=uuid.uuid4().hex[:8], title=t, details=d, deadline=deadline) for t, _, d, _ in paths])
    views = []
    for option, (title, choice, _, events) in zip(scenario.options, paths):
        events = _model(events, choice, span, start)
        for e in events:
            e["effects"] = dict(zip(MEASURE_NAMES, CHOICE_EFFECTS.get(title, (0, 0, 0, 0)) if e.get("head")
                                    else EFFECTS_ON_PATH.get((title, e["key"]), EFFECTS.get(e["key"], (0, 0, 0, 0)))))
        stored = _stored(sid, title)
        assumption, params = BIG_ASSUMPTIONS.get(title, ({}, {}))
        params = {**params, **stored.get("params", {})}
        view = branches.create_branch(person, fork, title, assumption, f"decide_by: {deadline}" if deadline else None,
                                      scenario_id=sid, option_id=option.id, params=dict(params), span=span, events=events,
                                      research="done" if stored.get("rates") or stored.get("facts") else "none",
                                      script={"partner": False, "children": False, "home": False},
                                      extra_evidence=_researched(DEMO_ID, stored, events, span), forked_at=start.isoformat())
        if title in OWN_WORDS:
            claim, value, unit = OWN_WORDS[title]
            priced = [(e, OWN_AMOUNTS[(title, e["key"])]) for e in view.branch.model["events"] if (title, e["key"]) in OWN_AMOUNTS]
            for e, (amount, currency, per) in priced:  # the person's own figure, on the moment it starts
                e["money_amount"] = {"value": amount, "currency": currency, "per": per, "evidence_id": f"ev_demo_{view.branch.id}"}
                e["effects_basis"] = "sourced"
            if priced:
                view = branches.resimulate(person, view.branch)
            store.add_evidence([Evidence(id=f"ev_demo_{view.branch.id}", person_id=DEMO_ID, branch_id=view.branch.id,
                                         kind="researched", claim=claim, value=value, unit=unit,
                                         source_title="your own description", retrieved_at=start.isoformat())])
        scenario.branch_ids.append(view.branch.id)
        views.append(view)
    db.save_scenario(scenario)
    return scenario, views


def ensure_demo(store) -> None:
    seeded = [b for b, _ in db.list_branches(DEMO_ID)]
    current = len(db.list_scenarios(DEMO_ID)) == 3 and all((b.model or {}).get("layout") == outcome_model.LAYOUT for b in seeded)
    if current:
        return
    db.erase_person(DEMO_ID)  # an older demo: seed it again from scratch (event ids are deterministic)
    store.erase(DEMO_ID)
    person = db.upsert_person(Person(id=DEMO_ID, display_name="Demo", birth_year=2004,
                                     personality=from_mbti(DEMO_MBTI).model_dump()))
    today = date.today()
    events = [
        LifeEvent(id=sha1(f"demo|{when}|{kind}|{text}".encode()).hexdigest()[:16], person_id=DEMO_ID, source="scraped",
                  branch_id="main", date=when, domain=domain, event_type=kind, payload=payload, confidence=0.9, text=text)
        for when, domain, kind, text, payload in trunk(today)
    ]
    store.append(events)
    fork, _, _ = build_state(store, person, len(events))

    # the earlier decision, made and merged three weeks ago: a chosen path and a road not taken
    earlier = today - timedelta(days=EARLIER_DAYS_AGO)
    scenario, (went, packed) = _scenario(person, fork, store, "demo-farewell", EARLIER_SITUATION, EARLIER_SPAN, "small",
                                         [DINNER, PACK], earlier)
    went.branch.status, packed.branch.status = "merged", "faded"
    db.save_branch(went.branch)
    db.save_branch(packed.branch)
    scenario.status, scenario.decided_branch_id = "decided", went.branch.id
    db.save_scenario(scenario)
    store.append([LifeEvent(id=sha1(f"{went.branch.id}|decision".encode()).hexdigest()[:16], person_id=DEMO_ID, source="told",
                            branch_id="main", date=earlier.isoformat(), domain="career", event_type="decision",
                            payload={"from_branch": went.branch.id, "label": went.branch.label}, confidence=1.0, text=DINNER[1])])

    _scenario(person, fork, store, "demo-offer", BIG_SITUATION, BIG_SPAN, "big", [OFFER, MASTERS, TORONTO], today,
              deadline=(today + timedelta(days=7)).isoformat())
    _scenario(person, fork, store, "demo-tonight", SMALL_SITUATION, SMALL_SPAN, "small", [GO, STAY_IN], today)
