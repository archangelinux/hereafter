"""What happens on a path must make sense: sensible horizons, step zero, a causal story, a representative life."""

from datetime import date

import numpy as np

from app import llm, outcome_model
from app.models import Horizon
from app.sim.outcomes import simulate_outcomes, step_dates, step_offsets, window_from_days

DEMO = {"person_id": "demo"}
START = date(2026, 9, 19)


def ev(key, window, bin_="usually", **extra):
    return {"key": key, "label": key, "domain": "x", "kind": "one_time", "window": list(window), "bin": bin_, "basis": "estimated",
            "base_probability": None, "depends_on": [], "after": [], "requires": [], **extra}


# --- A. horizons ---

def test_long_paths_step_weekly_then_monthly_then_quarterly():
    steps = step_dates("years", 3, START)
    gaps = [(b - a).days for a, b in zip(steps, steps[1:])]
    assert len(steps) == 4 + 11 + 8 and gaps[:3] == [7, 7, 7] and all(28 <= g <= 31 for g in gaps[4:14]) and all(89 <= g <= 92 for g in gaps[15:])
    assert steps[0] == START and step_offsets("years", 3, START)[-1] == (date(2029, 9, 19) - START).days
    assert len(step_dates("days", 7, START)) == 7 and len(step_dates("months", 4, START)) == 4, "short horizons step evenly"


def test_big_decisions_are_three_years_and_never_more_than_five_unless_the_person_says_so():
    assert outcome_model.rules_horizon("A job offer in another city", []) == Horizon(unit="years", count=3)
    assert outcome_model.clamp(Horizon(unit="years", count=40)).count == 5
    assert outcome_model.clamp(Horizon(unit="years", count=12), person_set=True).count == 12


# --- B. step zero ---

def test_step_zero_is_the_choice_in_every_life_and_first_in_the_one_you_read(client):
    for view in client.get("/branches", params=DEMO).json()["branches"]:
        head = view["branch"]["model"]["events"][0]
        assert head["head"] and head["basis"] == "choice" and head["probability"] == 1.0 and head["label"].startswith("You ")
        first = view["years"][0]["events"][0]
        assert first["payload"]["head"] and first["text"] == head["label"] and first["date"] == view["branch"]["forked_at"]
    events = outcome_model.ensure_head([ev("a", (0, 2))], "You go")
    result = simulate_outcomes("p", events, 3, 300)
    i = result.keys.index("choice")
    assert result.fired[0, :, i].all() and not result.fired[1:, :, i].any()
    assert outcome_model.choice_label("Take the offer") == "You take the offer" and outcome_model.choice_label("McMaster") == "You choose McMaster"


# --- C. a causal story ---

def test_repair_makes_the_story_causally_valid():
    events = [ev("start", (4, 6)), ev("promoted", (2, 9), after=["start", "nonsense"]), ev("fired", (1, 3), requires=["start"]),
              ev("a", (0, 1), after=["b"]), ev("b", (0, 1), after=["a"])]
    by = {e["key"]: e for e in outcome_model.repair(events)}
    assert by["promoted"]["after"] == ["start"] and by["promoted"]["window"] == [4, 9], "a window may not open before what it follows"
    assert by["fired"]["window"] == [4, 6] and by["fired"]["after"] == ["start"], "what is required is also followed, with room to follow it"
    assert not (("b" in by["a"]["after"]) and ("a" in by["b"]["after"])), "cycles are cut"


def test_proposals_arrive_in_days_and_become_steps():
    offsets = step_offsets("years", 3, START)
    assert window_from_days(offsets, 0, 6) == [0, 0] and window_from_days(offsets, 100, 140) == [6, 7] and window_from_days(offsets, 5000, 9000) == [22, 22]
    event = lambda key, a, b, **kw: llm.ProposedEvent(key=key, label=key, domain="work", phase="right_away", from_day=a, to_day=b,
                                                      bin="almost certainly", **kw)
    option = llm.ProposedOption(option_index=0, choice_label="You accept the offer",
                                events=[event("first_day", 100, 140, requires=["move"]), event("move", 95, 130), event("choice", 0, 0)])
    model = outcome_model.from_proposal(option, offsets, "Take the offer")
    assert [e["key"] for e in model] == ["choice", "first_day", "move"] and model[0]["label"] == "You accept the offer"
    assert model[1]["days"] == [100, 140] and model[1]["requires"] == ["move"] and model[1]["bin"] == "almost certainly"


def test_the_sampler_enforces_order_and_requirements_in_every_life():
    events = [ev("move", (0, 5), "as often as not"), ev("first_day", (0, 8), "usually", requires=["move"]),
              ev("miss_home", (0, 9), "usually", after=["move"])]
    r = simulate_outcomes("p", events, 10, 3000)
    when = lambda key: np.where(r.happened[:, :, r.keys.index(key)].any(axis=0), r.happened[:, :, r.keys.index(key)].argmax(axis=0), 99)
    move, first_day, miss_home = when("move"), when("first_day"), when("miss_home")
    assert ((first_day == 99) | (move <= first_day)).all() and (first_day[move == 99] == 99).all(), "never without, never before"
    assert (miss_home[(move != 99) & (miss_home != 99)] >= move[(move != 99) & (miss_home != 99)]).all()
    assert (miss_home[move == 99] > 5).all(), "after: only once the other's moment has passed"
    # a base chance means: given what it requires. P(first_day | move) stays close to "usually".
    assert 0.7 <= (first_day[move != 99] != 99).mean() <= 0.9


def test_near_certain_first_steps_keep_a_path_going():
    chain = [ev("sign", (0, 0), "almost certainly"), ev("move", (5, 7), "almost certainly", requires=["sign"]),
             ev("first_day", (6, 7), "almost certainly", requires=["move"])]
    r = simulate_outcomes("p", chain, 23, 2000)
    assert r.cumulative[-1, r.keys.index("first_day")] > 0.85


# --- D. the life you read ---

def test_the_modal_life_has_what_is_likely_and_a_typical_share_of_the_rest():
    likely = [ev(f"likely_{i}", (0, 5), "usually") for i in range(4)]
    unlikely = [ev(f"unlikely_{i}", (0, 5), "rare") for i in range(4)]
    coin = [ev(f"maybe_{i}", (0, 5), "sometimes") for i in range(4)]
    r = simulate_outcomes("p", likely + unlikely + coin, 6, 1000)
    lived = {k for step in r.life(r.typical) for k in step}
    assert {e["key"] for e in likely} <= lived and not ({e["key"] for e in unlikely} & lived)
    assert len(lived & {e["key"] for e in coin}) == 1, "about one in four of the four 'sometimes' things: a typical number of them"
    rare = {k for step in r.life(r.rare) for k in step}
    assert len(rare) >= 3 and rare != lived and r.score[r.rare] < r.score[r.typical]


def test_every_demo_life_reads_in_order(client):
    for view in client.get("/branches", params=DEMO).json()["branches"]:
        model = {e["key"]: e for e in view["branch"]["model"]["events"]}
        lived = [e for y in view["years"] for e in y["events"]]
        dates = [e["date"] for e in lived]
        assert dates == sorted(dates) and len(lived) >= 5, "dated, in order, and not sparse"
        on = {e["event_type"]: e["date"] for e in lived}
        for e in lived:
            spec = model[e["event_type"]]
            assert all(k in on and on[k] <= e["date"] for k in spec["requires"]), (view["branch"]["label"], e["text"])
            assert all(on[k] <= e["date"] for k in spec["after"] if k in on)
        if view["branch"]["span"]["unit"] == "years":
            assert dates[-1] > view["years"][14]["at"], "a three-year path does not go quiet after the first year"


# --- F. coherent narration ---

def test_chapters_share_a_story_bible_and_pick_up_from_the_one_before(client, monkeypatch):
    from app import chapters, db

    branch, years = db.get_branch(next(v for v in client.get("/branches", params=DEMO).json()["branches"]
                                       if v["branch"]["label"] == "Take the offer")["branch"]["id"])
    seen, bibles = [], []

    def bible(context):
        bibles.append(context)
        return llm.StoryBible(setting="a payments-infrastructure team on the fourth floor of a former warehouse",
                              neighbourhood="a shared flat two blocks from a train line",
                              people=[llm.BiblePerson(name="Dario", role="the teammate who sits opposite"),
                                      llm.BiblePerson(name="Wren", role="a flatmate who works nights")])

    def chapter(context):
        seen.append(context)
        return llm.ChapterDraft(title="First Month", paragraphs=[llm.ChapterParagraph(text="You sign.", evidence_ids=[])],
                                recap="You have signed and told your parents. The move is booked for January.")

    monkeypatch.setattr(llm, "enabled", lambda: True)
    monkeypatch.setattr(llm, "write_bible", bible)
    monkeypatch.setattr(llm, "write_chapter", chapter)
    chapters._write(branch, years, 0, 4, "typical")
    chapters._write(branch, years, 4, 15, "typical")
    first, second = seen
    assert "STEP ZERO" in first and "This is the first chapter: open on step zero" in first and first.index("STEP ZERO") < first.index("you sign the offer")
    assert len(bibles) == 1, "the bible is written once and stored"
    for context in (first, second):
        assert "Dario — the teammate who sits opposite" in context and "former warehouse" in context
        assert "first co-op term, at a payments startup in Toronto" in context, "real facts come from main"
    assert "THE STORY SO FAR: You have signed and told your parents. The move is booked for January." in second
    assert db.get_chapter(branch.id, branch.revision, "typical", years[0].at).recap.startswith("You have signed")
    assert "Dario" not in bibles[0], "the invented people are not fed back as facts"


# --- four measures, as change from now ---

from app.sim.outcomes import marks, measures


def _sure(key, step, effects, **extra):
    return ev(key, (step, step), basis="sourced", base_probability=0.995, band=0.0, effects=effects, **extra)


def test_effects_accumulate_and_decay_as_documented():
    events = [_sure("night_out", 0, {"health": -1, "joy": 2, "fulfilment": 1, "money": -1})]
    offsets = [0, 10, 20, 750]                                     # three steps: ten days, ten days, two years
    r = simulate_outcomes("p", events, 3, 400)
    m = measures(r, events, offsets, ["2026-01-01", "2026-01-11", "2026-01-21"])
    joy = [p["mean"] for p in m["series"]["joy"]]
    assert abs(joy[0] - 2 * 0.995) < 0.05 and abs(joy[1] - joy[0] / 2) < 0.01 and abs(joy[2] - joy[0] / 4) < 0.01, "half-life ten days"
    health = [p["mean"] for p in m["series"]["health"]]
    assert abs(health[1] / health[0] - 0.5 ** (10 / 730)) < 1e-3, "health fades slowly: half-life two years"
    assert [p["mean"] for p in m["series"]["fulfilment"]] == [m["series"]["fulfilment"][0]["mean"]] * 3, "fulfilment stays"
    assert m["end"]["money"]["marks"] == "−" and m["end"]["fulfilment"]["marks"] == "+" and m["money_end"] is None
    assert all(p["low"] <= p["mean"] <= p["high"] for series in m["series"].values() for p in series)
    assert [marks(d) for d in (0.49, 0.5, -1.5, 3.0, -9)] == ["=", "+", "−−", "+++", "−−−"]


def test_no_effects_means_flat_lines():
    events = [ev("a", (0, 2)), ev("b", (1, 2), "sometimes")]
    m = measures(simulate_outcomes("p", events, 3, 300), events, [0, 1, 2, 3], ["d0", "d1", "d2"])
    assert all(p == {"at": p["at"], "mean": 0.0, "low": 0.0, "high": 0.0} for series in m["series"].values() for p in series)
    assert all(e["marks"] == "=" for e in m["end"].values())


def test_the_money_ledger_is_arithmetic_in_real_units():
    salary = {"value": 120000, "currency": "USD", "per": "year", "evidence_id": None}
    events = [_sure("job_starts", 1, {"money": 2}, money_amount=salary), _sure("deposit", 0, {}, money_amount={"value": -2000, "currency": "CAD", "per": "once"}),
              _sure("rent", 0, {}, money_amount={"value": -1000, "currency": "CAD", "per": "month"})]
    offsets = [0, 365, 730]                                        # the job starts a year in and is paid for one year
    r = simulate_outcomes("p", events, 2, 400)
    m = measures(r, events, offsets, ["2026-01-01", "2027-01-01"], "CAD", {"income": 60000, "currency": "CAD"})
    expected = 120000 * 1.37 * (365 / 365.25) - 2000 - 1000 * (730 / 30.4375)
    assert abs(m["money_end"]["value"] - expected) / expected < 0.02 and m["money_end"]["currency"] == "CAD"
    assert "what you earn now" in m["money_end"]["note"] and "about the same as" in m["money_end"]["note"]
    assert "what you earn" not in measures(r, events, offsets, ["a", "b"])["money_end"]["note"], "no baseline given, none used"


def test_measures_through_the_api_with_the_llm_off(client):
    views = client.get("/branches", params=DEMO).json()["branches"]
    offer = next(v for v in views if v["branch"]["label"] == "Take the offer")["branch"]
    m = offer["measures"]
    assert set(m["series"]) == set(m["end"]) == {"health", "joy", "fulfilment", "money"} and len(m["series"]["joy"]) == 23
    assert m["end"]["money"]["marks"] in ("+", "++", "+++") and m["money_end"]["currency"] == "USD" and m["money_end"]["value"] > 300000  # their own currency when none is given: the figure as they said it
    job = next(e for e in offer["model"]["events"] if e["key"] == "first_day_at_work")
    assert job["effects_basis"] == "sourced" and job["money_amount"]["per"] == "year" and job["money_amount"]["evidence_id"]
    assert all(set(e["effects"]) == {"health", "joy", "fulfilment", "money"} and e["effects_basis"] in ("judgement", "sourced")
               for e in offer["model"]["events"])
    ids = [v["branch"]["id"] for v in views if v["branch"]["scenario_id"] == "demo-offer"]
    compared = client.get("/compare", params={"a": ids[0], "b": ids[1]}).json()
    assert set(compared["measures"]) == set(ids[:2]) and compared["measures"][ids[0]]["joy"]["marks"] and set(compared["money_end"]) == set(ids[:2])
    # a bare decision made with the LLM off has no judgements at all: flat lines
    made = client.post("/people", json={"income": 52000, "net_worth": 8000, "currency": "cad"}).json()
    auth = {"Authorization": f"Bearer {made['token']}"}
    client.post("/scenarios", json={"person_id": made["person_id"], "text": "Lend it or say no?"}, headers=auth)
    flat = client.get("/branches", params={"person_id": made["person_id"]}, headers=auth).json()["branches"][0]["branch"]["measures"]
    assert all(e["delta"] == 0 and e["marks"] == "=" for e in flat["end"].values()) and flat["money_end"] is None


def test_money_context_is_optional_encrypted_and_listed(client):
    from app import db

    made = client.post("/people", json={"income": 52000, "net_worth": 8000, "currency": "cad"}).json()
    pid, auth = made["person_id"], {"Authorization": f"Bearer {made['token']}"}
    assert client.get("/trunk", params={"person_id": pid}, headers=auth).json()["person"]["money"] == {"income": 52000, "net_worth": 8000, "currency": "CAD"}
    row = db.conn().execute("SELECT money FROM people WHERE id=?", (pid,)).fetchone()["money"]
    assert "52000" not in row and client.get("/inventory", params={"person_id": pid}, headers=auth).json()["money"]["income"] == 52000
    client.post("/ingest", data={"person_id": pid, "net_worth": "12000"}, headers=auth)
    assert client.get("/trunk", params={"person_id": pid}, headers=auth).json()["person"]["money"] == {"income": 52000, "net_worth": 12000, "currency": "CAD"}
    nobody = client.post("/people", json={}).json()
    assert client.get("/trunk", params={"person_id": nobody["person_id"]}, headers={"Authorization": f"Bearer {nobody['token']}"}).json()["person"]["money"] is None


# --- commit = one more step on the path you are on; branch = a split at a point ---

def _small(client):
    going = next(v for v in client.get("/branches", params=DEMO).json()["branches"] if v["branch"]["label"] == "Go to the housewarming")
    return going, going["branch"]["id"]


def test_assuming_a_possibility_happens_is_a_commit_without_the_llm(client):
    going, bid = _small(client)
    shape = lambda v: [(y["at"], [(e["date"], e["text"]) for e in y["events"]]) for y in v["years"]]
    before = {e["key"]: e["probability"] for e in going["branch"]["model"]["events"]}
    made = client.post(f"/branches/{bid}/commits", json={"event_key": "problem_set_full_marks", "at": going["years"][0]["at"]}).json()
    commit = made["branch"]["commits"][0]
    assert commit["message"] == "the set comes back with full marks happens" and commit["patch"]["event_key"] == "problem_set_full_marks"
    assert commit["at"] == going["years"][5]["at"], "not before its own moment can come: the start of its window"
    after = {e["key"]: e["probability"] for e in made["branch"]["model"]["events"]}
    assert after["problem_set_full_marks"] == 1.0 > before["problem_set_full_marks"]
    assert made["branch"]["measures"]["end"]["joy"]["delta"] != going["branch"]["measures"]["end"]["joy"]["delta"], "measures follow"
    assert "commit" in [e["event_type"] for e in made["years"][5]["events"]]
    assert client.post(f"/branches/{bid}/commits", json={"event_key": "nonsense", "at": going["years"][0]["at"]}).status_code == 404
    assert client.post(f"/branches/{bid}/commits", json={"event_key": "choice", "at": going["years"][0]["at"]}).status_code == 404
    undone = client.post(f"/branches/{bid}/undo", json={}).json()
    assert shape(undone) == shape(going) and undone["branch"]["measures"] == going["branch"]["measures"], "undo is exact"


def test_a_decision_can_split_off_a_path_at_a_date_and_pins_what_came_before(client):
    going, bid = _small(client)
    day2 = going["years"][2]["at"]
    early = client.post(f"/branches/{bid}/commits", json={"event_key": "reconnect_with_old_friend", "at": going["years"][0]["at"]}).json()
    body = {"person_id": "demo", "situation": "They asked me to a cottage weekend.", "options": [{"title": "Go", "details": ""}, {"title": "Stay home", "details": ""}],
            "assuming_branch_id": bid, "assuming_at": day2}
    made = client.post("/scenarios", json=body).json()["scenario"]
    assert made["fork_at"] == day2 and made["assuming_at"] == day2 and made["assuming_branch_id"] == bid
    assert any("asks for your number" in f for f in made["assumed_facts"]) and all(f[:10] <= day2 for f in made["assumed_facts"])
    nested = [v for v in client.get("/branches", params=DEMO).json()["branches"] if v["branch"]["scenario_id"] == made["id"]]
    assert all(v["branch"]["forked_at"] == day2 == v["years"][0]["at"] for v in nested), "the new paths start at the fork"
    refused = client.post(f"/branches/{bid}/undo", json={})
    assert refused.status_code == 409 and "splits off this path" in refused.json()["detail"]
    late = client.post(f"/branches/{bid}/commits", json={"event_key": "plans_next_weekend", "at": going["years"][5]["at"]}).json()
    assert client.post(f"/branches/{bid}/undo", json={}).status_code == 200, "a commit after the fork can still be undone"


def test_a_money_amount_must_be_in_the_persons_own_words():
    said = "The offer is US$165,000 base, rent would be about 2.4k a month, and I owe my sister four hundred."
    assert outcome_model.stated(165000, said) and outcome_model.stated(-2400, "rent of 2400") and outcome_model.stated(95000, "95k and equity")
    assert not outcome_model.stated(180000, said) and not outcome_model.stated(400, said), "a figure the person never wrote is not theirs"
    event = llm.ProposedEvent(key="job", label="the job starts", domain="work", phase="right_away", from_day=0, to_day=5, bin="usually",
                              money_amount=llm.MoneyAmount(value=180000, currency="USD", per="year"))
    option = llm.ProposedOption(option_index=0, choice_label="You accept", events=[event])
    offsets = step_offsets("years", 3, START)
    assert outcome_model.from_proposal(option, offsets, "Take it", said)[1]["money_amount"] is None
    event.money_amount.value = 165000
    kept = outcome_model.from_proposal(option, offsets, "Take it", said)[1]
    assert kept["money_amount"]["value"] == 165000 and kept["effects_basis"] == "sourced"
