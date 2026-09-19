"""Jev (classify + score) and the probability logic that combines it with evidence and personal context."""

from app import jev, llm, probability
from app.sim.outcomes import BINS, simulate_outcomes

from test_api import UNIS, canned_proposal, new_person, post_scenario


def event(**kw):
    base = {"key": "x", "label": "x", "domain": "work", "kind": "one_time", "window": [0, 0], "basis": "estimated",
            "bin": "rare", "base_probability": None, "band": 0.0, "depends_on": []}
    return {**base, **kw}


def scores(category="career", **kw):
    return {"category": category, "personal_fit": 3, "experience_fit": 3, "difficulty": 3, "accessibility": 3,
            "evidence_strength": 3, "prerequisites": [], "rationale": "r", "judged_by": "llm", **kw}


def test_the_probability_logic_cannot_reach_the_llm():
    assert not {"llm", "anthropic", "openai", "jev"} & set(vars(probability))


def test_neutral_scores_move_nothing():
    e = event(bin="as often as not", jev=scores())
    assert probability.estimate(e)["likelihood"] == 0.5 and probability.estimate(e)["shift"] == 0


def test_jev_can_nudge_a_base_rate_but_never_replace_it():
    perfect = scores(personal_fit=5, experience_fit=5, accessibility=5, difficulty=1)
    hopeless = scores(personal_fit=1, experience_fit=1, accessibility=1, difficulty=5)
    rare = event(bin="rare", jev=perfect)                 # base 6%
    up = probability.estimate(rare)["likelihood"]
    assert 0.06 < up < 0.2, "five perfect scores cannot make a rare outcome likely"
    down = probability.estimate(event(bin="usually", jev=hopeless))["likelihood"]   # base 80%
    assert 0.5 < down < 0.8, "five terrible scores cannot make a usual outcome impossible"
    published = event(basis="sourced", base_probability=0.20, jev=perfect)
    assert probability.estimate(published)["likelihood"] < up + 0.2 and probability.estimate(published)["likelihood"] > 0.20
    lo, hi = BINS["rare"]
    assert lo <= probability.estimate(event(bin="rare", jev=scores()))["likelihood"] <= hi


def test_category_routes_the_scores_differently():
    assert all(abs(sum(w.values()) - 1) < 1e-9 for w in probability.CATEGORY_WEIGHTS.values())
    experienced = dict(personal_fit=1, experience_fit=5)
    career = probability.estimate(event(bin="as often as not", jev=scores("career", **experienced)))["likelihood"]
    social = probability.estimate(event(bin="as often as not", jev=scores("social", **experienced)))["likelihood"]
    assert career > 0.5 > social, "experience matters for a career outcome; personal fit matters for a social one"


def test_an_unmet_hard_prerequisite_caps_the_outcome_and_an_unknown_one_only_widens_it():
    need = {"requirement": "a bachelor's degree", "basis": "no degree in the record"}
    blocked = probability.estimate(event(bin="usually", jev=scores(prerequisites=[{**need, "met": "no"}])))
    assert blocked["likelihood"] <= probability.HARD_CAP and blocked["blocked"] and blocked["difficulty_label"] == "blocked"
    assert any(l["kind"] == "prerequisite" and "bachelor" in l["text"] for l in blocked["evidence"])
    plain = probability.estimate(event(bin="usually", jev=scores()))
    unsure = probability.estimate(event(bin="usually", jev=scores(prerequisites=[{**need, "met": "unknown"}])))
    assert unsure["likelihood"] == plain["likelihood"] and unsure["spread"] > plain["spread"] and unsure["confidence"] < plain["confidence"]


def test_confidence_follows_the_evidence():
    weak = probability.estimate(event(bin="sometimes", jev=scores(evidence_strength=1)))
    published = probability.estimate(event(basis="sourced", base_probability=0.3, jev=scores(evidence_strength=3)))
    poor_fit = probability.estimate(event(basis="sourced", base_probability=0.3, band=0.15, jev=scores(evidence_strength=3)))
    assert weak["confidence"] < poor_fit["confidence"] < published["confidence"]
    assert published["spread"] < weak["spread"]


def test_assess_is_idempotent_and_leaves_the_audit_trail_alone():
    e = event(basis="sourced", base_probability=0.25, band=0.0, evidence_id="ev_1", jev=scores(personal_fit=5))
    probability.assess_events([e])
    first = dict(e["estimate"])
    probability.assess_events([e])
    assert e["estimate"] == first and e["base_probability"] == 0.25 and e["basis"] == "sourced"
    assert e["estimate"]["base"] == {"probability": 0.25, "basis": "sourced"}
    assert e["estimate"]["evidence"][0]["evidence_id"] == "ev_1"


def test_the_sampler_centres_on_the_estimate_and_old_models_keep_their_seed():
    e = event(bin="rare", jev=scores(personal_fit=5, experience_fit=5, accessibility=5, difficulty=1))
    plain = simulate_outcomes("p", [dict(e)], 1, 4000)
    probability.assess_events([e])
    est = simulate_outcomes("p", [e], 1, 4000)
    assert abs(est.shares[0, 0] - e["estimate"]["likelihood"]) < 0.03 and est.shares[0, 0] > plain.shares[0, 0]
    assert est.seed != plain.seed
    old = event(bin="rare")
    assert simulate_outcomes("p", [old], 1, 200).seed == simulate_outcomes("p", [dict(old)], 1, 200).seed


# --- Jev ---


def fake_judgement(events, **per_key):
    return llm.Judgement(events=[llm.JudgedEvent(**{
        "key": e["key"], "category": "career", "personal_fit": 3, "experience_fit": 3, "difficulty": 3, "accessibility": 3,
        "evidence_strength": 3, "prerequisites": [], "rationale": "because", **per_key.get(e["key"], {})}) for e in events])


def test_jev_attaches_scores_and_falls_back_to_neutral_rules(monkeypatch):
    es = [event(key="a", domain="money"), event(key="b", domain="whatever")]
    monkeypatch.setattr(llm, "judge_events", lambda about, record, option, events: fake_judgement(events, a={"category": "financial", "difficulty": 5}))
    assert jev.judge(es) == 2 and es[0]["jev"]["category"] == "financial" and es[0]["jev"]["difficulty"] == 5
    assert es[0]["jev"]["judged_by"] == "llm"

    fresh = [event(key="a", domain="money"), event(key="b", domain="whatever")]
    monkeypatch.setattr(llm, "judge_events", lambda *a: None)          # model off or failed
    assert jev.judge(fresh) == 0
    assert fresh[0]["jev"]["category"] == "financial" and fresh[1]["jev"]["category"] == "other"
    assert fresh[0]["jev"]["judged_by"] == "rules" and fresh[0]["jev"]["accessibility"] == 3


def test_jev_clamps_out_of_range_scores(monkeypatch):
    e = [event(key="a")]
    monkeypatch.setattr(llm, "judge_events", lambda about, record, option, events: fake_judgement(events, a={"difficulty": 9, "personal_fit": -2}))
    jev.judge(e)
    assert e[0]["jev"]["difficulty"] == 5 and e[0]["jev"]["personal_fit"] == 1


# --- the whole path, through the API ---


def test_scenarios_come_back_classified_scored_and_estimated(client, monkeypatch):
    monkeypatch.setattr(llm, "propose_scenario_model", lambda *a, **k: canned_proposal(question=False))
    seen = {}

    def judge(about, record, option, events):
        seen[option] = record
        return fake_judgement(events, coop_term={"category": "career", "experience_fit": 2, "accessibility": 1, "difficulty": 5,
                                                 "prerequisites": [llm.Prerequisite(requirement="be admitted to the co-op stream", met="no", basis="grades in record")]},
                              finish_degree={"category": "education", "personal_fit": 5, "experience_fit": 5, "difficulty": 2})

    monkeypatch.setattr(llm, "judge_events", judge)
    pid, auth = new_person(client, birth_year=2008)
    made = post_scenario(client, auth, {"person_id": pid, "situation": "Which uni?", "options": UNIS})
    branch = made["branches"][0]["branch"]
    events = {e["key"]: e for e in branch["model"]["events"]}
    assert len(seen) == 2, "Jev is called once per option, with that option's own record"

    coop = events["coop_term"]["estimate"]
    assert coop["blocked"] and coop["likelihood"] <= probability.HARD_CAP and coop["category"] == "career"
    finish = events["finish_degree"]["estimate"]
    assert finish["category"] == "education" and finish["likelihood"] > 0.25 and finish["confidence"] < 0.5
    assert events["finish_degree"]["base_probability"] is None and events["finish_degree"]["basis"] == "estimated"

    shares = {k: v["share"] for k, v in made["branches"][0]["years"][-1]["outlook"].items()}
    assert shares["coop_term"] < 0.08 < 0.2 < shares["finish_degree"], "the simulation runs on the estimate"

    got = client.get("/assessment", params={"branch_id": branch["id"]}, headers=auth).json()
    assert got["categories"] == {"career": 1, "education": 1} and got["events"][0]["key"] == "finish_degree"
    assert client.get("/assessment", params={"branch_id": branch["id"]}, headers={"Authorization": "Bearer demo"}).status_code in (401, 403, 404)


def test_without_a_model_the_pipeline_still_runs_and_moves_nothing(client, monkeypatch):
    monkeypatch.setattr(llm, "propose_scenario_model", lambda *a, **k: canned_proposal(question=False))
    pid, auth = new_person(client, birth_year=2008)
    made = post_scenario(client, auth, {"person_id": pid, "situation": "Which uni?", "options": UNIS})
    for e in made["branches"][0]["branch"]["model"]["events"]:
        if e.get("head"):
            assert "estimate" not in e and "jev" not in e, "the option itself happens in every life; there is nothing to score"
            continue
        est = e["estimate"]
        lo, hi = BINS[e["bin"]]
        assert est["judged_by"] == "rules" and est["shift"] == 0 and abs(est["likelihood"] - (lo + hi) / 2) < 1e-3
