"""The generic sampler and the one door a number may come through."""

import json
from pathlib import Path

from app import llm, outcome_model
from app.sim.outcomes import BINS, simulate_outcomes

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "text_my_ex.json").read_text())


def test_a_stored_model_for_a_small_decision_reruns_identically_with_the_llm_off():
    assert llm.enabled() is False
    events = FIXTURE["options"]["text_them"]
    a = simulate_outcomes("p", events, FIXTURE["steps"], 1000)
    b = simulate_outcomes("p", events, FIXTURE["steps"], 1000)
    assert a.seed == b.seed and a.typical == b.typical and a.rare == b.rare
    assert (a.fired == b.fired).all() and a.life(a.typical) == b.life(b.typical)
    assert simulate_outcomes("someone else", events, FIXTURE["steps"], 1000).seed != a.seed


def test_shares_respect_bins_sourced_figures_and_dependencies():
    events = FIXTURE["options"]["text_them"]
    r = simulate_outcomes("p", events, FIXTURE["steps"], 4000)
    final = dict(zip(r.keys, r.shares[-1]))
    lo, hi = BINS["usually"]
    assert lo - 0.03 <= final["they_read_it_tonight"] <= hi + 0.03          # estimated: inside its bin
    assert abs(final["they_reply_within_a_day"] - 0.44 * final["they_read_it_tonight"]) < 0.2
    assert final["you_meet_for_coffee"] <= final["they_reply_within_a_day"]  # requires a reply
    quiet = simulate_outcomes("p", FIXTURE["options"]["leave_it"], FIXTURE["steps"], 4000)
    assert dict(zip(quiet.keys, quiet.shares[-1]))["regret_next_morning"] < final["regret_next_morning"] + 0.5


def test_commit_patches_force_and_prevent():
    events = FIXTURE["options"]["text_them"]
    forced = simulate_outcomes("p", events, FIXTURE["steps"], 500, [{"step": 1, "force": ["you_meet_for_coffee"]}])
    assert forced.shares[1, forced.keys.index("you_meet_for_coffee")] == 1.0
    prevented = simulate_outcomes("p", events, FIXTURE["steps"], 500, [{"step": 0, "prevent": ["regret_next_morning"]}])
    assert prevented.shares[-1, prevented.keys.index("regret_next_morning")] == 0.0


def test_the_rare_life_is_eventful_and_unlike_the_typical_one():
    r = simulate_outcomes("p", FIXTURE["options"]["text_them"], FIXTURE["steps"], 1000)
    assert r.rare != r.typical and sum(len(step) for step in r.life(r.rare)) >= 2
    assert r.score[r.rare] < r.score[r.typical]


def test_a_figure_counts_only_if_it_is_literally_in_its_own_snippet():
    event = {"key": "relapse", "label": "you drink again before the month is out", "kind": "one_time",
             "window": [0, 3], "basis": "estimated", "bin": "sometimes", "probability": None}
    honest = llm.PublishedRate(claim="Share of Dry January participants who stay dry all month.",
                               figure_as_written="62%", span_days=31,
                               snippet="In the follow-up survey, 62% of participants reported staying dry for the whole month.")
    arithmetic = outcome_model.apply_rate(dict(event), honest, "ev_1", "weeks")
    assert arithmetic and "0.620" in arithmetic and "31 days" in arithmetic

    invented = honest.model_copy(update={"figure_as_written": "71%"})
    untouched = dict(event)
    assert outcome_model.apply_rate(untouched, invented, "ev_2", "weeks") is None
    assert untouched["basis"] == "estimated" and untouched["probability"] is None

    vague = honest.model_copy(update={"figure_as_written": "most", "snippet": "most participants stayed dry"})
    assert outcome_model.apply_rate(dict(event), vague, "ev_3", "weeks") is None


def test_published_shares_are_parsed_and_converted_in_code():
    assert outcome_model.parse_share("23%") == 0.23
    assert outcome_model.parse_share("1 in 4") == 0.25
    assert outcome_model.parse_share("41 per 1,000") == 0.041
    assert outcome_model.parse_share("about half") is None and outcome_model.parse_share("140%") is None
    event = {"kind": "one_time", "window": [0, 3], "label": "x"}
    p, words = outcome_model.window_probability(0.5, 56, event, "weeks")   # half over 8 weeks -> over 4 weeks
    assert abs(p - (1 - 0.5 ** 0.5)) < 1e-9 and "56 days" in words
    assert outcome_model.window_probability(0.3, None, event, "weeks")[0] == 0.3
    assert outcome_model.parse_share("Between 61 and 64%") == 0.625 and outcome_model.parse_share("20–30 percent") == 0.25
    finish = {"kind": "state", "window": [29, 29], "label": "you reach day 30"}                    # an end-of-month outcome
    p, _ = outcome_model.window_probability(0.625, 31, finish, "days")
    assert 0.58 < p < 0.64, "a month-long published rate applied to day 30 stays close to the published figure"


def test_the_sampler_cannot_reach_the_llm():
    import app.sim.outcomes as outcomes

    assert "llm" not in vars(outcomes) and "anthropic" not in vars(outcomes) and "openai" not in vars(outcomes)


def test_a_poor_fit_draws_from_a_band_instead_of_a_point():
    base = {"key": "x", "label": "x", "kind": "one_time", "window": [0, 0], "basis": "sourced", "probability": 0.5, "depends_on": []}
    point = simulate_outcomes("p", [dict(base, band=0.0)], 1, 4000)
    banded = simulate_outcomes("p", [dict(base, band=0.15)], 1, 4000)
    assert abs(point.shares[0, 0] - 0.5) < 0.03 and abs(banded.shares[0, 0] - 0.5) < 0.03   # same centre
    assert point.seed != banded.seed
    honest = llm.PublishedRate(claim="c", figure_as_written="40%", snippet="about 40% of them did", gap="US students, 2009", gap_is_large=True)
    event = {"key": "k", "label": "l", "kind": "one_time", "window": [0, 0], "basis": "estimated", "bin": "sometimes"}
    outcome_model.apply_rate(event, honest, "ev", "days")
    assert event["band"] == 0.15 and event["probability"] == 0.4
    close = honest.model_copy(update={"gap_is_large": False})
    outcome_model.apply_rate(event, close, "ev", "days")
    assert event["band"] == 0.0


def test_open_questions_widen_every_range():
    events = FIXTURE["options"]["text_them"]
    narrow = simulate_outcomes("p", events, FIXTURE["steps"], 2000)
    wide = simulate_outcomes("p", events, FIXTURE["steps"], 2000, widen=0.16)
    assert sum(wide.solidity) < sum(narrow.solidity) + 0.5 and wide.seed != narrow.seed
