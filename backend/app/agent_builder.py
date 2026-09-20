"""The retrieval agent, as an Elastic Agent Builder agent.

`state.py` has always had an agent at its centre: something that decides *which* store queries
to run to work out who a person is now, looks at what is still unknown, and decides again. This
module moves that decision to Elastic's own agent, and registers the queries it may choose from
as Agent Builder tools so they exist on the cluster rather than only inside this process.

The division of labour does not change, and it is the important part: the agent chooses the
queries. It does not get to say what the retrieved events *mean* — `state.reduce_events` is
plain code, and the agent's chosen queries are re-run here against `store` so that what reaches
it is typed `LifeEvent`s, not an agent's prose about them.

`setup()` is idempotent and lives behind `backend/scripts/agent_builder_setup.py`.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional
from urllib import error, request

from . import config

log = logging.getLogger("hereafter.agent_builder")

AGENT_ID = "hereafter.who_am_i"
LIFE_EVENTS = "hereafter.latest_in_domain"
HISTOGRAM = "hereafter.domain_histogram"
SEARCH = "hereafter.search_life_events"
EVIDENCE = "hereafter.recall_evidence"
DISTINCTIVE = "hereafter.distinctive_events"

# The store method each tool stands for, and how to read the agent's arguments into that
# method's keywords. A tool the agent calls that is not in here is logged and ignored.
TOOL_TO_STORE: dict[str, tuple[str, dict[str, str]]] = {
    LIFE_EVENTS: ("latest_in_domain", {"domain": "domain"}),
    HISTOGRAM: ("domain_histogram", {"domain": "domain"}),
    SEARCH: ("hybrid_search", {"query": "text", "nlQuery": "text"}),
}

INSTRUCTIONS = """You work out who a person is *now* from their append-only life log.

Call the hereafter.* tools to gather what you need, then stop. You are choosing which queries to
run — nothing else. Do not interpret, summarise, reconcile contradictions, or state conclusions
about the person: code downstream does that from the same events, and it must not be second-guessed.

Work slot by slot. The slots are: city, education, field, employment, income_band,
relationship_status, housing. Start with hereafter.latest_in_domain for the domain a slot lives
in (career, housing, relationship, money, health); if that does not settle it, use
hereafter.search_life_events once for that slot. Use hereafter.domain_histogram when you want
counts over time rather than individual events. Every tool takes person_id explicitly — pass it,
and never put the person's id into a search query, which searches their own events only anyway.

Two rounds of tool calls is normally enough and you should rarely need a third. Never call a
tool twice with the same arguments, and do not re-search a slot that came back empty: a log that
says nothing about a slot is a real answer, and the code downstream handles it. When you have
queried for every slot you can, reply with one short sentence saying so."""


def _url(path: str) -> str:
    return config.ES_URL.replace(".es.", ".kb.") + path


def _call(method: str, path: str, body: Optional[dict] = None, timeout: int = 90) -> Any:
    req = request.Request(
        _url(path), method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"ApiKey {config.ES_API_KEY}", "Content-Type": "application/json",
                 "kbn-xsrf": "true"})
    with request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else None


def _put(kind: str, spec: dict) -> str:
    """Create the tool or agent; update it in place if it is already there; replace it if the
    update is refused, which is what happens when a tool changes type."""
    ident = spec["id"]
    try:
        _call("POST", f"/api/agent_builder/{kind}", spec)
        return "created"
    except error.HTTPError as exc:
        detail = exc.read().decode()
        if "already exists" not in detail and exc.code != 409:
            raise RuntimeError(f"{kind}/{ident}: {detail[:400]}") from exc

    # An update may not restate `id` or `type`; changing a tool's type needs a replacement.
    update = {k: v for k, v in spec.items() if k not in ("id", "type")}
    try:
        _call("PUT", f"/api/agent_builder/{kind}/{ident}", update)
        return "updated"
    except error.HTTPError:
        _call("DELETE", f"/api/agent_builder/{kind}/{ident}")
        _call("POST", f"/api/agent_builder/{kind}", spec)
        return "replaced"


def tool_specs() -> list[dict]:
    events, evidence, runs = config.ES_INDEX, config.ES_EVIDENCE_INDEX, config.ES_RUNS_INDEX
    return [
        {"id": LIFE_EVENTS, "type": "esql", "tags": ["hereafter"],
         "description": "The newest real events in one domain of a person's life log. Use this "
                        "first when a slot is empty. Domains: career, housing, relationship, money, health.",
         "configuration": {
             "query": f'FROM {events} | WHERE person_id == ?person_id AND branch_id == "main" '
                      f"AND domain == ?domain | SORT date DESC "
                      f"| KEEP date, event_type, text, confidence, source | LIMIT 10",
             "params": {"person_id": {"type": "string", "description": "The person whose log to read."},
                        "domain": {"type": "string", "description": "career, housing, relationship, money or health."}}}},
        {"id": HISTOGRAM, "type": "esql", "tags": ["hereafter"],
         "description": "How many events of each type happened in each year of one domain. Use this "
                        "for density and pace over time, not for individual events.",
         "configuration": {
             "query": f'FROM {events} | WHERE person_id == ?person_id AND branch_id == "main" '
                      f'AND domain == ?domain | EVAL year = DATE_FORMAT("yyyy", date) '
                      f"| STATS events = COUNT(*) BY year, event_type | SORT year ASC | LIMIT 100",
             "params": {"person_id": {"type": "string", "description": "The person whose log to read."},
                        "domain": {"type": "string", "description": "career, housing, relationship, money or health."}}}},
        # Both searches are ES|QL rather than `index_search`, because an index_search tool takes
        # only a natural-language query and would read across every person in the index. The
        # person filter has to be a parameter the agent cannot opt out of.
        {"id": SEARCH, "type": "esql", "tags": ["hereafter"],
         "description": "Search one person's real life events by meaning, not just words: a query "
                        "about relocating finds 'moved to Waterloo'. Use this when listing a domain "
                        "did not settle a slot.",
         "configuration": {
             # SORT before KEEP: KEEP drops _score, and sorting on it afterwards is an error.
             "query": f"FROM {events} METADATA _score | WHERE person_id == ?person_id "
                      f'AND branch_id == "main" AND match(text_semantic, ?query) '
                      f"| SORT _score DESC | LIMIT 8 "
                      f"| KEEP date, event_type, text, confidence, source",
             "params": {"person_id": {"type": "string", "description": "The person whose log to read."},
                        "query": {"type": "string", "description": "What you are looking for, in plain words."}}}},
        {"id": EVIDENCE, "type": "esql", "tags": ["hereafter"],
         "description": "Search the shared evidence base: published figures, the sentence each was "
                        "quoted from, and its source URL. Public research, not anyone's private log.",
         "configuration": {
             "query": f"FROM {evidence} METADATA _score | WHERE kind == \"researched\" "
                      f"AND match(claim_semantic, ?query) "
                      f"| SORT _score DESC | LIMIT 8 "
                      f"| KEEP question, figure, unit, claim, snippet, source_url",
             "params": {"query": {"type": "string", "description": "The question you want a published figure for."}}}},
        {"id": DISTINCTIVE, "type": "esql", "tags": ["hereafter"],
         "description": "How often each kind of event happens across the thousand simulated lives of "
                        "one path. Use it to say what a path is actually like, or how rare something is.",
         "configuration": {
             "query": f"FROM {runs} | WHERE branch_id == ?branch_id | STATS lives = COUNT(*) BY event_key "
                      f"| SORT lives DESC | LIMIT 25",
             "params": {"branch_id": {"type": "string", "description": "The path's id."}}}},
    ]


def agent_spec() -> dict:
    return {
        "id": AGENT_ID, "name": "Hereafter — who am I now",
        "description": "Chooses which life-log queries answer 'who is this person now'. It picks the "
                       "queries; Hereafter's own code decides what the answers mean.",
        "configuration": {
            "instructions": INSTRUCTIONS,
            "tools": [{"tool_ids": [LIFE_EVENTS, HISTOGRAM, SEARCH]}],
        },
    }


def plan(person_id: str, empty: list[str], filled: dict) -> Optional[list[dict]]:
    """Ask the Elastic agent which store queries to run, and return them in `state.py`'s plan
    shape. The agent's *choices* are what comes back — its tool results are thrown away and the
    same queries re-run against `store`, so what reaches `reduce_events` is typed `LifeEvent`s
    and no model is between the events and what they are taken to mean.

    Returns None whenever the agent cannot answer, which tells the caller to fall back to the
    planners in `state.py`. Nothing here is allowed to break building a state vector."""
    if not (config.ES_URL and config.ES_API_KEY):
        return None
    known = ", ".join(f"{k}={v}" for k, v in filled.items()) or "nothing yet"
    prompt = (f'Person id is "{person_id}". Already known: {known}. '
              f"Still empty: {', '.join(empty)}.")
    try:
        resp = _call("POST", "/api/agent_builder/converse",
                     {"agent_id": AGENT_ID, "input": prompt},
                     timeout=config.STATE_PLANNER_TIMEOUT)
    except Exception as exc:
        log.warning("Agent Builder planner unavailable (%s); falling back", exc)
        return None

    steps = resp.get("steps", [])
    reasons = {s["tool_call_group_id"]: s.get("reasoning", "") for s in steps
               if s.get("type") == "reasoning"}
    chosen: list[dict] = []
    for step in steps:
        if step.get("type") != "tool_call":
            continue
        mapped = TOOL_TO_STORE.get(step.get("tool_id", ""))
        if not mapped:
            log.info("agent called %s, which has no store equivalent; ignored", step.get("tool_id"))
            continue
        method, keys = mapped
        args = {store_kw: value for param, value in (step.get("params") or {}).items()
                if (store_kw := keys.get(param))}
        if args:
            chosen.append({"tool": method, "args": args,
                           "reason": reasons.get(step.get("tool_call_group_id"), "").strip()})
    return chosen or None


def setup() -> list[str]:
    # The agent holds references to the tools, and a referenced tool cannot be replaced, so the
    # agent goes first and is rebuilt at the end.
    try:
        _call("DELETE", f"/api/agent_builder/agents/{AGENT_ID}")
    except error.HTTPError:
        pass
    done = [f"{spec['id']}: {_put('tools', spec)}" for spec in tool_specs()]
    done.append(f"{AGENT_ID}: {_put('agents', agent_spec())}")
    return done


def teardown() -> list[str]:
    done = []
    for path in [f"agents/{AGENT_ID}"] + [f"tools/{s['id']}" for s in tool_specs()]:
        try:
            _call("DELETE", f"/api/agent_builder/{path}")
            done.append(f"{path}: deleted")
        except error.HTTPError as exc:
            done.append(f"{path}: {exc.code}")
    return done
