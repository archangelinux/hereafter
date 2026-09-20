"""The Agent Builder planner: what it maps, what it refuses to map, and that it stays optional.

No cluster is involved. `plan` is exercised against a canned `converse` response, because what
matters here is the translation — the agent's tool calls becoming store queries — not Elastic's
side of it.
"""

from app import agent_builder, config, state

CONVERSE = {
    "steps": [
        {"type": "reasoning", "tool_call_group_id": "g1",
         "reasoning": "Start with the newest events in each domain."},
        {"type": "tool_call", "tool_call_group_id": "g1", "tool_id": "hereafter.latest_in_domain",
         "params": {"person_id": "demo", "domain": "career"}},
        {"type": "tool_call", "tool_call_group_id": "g1", "tool_id": "hereafter.domain_histogram",
         "params": {"person_id": "demo", "domain": "housing"}},
        {"type": "reasoning", "tool_call_group_id": "g2", "reasoning": "Housing is still open."},
        {"type": "tool_call", "tool_call_group_id": "g2", "tool_id": "hereafter.search_life_events",
         "params": {"person_id": "demo", "query": "apartment rent lease"}},
        # not one of ours, and not something the store can run
        {"type": "tool_call", "tool_call_group_id": "g2", "tool_id": "platform.core.execute_esql",
         "params": {"query": "FROM anything"}},
    ],
    "response": {"message": "done"},
}


def _canned(monkeypatch, payload=CONVERSE):
    monkeypatch.setattr(agent_builder.config, "ES_URL", "https://example.es.cloud:443")
    monkeypatch.setattr(agent_builder.config, "ES_API_KEY", "key")
    monkeypatch.setattr(agent_builder, "_call", lambda *a, **k: payload)


def test_tool_calls_become_store_queries_with_the_agents_reasons(monkeypatch):
    _canned(monkeypatch)
    plan = agent_builder.plan("demo", ["city", "housing"], {"education": "bachelor's"})

    assert [q["tool"] for q in plan] == ["latest_in_domain", "domain_histogram", "hybrid_search"]
    # person_id is passed to the store separately, and the search parameter is renamed to `text`
    assert plan[0]["args"] == {"domain": "career"}
    assert plan[2]["args"] == {"text": "apartment rent lease"}
    # each query carries the reasoning from its own round, so the agent log says why
    assert plan[0]["reason"] == "Start with the newest events in each domain."
    assert plan[2]["reason"] == "Housing is still open."


def test_a_tool_with_no_store_equivalent_is_ignored_rather_than_run(monkeypatch):
    _canned(monkeypatch)
    plan = agent_builder.plan("demo", ["city"], {})
    assert all(q["tool"] in ("latest_in_domain", "domain_histogram", "hybrid_search") for q in plan)


def test_an_unreachable_agent_falls_back_instead_of_raising(monkeypatch):
    monkeypatch.setattr(agent_builder.config, "ES_URL", "https://example.es.cloud:443")
    monkeypatch.setattr(agent_builder.config, "ES_API_KEY", "key")

    def boom(*a, **k):
        raise OSError("cluster unreachable")

    monkeypatch.setattr(agent_builder, "_call", boom)
    assert agent_builder.plan("demo", ["city"], {}) is None


def test_no_tool_calls_means_no_plan_rather_than_an_empty_one(monkeypatch):
    _canned(monkeypatch, {"steps": [], "response": {"message": "nothing"}})
    assert agent_builder.plan("demo", ["city"], {}) is None


def test_the_planner_is_off_unless_asked_for(monkeypatch):
    """The default is the in-process planner, so nothing reaches the cluster on the hot path."""
    monkeypatch.setattr(config, "STATE_PLANNER", "llm")
    called = []
    monkeypatch.setattr(agent_builder, "plan", lambda *a: called.append(a))
    assert state._elastic_plan("demo", ["city"], {}) is None
    assert not called

    monkeypatch.setattr(config, "STATE_PLANNER", "elastic")
    monkeypatch.setattr(agent_builder, "plan", lambda *a: [{"tool": "latest_in_domain",
                                                           "args": {"domain": "career"}, "reason": "r"}])
    assert state._elastic_plan("demo", ["city"], {})[0]["tool"] == "latest_in_domain"
