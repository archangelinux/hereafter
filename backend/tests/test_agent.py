"""The question-asking agent: what it checks, how it chooses, and that it cannot be talked into guessing.

Everything runs offline with a scripted fake in place of the language model.
"""

import json

import pytest

from app.agent import questions, uncertainty, verify
from app.agent import context
from app.agent.context import Context, fixture_names
from app.agent.engine import MAX_QUESTIONS, Agent, AgentError
from app.agent.model import Choice, Cite, ContextItem, Event, Gate, Priorities, Route, Session
from app.agent.prompts import (AnswerReading, GapUpdate, JEvent, JGate, PCite, PEvent, PRoute, PriorityJudgement, PriorityP,
                               QChoice, RouteJudgement, RoutesProposal, WrittenQuestion)

ITEMS = [
    ContextItem(id=1, source="linkedin", date="2026-09", text="Senior Backend Engineer at Acme Payments in Toronto since 2022."),
    ContextItem(id=2, source="github", date="2026-07", text="Maintains a Rust command-line tool with 340 stars."),
    ContextItem(id=3, source="chat", date="2026-08", text="Asked how startup equity and vesting cliffs work."),
]
GOOD_Q = WrittenQuestion(
    question="Your profile says you've been at Acme Payments since 2022; could you relocate abroad for the new job?",
    choices=[QChoice(text="Yes, I could", resolves="met"), QChoice(text="No, I can't", resolves="unmet")],
    grounding=[PCite(item=1, quote="Senior Backend Engineer at Acme Payments in Toronto")])


OPTS = ["Berlin startup", "Stay at Acme"]


def ctx() -> Context:
    return Context([i.model_copy() for i in ITEMS], about="a test engineer")


def ev(key, dim, val, bin_, impact=2):
    return PEvent(key=key, label=f"outcome {key}", dimension=dim, valence=val, impact=impact, bin=bin_, category="career")


class FakeBrain:
    """Two routes; A's best outcomes depend on one requirement (relocating), so that question is worth asking."""

    def __init__(self, gate_p=0.5, gate_cites=None, questions=None, reading=None, gates=True, priorities_cited=True, typical=0.5):
        self.gate_p, self.gate_cites, self.typical = gate_p, gate_cites or [], typical
        self.queue, self.reading, self.gates = list(questions or []), reading, gates
        self.priorities_cited = priorities_cited
        self.calls = {"write": [], "read": 0}

    def propose_routes(self, decision, options, record, about):
        a = PRoute(title="Berlin startup", summary="Move and join a seed-stage startup.",
                   events=[ev("a_money", "money", 1, "usually"), ev("a_growth", "growth", 1, "usually"),
                           ev("a_free", "freedom", 1, "usually"), ev("a_burn", "wellbeing", -1, "sometimes")])
        b = PRoute(title="Stay at Acme", summary="Keep the current job.",
                   events=[ev("b_money", "money", 1, "as often as not"), ev("b_stab", "stability", 1, "usually"),
                           ev("b_bored", "growth", -1, "sometimes"), ev("b_free", "freedom", 1, "rare")])
        return RoutesProposal(routes=[a, b])

    def judge_route(self, decision, route, record):
        neutral = [JEvent(key=e["key"], personal_fit=3, experience_fit=3, difficulty=3, accessibility=3, evidence_strength=1, cites=[], note="") for e in route["events"]]
        gates = []
        if self.gates and route["title"] == "Berlin startup":
            gates = [JGate(requirement="You are allowed to work in Germany", applies_to=["a_money", "a_growth"], p_typical=self.typical, p_met=self.gate_p, cites=self.gate_cites)]
        return RouteJudgement(events=neutral, gates=gates)

    def judge_priorities(self, decision, routes, record):
        cites = [PCite(item=3, quote="Asked how startup equity and vesting")] if self.priorities_cited else []
        return PriorityJudgement(probs=[PriorityP(dimension=d, p=0.2) for d in ("money", "growth", "stability", "wellbeing", "freedom")], cites=cites)

    def write_question(self, spec, record, feedback):
        self.calls["write"].append((spec, list(feedback)))
        if self.queue:
            nxt = self.queue.pop(0)
            return nxt(spec) if callable(nxt) else nxt
        if spec["kind"] == "priority":
            return WrittenQuestion(question="You've been asking how startup equity works; what matters most to you here?",
                                   choices=[QChoice(text="Earning more", resolves="money"), QChoice(text="Learning fast", resolves="growth"),
                                            QChoice(text="Feeling secure", resolves="stability")],
                                   grounding=[PCite(item=3, quote="Asked how startup equity and vesting")])
        return GOOD_Q

    def read_answer(self, question, answer, gaps):
        self.calls["read"] += 1
        return self.reading


def agent(tmp_path, brain=None, **kw):
    return Agent(brain or FakeBrain(**kw), ctx(), "fixture:test", root=tmp_path)


# --- receipts and question checks ---


def test_a_citation_counts_only_if_its_quote_is_really_in_the_item():
    by_id = {i.id: i for i in ITEMS}
    ok = Cite(item=1, quote="senior backend engineer at ACME payments")           # case and punctuation are forgiven
    wrong_item = Cite(item=2, quote="Senior Backend Engineer at Acme Payments")
    invented = Cite(item=1, quote="Led a team of forty engineers at Acme")
    too_short = Cite(item=1, quote="Acme Payments")
    missing = Cite(item=99, quote="Senior Backend Engineer at Acme")
    assert verify.valid_cites([ok, wrong_item, invented, too_short, missing], by_id) == [ok]


def test_a_question_may_not_mention_numbers_or_names_that_are_not_in_the_context():
    allowed = " ".join(i.text for i in ITEMS) + " Should I take the Berlin startup offer or stay"
    assert verify.unknown_mentions("Would you leave Acme Payments for Berlin?", allowed) == []
    assert verify.unknown_mentions("Would you leave Acme Payments for Google?", allowed) == ["Google"]
    assert verify.unknown_mentions("You've been there for 9 years, right?", allowed) == ["9"]
    assert verify.unknown_mentions("Toronto is home, is it?", allowed) == []       # sentence-initial words are not names


def test_a_good_question_passes_and_each_rule_is_enforced():
    by_id = {i.id: i for i in ITEMS}
    allowed = " ".join(i.text for i in ITEMS) + " relocate abroad new job"
    choices = [Choice(text="Yes, I could", resolves="met"), Choice(text="No, I can't", resolves="unmet")]
    cite = [Cite(item=1, quote="Senior Backend Engineer at Acme Payments in Toronto")]
    q = "Your profile says you've been at Acme Payments since 2022; could you relocate abroad for the new job?"
    assert verify.check_question(q, choices, cite, by_id, allowed) == []
    bad = lambda text, ch=choices, c=cite: verify.check_question(text, ch, c, by_id, allowed)
    assert any("ground" in p for p in verify.check_question(q, choices, [], by_id, allowed))
    assert any("exactly one question" in p for p in bad("Could you relocate? And would you?"))
    assert any("probabilit" in p for p in bad("What is the probability you would relocate abroad?"))
    assert any("words" in p for p in bad("could you relocate " + "really " * 40 + "abroad?"))
    assert any("2 to 4" in p for p in bad(q, choices[:1]))
    assert any("different" in p for p in bad(q, [choices[0], Choice(text="yes i could", resolves="unmet")]))


# --- which question is worth asking ---


def session(p_gate=0.5, priorities="resolved", both_dominated=False) -> Session:
    brain = FakeBrain()
    proposal = brain.propose_routes("d", [], "", "")
    s = Session(id="t", created="now", decision="Berlin or Acme?", who="fixture:test", items=list(ITEMS))
    for i, pr in enumerate(proposal.routes, 1):
        s.routes.append(Route(id=f"r{i}", title=pr.title, events=[Event(key=e.key, label=e.label, dimension=e.dimension, valence=e.valence, impact=e.impact, bin=e.bin) for e in pr.events]))
    s.gates = [Gate(id="r1.g1", route_id="r1", requirement="You are allowed to work in Germany", applies_to=["a_money", "a_growth"], p_met=p_gate)]
    s.priorities = Priorities(status=priorities)
    if both_dominated:
        s.routes[0].events = [Event(key="a_bad", label="x", dimension="money", valence=-1, bin="usually")]
        s.gates = []
    return s


def test_the_value_of_a_question_is_positive_only_when_the_answer_could_change_the_choice():
    s = session()
    top = uncertainty.rank_gaps(s)[0]
    assert top.gap == "r1.g1" and top.evpi > 0 and 0 < top.flip <= 1 and top.affects == ["r1"]
    assert top.flip == pytest.approx(0.5, abs=0.01), "the gate is a coin flip and it decides which route leads"

    # if the gate could not change which route leads, nobody should be asked about it
    s2 = session()
    s2.routes[0].events = [e for e in s2.routes[0].events if e.key != "a_free"]
    s2.routes[0].events[0].bin = "rare"
    s2.routes[0].events[1].bin = "rare"
    dead = uncertainty.rank_gaps(s2)[0]
    assert dead.evpi == pytest.approx(0, abs=1e-9) and dead.flip == 0 and uncertainty.should_stop([dead]) is not None


def test_a_gate_that_is_already_settled_or_answered_is_never_ranked():
    assert uncertainty.rank_gaps(session(p_gate=0.99)) == []
    s = session()
    s.gates[0].status = "resolved"
    assert uncertainty.rank_gaps(s) == []
    assert uncertainty.should_stop([]) == "there is nothing left that we are unsure about"


def test_priorities_are_worth_asking_when_routes_differ_by_what_they_deliver():
    s = session(p_gate=0.99, priorities="open")
    ranked = uncertainty.rank_gaps(s)
    assert [g.gap for g in ranked] == ["priorities"] and ranked[0].evpi >= 0
    assert dict((name, round(p, 2)) for p, name in ranked[0].outcomes)["money"] == 0.2


def test_an_unmet_requirement_collapses_the_outcomes_that_depend_on_it():
    s = session()
    before = uncertainty.event_likelihoods(s)["r1"]
    s.gates[0].p_met, s.gates[0].status = 0.03, "resolved"
    after = uncertainty.event_likelihoods(s)["r1"]
    assert after["a_money"] < 0.1 < before["a_money"] and after["a_free"] == before["a_free"]
    # ...but a requirement failing never makes a route's RISKS go away: only its upsides
    s.gates[0].applies_to = ["a_burn"]                         # a_burn is a bad outcome
    s.gates[0].p_met = 0.03
    assert uncertainty.event_likelihoods(s)["r1"]["a_burn"] == before["a_burn"]


def test_ignoring_impact_picks_the_status_quo_and_using_it_does_not():
    """Staying put is full of near-certain small things; a leap has uncertain but life-changing ones."""
    s = session(p_gate=0.99)
    stay = Route(id="r2", title="Stay", events=[Event(key=f"t{i}", label="routine", dimension="stability", valence=1, bin="almost certainly", impact=1) for i in range(3)])
    leap = Route(id="r1", title="Leap", events=[Event(key=f"b{i}", label="career-defining", dimension="stability", valence=1, bin="as often as not", impact=3) for i in range(3)])
    s.routes, s.gates = [leap, stay], []
    assert uncertainty.leader(uncertainty.scores(s)) == "r1", "with impact, three coin-flip life-changers beat three trivial certainties"
    for e in stay.events + leap.events:
        e.impact = 2                                        # the old model: every outcome counts the same
    assert uncertainty.leader(uncertainty.scores(s)) == "r2", "without it the mundane certainties win"


def test_the_scoring_module_cannot_reach_the_language_model():
    for name in ("llm", "openai", "anthropic", "prompts"):
        assert name not in vars(uncertainty) and name not in vars(verify)


# --- the loop ---


def test_start_builds_routes_and_only_believes_gates_that_have_receipts(tmp_path):
    invented = [PCite(item=1, quote="Holds a German work visa valid until 2028")]
    real = [PCite(item=1, quote="Senior Backend Engineer at Acme Payments in Toronto")]
    a = agent(tmp_path, gate_p=0.9, gate_cites=invented, typical=0.3)
    a.start("Berlin or Acme?", OPTS)
    assert a.s.gates[0].p_met == 0.3 and a.s.gates[0].cites == [] and a.s.gates[0].basis == "typical", \
        "a made-up quote earns no confidence: the typical person's base rate stands in, not the model's claim about you"
    b = agent(tmp_path, gate_p=0.9, gate_cites=real)
    b.start("Berlin or Acme?", OPTS)
    assert b.s.gates[0].p_met == 0.9 and len(b.s.gates[0].cites) == 1 and b.s.gates[0].basis == "record"
    assert [r.title for r in b.s.routes] == OPTS
    c = agent(tmp_path, priorities_cited=False)
    c.start("Berlin or Acme?", OPTS)
    assert set(c.s.priorities.probs.values()) == {0.2}, "priorities without a receipt stay flat"


def test_an_answer_becomes_memory_moves_the_scores_and_is_never_asked_again(tmp_path):
    a = agent(tmp_path)
    a.start("Berlin startup or stay at Acme?", OPTS)
    a.s.priorities.status = "resolved"                      # isolate the requirement question
    qa = a.next_question()
    assert qa.gap == "r1.g1" and not qa.fallback and qa.grounding and "relocate" in qa.question
    n_before = len(a.ctx.items)
    done = a.answer("choice", "2")                          # "No, I can't"
    assert done.kind == "choice" and done.answer == "No, I can't"
    assert len(a.ctx.items) == n_before + 1 and a.ctx.items[-1].source == "told" and "No, I can't" in a.ctx.items[-1].text
    assert done.answer_item == a.ctx.items[-1].id
    assert done.after["r1"] < done.before["r1"], "route A depended on it, so it fell"
    assert uncertainty.leader(done.before) == "r1" and uncertainty.leader(done.after) == "r2", "and the leader changed"
    assert a.s.gates[0].status == "resolved" and a.s.gates[0].p_met <= 0.15
    assert a.next_question() is None and "nothing left" in a.s.stop_reason


def test_never_more_than_three_questions_and_a_skip_is_not_repeated(tmp_path):
    a = agent(tmp_path)
    a.start("Berlin startup or stay at Acme?", OPTS)
    first = a.next_question()
    a.answer("skip")
    assert first.kind == "skip" and a.s.gates[0].status == "skipped" or a.s.priorities.status == "skipped"
    asked = {first.gap}
    while (qa := a.next_question()) is not None:
        assert qa.gap not in asked, "skipped or answered unknowns are not asked again"
        asked.add(qa.gap)
        a.answer("skip")
    assert len(a.s.qas) <= MAX_QUESTIONS == 3


def test_it_stops_early_when_no_question_could_change_the_answer(tmp_path):
    a = agent(tmp_path, gates=False)
    a.start("Berlin startup or stay at Acme?", OPTS)
    a.s.priorities.status = "resolved"
    assert a.next_question() is None and a.s.status == "done" and a.s.qas == []


def test_it_always_asks_one_question_even_when_the_routes_look_settled_but_then_stops(tmp_path):
    class Lopsided(FakeBrain):
        def propose_routes(self, *a):
            good = PRoute(title="Berlin startup", summary="s", events=[ev(f"g{i}", "money", 1, "usually") for i in range(3)])
            bad = PRoute(title="Stay at Acme", summary="s", events=[ev(f"b{i}", "money", -1, "usually") for i in range(3)])
            return RoutesProposal(routes=[good, bad])

    a = Agent(Lopsided(gates=False), ctx(), "fixture:test", root=tmp_path)
    a.start("Berlin startup or stay at Acme?", OPTS)
    top = a.ranked()[0]
    assert uncertainty.should_stop([top]) is not None, "on the numbers nothing would change the answer"
    assert a.next_question() is not None, "but the first question is still asked"
    a.answer("skip")
    assert a.next_question() is None and a.s.status == "done"


def test_naming_where_a_fact_came_from_is_not_inventing_it():
    by_id = {i.id: i for i in ITEMS}
    allowed = " ".join(i.text for i in ITEMS) + " LinkedIn linkedin github chat relocate abroad job"
    cite = [Cite(item=1, quote="Senior Backend Engineer at Acme Payments in Toronto")]
    choices = [Choice(text="Yes", resolves="met"), Choice(text="No", resolves="unmet")]
    q = "Your LinkedIn shows Senior Backend Engineer at Acme Payments in Toronto; could you relocate abroad for a job?"
    assert verify.check_question(q, choices, cite, by_id, allowed) == []


def test_a_question_that_invents_a_fact_is_sent_back_once_then_replaced_by_a_plain_one(tmp_path):
    invented = WrittenQuestion(question="Since you led 40 engineers at Google, could you relocate abroad?",
                               choices=GOOD_Q.choices, grounding=GOOD_Q.grounding)
    a = agent(tmp_path, brain=FakeBrain(questions=[invented, invented]))
    a.start("Berlin startup or stay at Acme?", OPTS)
    a.s.priorities.status = "resolved"
    qa = a.next_question()
    assert qa.fallback and qa.grounding == [] and "Google" not in qa.question and "40" not in qa.question
    assert "allowed to work in Germany" in qa.question and [c.resolves for c in qa.choices] == ["met", "unmet"]
    calls = a.brain.calls["write"]
    assert len(calls) == 2 and calls[0][1] == [] and any("Google" in f for f in calls[1][1]), "the model was told exactly what was wrong"
    assert any("failed checks" in w for w in a.s.warnings)

    good_second = agent(tmp_path, brain=FakeBrain(questions=[invented, GOOD_Q]))
    good_second.start("Berlin startup or stay at Acme?", OPTS)
    good_second.s.priorities.status = "resolved"
    assert not good_second.next_question().fallback


def test_a_free_text_answer_only_counts_for_words_the_person_actually_wrote(tmp_path):
    lie = AnswerReading(updates=[GapUpdate(gap="r1.g1", resolves="met", p=0.97, quote="I hold a German passport")])
    a = agent(tmp_path, brain=FakeBrain(reading=lie))
    a.start("Berlin startup or stay at Acme?", OPTS)
    a.s.priorities.status = "resolved"
    a.next_question()
    done = a.answer("text", "I'm not sure yet, need to check with HR")
    assert a.brain.calls["read"] == 1
    assert a.s.gates[0].p_met == 0.5 and a.s.gates[0].status == "skipped" and a.s.gates[0].basis == "typical", "the quote was not in their words, so nothing was learned"
    assert done.answer_item is not None, "but what they said is still remembered"

    honest = AnswerReading(updates=[GapUpdate(gap="r1.g1", resolves="met", p=0.9, quote="I hold a German passport")])
    b = agent(tmp_path, brain=FakeBrain(reading=honest))
    b.start("Berlin startup or stay at Acme?", OPTS)
    b.s.priorities.status = "resolved"
    b.next_question()
    b.answer("text", "Actually I hold a German passport")
    assert b.s.gates[0].status == "resolved" and b.s.gates[0].p_met >= 0.85


def test_a_typed_answer_that_matches_a_choice_needs_no_interpretation(tmp_path):
    a = agent(tmp_path)
    a.start("Berlin startup or stay at Acme?", OPTS)
    a.s.priorities.status = "resolved"
    a.next_question()
    done = a.answer("text", "yes, i could")
    assert done.kind == "choice" and a.s.gates[0].p_met >= 0.85 and a.brain.calls["read"] == 0


def test_the_session_is_saved_every_step_and_loads_back_exactly(tmp_path):
    a = agent(tmp_path)
    a.start("Berlin startup or stay at Acme?", OPTS)
    a.s.priorities.status = "resolved"
    a.next_question()
    a.answer("choice", "1")
    a.decide("r1")
    folder = tmp_path / a.s.id
    assert (folder / "session.json").exists() and (folder / "memory.md").exists()
    loaded = Agent.load_session(a.s.id, tmp_path)
    assert loaded == a.s and loaded.status == "decided" and loaded.decided_route == "r1"
    text = (folder / "memory.md").read_text()
    assert "Senior Backend Engineer at Acme Payments" in text and "(your answer)" in text and "decided **Berlin startup**" in text
    assert "You are allowed to work in Germany" in text and "Yes, I could" in text
    with pytest.raises(AgentError):
        a.decide("r9")


def test_it_refuses_to_start_when_the_model_cannot_lay_out_routes(tmp_path):
    class Dead(FakeBrain):
        def propose_routes(self, *a):
            return None

    with pytest.raises(AgentError, match="could not lay out the routes"):
        Agent(Dead(), ctx(), "fixture:test", root=tmp_path).start("A or B?", ["A", "B"])
    assert list(tmp_path.iterdir()) == [], "nothing is saved for a session that never started"


def test_when_the_judge_is_down_it_says_so_and_asks_only_about_priorities(tmp_path):
    class NoJudge(FakeBrain):
        def judge_route(self, *a):
            return None

        def judge_priorities(self, *a):
            return None

    a = Agent(NoJudge(), ctx(), "fixture:test", root=tmp_path)
    a.start("Berlin startup or stay at Acme?", OPTS)
    assert a.s.gates == [] and len(a.s.warnings) == 3
    qa = a.next_question()
    assert qa is None or qa.gap == "priorities"


# --- context and fixtures ---

# The repo ships no built-in people. A fixture is just a JSON file of numbered items and a line about them;
# these tests write one into a temporary folder and point the loader there.
FIXTURE = {
    "about": "a test engineer",
    "items": [
        {"source": "linkedin", "date": "2026-09", "text": "Senior Backend Engineer at Acme Payments, Toronto, since 2022. Led the ledger migration to services."},
        {"source": "linkedin", "date": "2022-05", "text": "Software Engineer at a payments company; built a Rust reconciliation tool."},
        {"source": "github", "date": "2026-07", "text": "Maintains an open-source Rust command-line tool for ledgers with 340 stars."},
        {"source": "github", "date": "2026-02", "text": "Contributed a fix to a distributed database project."},
        {"source": "instagram", "date": "2026-08", "text": "Photos from a climbing trip in Squamish."},
        {"source": "chat", "date": "2026-08", "text": "Asked how startup equity and vesting cliffs work."},
        {"source": "chat", "date": "2026-09", "text": "Asked how much runway a founder should have saved before quitting a job."},
        {"source": "told", "date": "2026-09", "text": "Said they might relocate for the right offer."},
    ],
}


@pytest.fixture()
def people(tmp_path, monkeypatch):
    folder = tmp_path / "people"
    folder.mkdir()
    (folder / "dev.json").write_text(json.dumps(FIXTURE))
    monkeypatch.setattr(context, "FIXTURES", folder)
    return folder


def test_a_fixture_file_loads_with_numbered_items_from_several_sources(people):
    assert fixture_names() == ["dev"]
    c = Context.from_fixture("dev")
    assert [i.id for i in c.items] == list(range(1, len(c.items) + 1))
    assert len({i.source for i in c.items}) >= 3 and c.about


def test_with_no_fixtures_there_are_none(tmp_path, monkeypatch):
    monkeypatch.setattr(context, "FIXTURES", tmp_path / "nothing-here")
    assert fixture_names() == []
    with pytest.raises(SystemExit):
        Context.from_fixture("dev")


def test_told_items_are_always_kept_and_numbering_never_changes(people):
    c = Context.from_fixture("dev")
    told = c.add_told("Asked “x” — they said: I could relocate")
    assert told.id == len(c.items) and told.source == "told"
    few = c.relevant("rust ledger startup equity", k=5)
    assert len(few) == 5 and told in few and [i.id for i in few] == sorted(i.id for i in few)


def test_the_cli_runs_a_scripted_conversation_end_to_end(tmp_path, monkeypatch, people):
    from app.agent import cli

    monkeypatch.setenv("HEREAFTER_SESSIONS", str(tmp_path))
    monkeypatch.setattr(cli, "LLMBrain", FakeBrain)
    code = cli.main(["--fixture", "dev", "-q", "Berlin startup or stay at Acme?", "--options", "Berlin startup|Stay at Acme",
                     "--answers", "s;1;e", "--decide", "2"])
    assert code == 0
    saved = list(tmp_path.glob("*/session.json"))
    assert len(saved) == 1
    s = Session.model_validate_json(saved[0].read_text())
    assert s.status == "decided" and s.decided_route == "r2" and 1 <= len(s.qas) <= 3
    assert cli.main(["--show", "LATEST"]) == 0
    assert cli.main(["--fixtures"]) == 0


def test_the_agent_prompts_forbid_what_the_checks_enforce():
    from app.agent import prompts

    assert "COPIED EXACTLY" in prompts.QUESTION_SYSTEM and "at most 25 words" in prompts.QUESTION_SYSTEM
    assert "p_typical" in prompts.JUDGE_SYSTEM and "DIRECTLY supports" in prompts.JUDGE_SYSTEM and "never guess" in prompts.NO_INVENTING
    assert questions.TOP_CANDIDATES == 4
