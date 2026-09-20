"""The evidence audit, as an Elastic Workflow.

Hereafter reuses a published figure instead of crawling for it again when a cross-encoder says
the stored question and the new one are the same question (`research.py`). That judgement is
about meaning and has no sense of time, so on its own it will happily hand back a rent figure
from two years ago.

This is the part that has to keep running when nobody is looking, so it belongs on the cluster
rather than in a request handler: a scheduled Workflow marks researched evidence older than
`HEREAFTER_EVIDENCE_MAX_AGE_DAYS` as `stale`, clears the flag on anything fresh, and writes an
audit document. `remembered()` filters stale evidence out, so a figure that has aged out is
simply researched again the next time it is needed.

It writes only to the evidence index and the audit index. The life log is append-only and no
workflow touches it.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional
from urllib import error, request

from . import config

log = logging.getLogger("hereafter.workflows")

WORKFLOW_ID = "hereafter-evidence-audit"
AUDIT_INDEX = "hereafter-workflow-runs"
# Stamps `at` from _ingest.timestamp: the workflow templating renders dates in a
# format Elasticsearch will not parse, so the cluster supplies the time itself.
AUDIT_PIPELINE = "hereafter-workflow-audit"


def _kibana(path: str) -> str:
    return config.ES_URL.replace(".es.", ".kb.") + path


def _call(method: str, path: str, body: Optional[dict] = None, timeout: int = 120) -> Any:
    req = request.Request(
        _kibana(path), method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"ApiKey {config.ES_API_KEY}", "Content-Type": "application/json",
                 "kbn-xsrf": "true"})
    with request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else None


def definition() -> str:
    """The workflow YAML. The age threshold is baked in at registration time rather than passed
    as a trigger input, so the scheduled run and a manual run can never disagree about it."""
    days = config.EVIDENCE_MAX_AGE_DAYS
    return f"""version: "1"
name: {WORKFLOW_ID}
description: >-
  Marks researched evidence older than {days} days as stale so it is re-researched instead of
  reused, and records what it found. Writes only to the evidence and audit indices.
enabled: true
triggers:
  - type: manual
  - type: scheduled
    with:
      every: 24h
steps:
  - name: mark_stale
    type: elasticsearch.request
    with:
      method: POST
      path: /{config.ES_EVIDENCE_INDEX}/_update_by_query?conflicts=proceed&refresh=true
      body:
        query:
          bool:
            filter:
              - term: {{ kind: researched }}
              - range: {{ retrieved_at: {{ lt: now-{days}d }} }}
        script:
          lang: painless
          source: "ctx._source.stale = true; ctx._source.checked_at = System.currentTimeMillis()"

  - name: mark_fresh
    type: elasticsearch.request
    with:
      method: POST
      path: /{config.ES_EVIDENCE_INDEX}/_update_by_query?conflicts=proceed&refresh=true
      body:
        query:
          bool:
            filter:
              - term: {{ kind: researched }}
              - range: {{ retrieved_at: {{ gte: now-{days}d }} }}
        script:
          lang: painless
          source: "ctx._source.stale = false; ctx._source.checked_at = System.currentTimeMillis()"

  - name: write_audit
    type: elasticsearch.request
    with:
      method: POST
      path: /{AUDIT_INDEX}/_doc?refresh=true&pipeline={AUDIT_PIPELINE}
      body:
        workflow: {WORKFLOW_ID}
        execution: "{{{{ execution.id }}}}"
        max_age_days: {days}
        stale: "{{{{ steps.mark_stale.output.total }}}}"
        fresh: "{{{{ steps.mark_fresh.output.total }}}}"
"""


def validate() -> dict:
    return _call("POST", "/api/agent_builder/tools/_execute", {
        "tool_id": "platform.workflows.validate_workflow",
        "tool_params": {"yaml": definition()},
    })


def registered() -> list[dict]:
    """Every workflow currently carrying our name. Creating does not replace: posting the same
    name again yields a second workflow with a suffixed id, so registration has to sweep."""
    listing = _call("GET", "/api/workflows") or {}
    return [w for w in listing.get("results", []) if w.get("name") == WORKFLOW_ID]


def _delete(ids: list[str]) -> int:
    """Deletion is a bulk call with the ids in the body; there is no per-id route."""
    if not ids:
        return 0
    return (_call("DELETE", "/api/workflows", {"ids": ids}) or {}).get("deleted", 0)


def setup() -> str:
    """Delete every copy of the workflow, then create one from the current definition."""
    removed = _delete([w["id"] for w in registered()])
    created = _call("POST", "/api/workflows", {"workflows": [{"yaml": definition()}]})
    made = (created or {}).get("created", [])
    if not made:
        raise RuntimeError(f"{WORKFLOW_ID}: nothing was created")
    # The cluster assigns the id and keeps suffixing it even after the previous copy is deleted,
    # so the id is not stable across registrations and is always resolved by name.
    return f"{'replaced' if removed else 'created'} as {made[0]['id']}"


def teardown() -> str:
    return f"deleted {_delete([w['id'] for w in registered()])}"


def current() -> Optional[dict]:
    """The registered workflow, newest first if several somehow exist."""
    found = sorted(registered(), key=lambda w: w.get("lastUpdatedAt") or "", reverse=True)
    return found[0] if found else None


def health() -> dict:
    """What the audit last found, plus the live counts, for `GET /evidence/health`."""
    from .store import get_store

    store = get_store()
    if getattr(store, "kind", "") != "elastic":
        return {"available": False, "reason": "the local store keeps no evidence audit"}

    out: dict[str, Any] = {"available": True, "max_age_days": config.EVIDENCE_MAX_AGE_DAYS,
                           "workflow": WORKFLOW_ID, "registered": bool(current())}
    try:
        counts = store.es.search(
            index=config.ES_EVIDENCE_INDEX, size=0,
            query={"bool": {"filter": [{"term": {"kind": "researched"}}]}},
            aggs={"stale": {"filters": {"filters": {
                "stale": {"term": {"stale": True}},
                "usable": {"bool": {"must_not": [{"term": {"stale": True}}]}},
            }}}},
        )
        buckets = counts["aggregations"]["stale"]["buckets"]
        out["researched"] = counts["hits"]["total"]["value"]
        out["stale"] = buckets["stale"]["doc_count"]
        out["usable"] = buckets["usable"]["doc_count"]
    except Exception as exc:
        log.warning("evidence counts unavailable (%s)", type(exc).__name__)
        out["available"] = False
        return out

    try:
        last = store.es.search(index=AUDIT_INDEX, size=1, sort=[{"at": "desc"}],
                               query={"term": {"workflow": WORKFLOW_ID}})
        hits = last["hits"]["hits"]
        out["last_run"] = hits[0]["_source"] if hits else None
    except Exception:
        out["last_run"] = None
    return out


def run() -> dict:
    """Execute the workflow now. Returns the execution as the cluster reported it."""
    workflow = current()
    if not workflow:
        raise RuntimeError(f"{WORKFLOW_ID} is not registered; run scripts/workflow_setup.py")
    result = _call("POST", "/api/agent_builder/tools/_execute", {
        "tool_id": "platform.core.execute_workflow",
        "tool_params": {"workflowId": workflow["id"], "inputs": {}},
    }, timeout=180)
    for item in (result or {}).get("results", []):
        execution = (item.get("data") or {}).get("execution")
        if execution:
            return execution
    raise RuntimeError(f"{WORKFLOW_ID}: no execution came back ({json.dumps(result)[:200]})")
