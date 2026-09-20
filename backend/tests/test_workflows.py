"""The evidence audit workflow: the definition it renders, how it registers, and the one
behaviour that matters in the app — stale evidence is never reused from memory.

No cluster is involved. The Kibana calls are canned.
"""

import json

import pytest

from app import config, workflows


def test_the_definition_is_valid_yaml_and_writes_only_where_it_should(monkeypatch):
    monkeypatch.setattr(config, "EVIDENCE_MAX_AGE_DAYS", 90)
    monkeypatch.setattr(config, "ES_EVIDENCE_INDEX", "ev-idx")
    text = workflows.definition()

    assert "every: 24h" in text and "- type: manual" in text
    assert "now-90d" in text
    # it may touch the evidence index and the audit index, and nothing else — above all not the
    # append-only life log
    touched = {line.split("path:")[1].strip().split("?")[0].strip("/").split("/")[0]
               for line in text.splitlines() if "path:" in line}
    assert touched == {"ev-idx", workflows.AUDIT_INDEX}
    assert config.ES_INDEX not in text


def test_registration_sweeps_old_copies_because_creating_does_not_replace(monkeypatch):
    calls = []

    def fake(method, path, body=None, timeout=120):
        calls.append((method, path, body))
        if method == "GET":
            return {"results": [{"id": "hereafter-evidence-audit", "name": workflows.WORKFLOW_ID},
                                {"id": "hereafter-evidence-audit-1", "name": workflows.WORKFLOW_ID},
                                {"id": "something-else", "name": "not ours"}]}
        if method == "DELETE":
            return {"deleted": len(body["ids"])}
        return {"created": [{"id": "hereafter-evidence-audit-2"}]}

    monkeypatch.setattr(workflows, "_call", fake)
    assert workflows.setup() == "replaced as hereafter-evidence-audit-2"

    deleted = [b["ids"] for m, _, b in calls if m == "DELETE"]
    assert deleted == [["hereafter-evidence-audit", "hereafter-evidence-audit-1"]]  # not the stranger


def test_running_resolves_the_id_by_name_since_the_cluster_keeps_suffixing_it(monkeypatch):
    seen = {}

    def fake(method, path, body=None, timeout=120):
        if method == "GET":
            return {"results": [{"id": "hereafter-evidence-audit-7", "name": workflows.WORKFLOW_ID,
                                 "lastUpdatedAt": "2026-09-20T08:00:00Z"},
                                {"id": "hereafter-evidence-audit-3", "name": workflows.WORKFLOW_ID,
                                 "lastUpdatedAt": "2026-09-19T08:00:00Z"}]}
        seen["params"] = body["tool_params"]
        return {"results": [{"data": {"execution": {"status": "completed"}}}]}

    monkeypatch.setattr(workflows, "_call", fake)
    assert workflows.run()["status"] == "completed"
    assert seen["params"]["workflowId"] == "hereafter-evidence-audit-7"  # the newest, not the name


def test_running_an_unregistered_workflow_says_so(monkeypatch):
    monkeypatch.setattr(workflows, "_call", lambda *a, **k: {"results": []})
    with pytest.raises(RuntimeError, match="not registered"):
        workflows.run()


def test_the_local_store_reports_no_audit_rather_than_failing():
    assert workflows.health() == {"available": False,
                                  "reason": "the local store keeps no evidence audit"}


def test_stale_evidence_is_filtered_out_of_recall(monkeypatch):
    """The flag only means something because `remembered` refuses to offer what it marks."""
    from app.store import ElasticStore

    captured = {}

    class FakeES:
        def search(self, **kwargs):
            captured.update(kwargs)
            return {"hits": {"hits": []}}

    store = ElasticStore.__new__(ElasticStore)
    store.es = FakeES()
    store.evidence_index = "ev-idx"
    store.remembered("how many students finish the degree")

    body = json.dumps(captured["retriever"])
    assert '"must_not": [{"term": {"stale": true}}]' in body


def test_the_audit_endpoint_refuses_politely_without_a_cluster(client):
    person = client.post("/people", json={"birth_year": 2000}).json()
    client.headers["Authorization"] = f"Bearer {person['token']}"
    reply = client.post(f"/evidence/audit?person_id={person['person_id']}")
    assert reply.status_code == 400
    assert "Elasticsearch" in reply.json()["detail"]


def test_evidence_health_is_owner_only(client):
    mine = client.post("/people", json={"birth_year": 2000}).json()
    theirs = client.post("/people", json={"birth_year": 1990}).json()
    client.headers["Authorization"] = f"Bearer {mine['token']}"
    assert client.get(f"/evidence/health?person_id={theirs['person_id']}").status_code == 403
