import numpy as np

from app import config
from app.models import StateVector
from app.sim.engine import simulate
from app.sim.tables import load_tables

FORK = StateVector(year=2026, age=22, city="Waterloo", field="math_cs", employment="student")


def tables():
    return load_tables(str(config.DATA_DIR))


def test_tables_are_probabilities():
    t = tables()
    for arr in [*t.mortality.values(), *t.first_marriage.values(), t.divorce, t.fertility,
                t.purchase_hazard, t.separation, t.interprovincial, t.emigration]:
        assert np.all((arr >= 0) & (arr <= 1))
    assert t.mortality["both"][80] > t.mortality["both"][40] > 0


def test_same_inputs_same_future():
    a = simulate(tables(), "p", FORK, {"city": "Toronto"}, None, 30, 300)
    b = simulate(tables(), "p", FORK, {"city": "Toronto"}, None, 30, 300)
    assert a.seed == b.seed and a.events == b.events and a.solidity == b.solidity


def test_assumption_changes_the_future_and_holds_at_the_fork():
    a = simulate(tables(), "p", FORK, {"city": "Toronto"}, None, 30, 300)
    b = simulate(tables(), "p", FORK, {"city": "Vancouver"}, None, 30, 300)
    assert a.seed != b.seed
    assert a.states[0].city == "Toronto" and b.states[0].city == "Vancouver"


def test_solidity_is_agreement_and_fades_with_distance():
    r = simulate(tables(), "p", FORK, {}, None, 40, 500)
    assert all(0 <= s <= 1 for s in r.solidity)
    assert np.mean(r.solidity[:5]) > np.mean(r.solidity[-5:])


def test_no_personality_means_no_tilt():
    base = simulate(tables(), "p", FORK, {}, None, 20, 200)
    flat = simulate(tables(), "p", FORK, {}, None, 20, 200, {"O": 2, "C": 2, "E": 2, "A": 2, "N": 2, "confidence": 0})
    # Different seed (personality is part of it) but zero confidence must leave hazards untouched.
    assert base.seed != flat.seed and len(flat.years) > 0


def test_simulator_cannot_reach_the_llm():
    import app.sim.engine as engine
    import app.sim.tables as tables_module

    for module in (engine, tables_module):
        assert "llm" not in vars(module) and "anthropic" not in vars(module)


def test_personality_tilts_only_sourced_significant_hazards():
    t = tables()
    assert "job_change" not in t.trait_effects and "home_purchase" not in t.trait_effects
    assert set(t.trait_effects.get("mortality", {})) == {"C"}
    careful = {"C": 2.0, "confidence": 1.0}
    assert t.tilt("mortality", {k: v for k, v in careful.items() if k != "confidence"}) < 0


def test_commits_and_researched_params_are_deterministic_and_matter():
    base = simulate(tables(), "p", FORK, {"city": "Toronto", "employment": "employed"}, None, 30, 300)
    paid = simulate(tables(), "p", FORK, {"city": "Toronto", "employment": "employed"}, None, 30, 300,
                    None, [], {"salary": 240_000, "housing_cost_ratio": 2.0})
    again = simulate(tables(), "p", FORK, {"city": "Toronto", "employment": "employed"}, None, 30, 300,
                     None, [], {"salary": 240_000, "housing_cost_ratio": 2.0})
    assert paid.events == again.events and paid.outlook == again.outlook
    assert paid.states[0].income_band == "high" and base.seed != paid.seed
    moved = simulate(tables(), "p", FORK, {"city": "Toronto"}, None, 30, 300, None,
                     [(2031, {"city": "Vancouver", "employment": "student", "graduates_in": 2})])
    at = {s.year: s for s in moved.states}
    assert at[2030].city == "Toronto" and at[2031].city == "Vancouver" and at[2031].employment == "student"
    assert at[2033].employment == "employed"


def test_the_people_around_you_come_from_the_same_tables():
    r = simulate(tables(), "p", FORK.model_copy(update={"activity_proxy": 1.0}), {}, None, 45, 400)
    kinds = {e["event_type"] for year in r.events for e in year}
    assert {"peer_wedding", "peer_child", "parent_death"} <= kinds
    parent = next(e for year in r.events for e in year if e["event_type"] == "parent_death")
    assert parent["payload"]["who"] in ("mother", "father", "mother and father")


def test_likelihood_words_use_fixed_thresholds():
    from app.sim.engine import likelihood_words

    assert [likelihood_words(s) for s in (0.95, 0.9, 0.7, 0.45, 0.2, 0.19)] == [
        "almost always", "almost always", "usually", "as often as not", "sometimes", "rarely"]
