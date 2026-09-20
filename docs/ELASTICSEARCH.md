# Elasticsearch in Hereafter — technical README

Elastic Cloud Serverless, Elasticsearch 9.6. Three indices, one Agent Builder agent, five
registered tools, two Elastic Inference Service endpoints.

All Elasticsearch query code is in one file, [`backend/app/store.py`](../backend/app/store.py),
class `ElasticStore`. Agent Builder registration and the converse call are in
[`backend/app/agent_builder.py`](../backend/app/agent_builder.py). A `LocalStore` (SQLite) with
the same method surface is used when `ELASTICSEARCH_URL` is unset; the test suite runs that way.

## Who issues queries

| Component | Talks to the cluster | How |
|---|---|---|
| `backend/app/store.py` | Yes | The only ES client in the application. Every application query goes through it. Called from `state.py`, `scenarios.py`, `jev.py`, `research.py`, `branches.py`, `main.py`. |
| `backend/app/llm.py` (OpenAI) | **No** | No store import, no client, no credentials. `plan_queries` returns a typed `PlannedQuery` (`tool` ∈ {`latest_in_domain`, `domain_histogram`, `hybrid_search`}, plus `domain` or `text`, plus `reason`). Python validates it and runs the query. |
| Agent Builder agent | Yes, server-side | Runs its own ES\|QL tools on the cluster, driven by `.anthropic-claude-5-sonnet-chat_completion` hosted on Elastic. `agent_builder.plan` reads its tool *calls* and discards its results; the queries are re-run through `store`. |
| Elasticsearch itself | n/a | Calls the Jina inference endpoints at index time (`copy_to` → `semantic_text`) and at query time (`semantic` clause, `text_similarity_reranker`). |
| `backend/scripts/*` | Yes | Setup and reindex only. |

## Configuration

`backend/app/config.py`, read from `.env`:

| Variable | Default | Meaning |
|---|---|---|
| `ELASTICSEARCH_URL` | — | Cluster endpoint. Unset → `LocalStore`. |
| `ELASTICSEARCH_API_KEY` | — | API key. Also authenticates the Kibana Agent Builder API. |
| `HEREAFTER_ES_INDEX` | `hereafter-life-events-v2` | Life log. |
| `HEREAFTER_ES_EVIDENCE_INDEX` | `hereafter-evidence-v2` | Evidence base. |
| `HEREAFTER_ES_RUNS_INDEX` | `hereafter-runs` | Simulation output. |
| `HEREAFTER_ES_INFERENCE_ID` | `.jina-embeddings-v5-text-small` | Embedding endpoint behind `semantic_text`. 1024 dimensions, cosine. |
| `HEREAFTER_ES_RERANK_ID` | `.jina-reranker-v3.5` | Cross-encoder. Empty string disables the rerank stage. |
| `HEREAFTER_REUSE_THRESHOLD` | `0.2` | Rerank score above which stored research is reused instead of re-crawled. |
| `HEREAFTER_STATE_PLANNER` | `llm` | `elastic` \| `llm` \| `rules`. Who chooses the state-building queries. |
| `HEREAFTER_STATE_PLANNER_TIMEOUT` | `120` | Seconds for the Agent Builder converse call. |

Client: `elasticsearch` 9.x, `request_timeout=60`, `retry_on_timeout`, `max_retries=2`. Bulk
writes use `request_timeout=300`. Indices are created on first start if missing. `GET /health`
reports `"store": "elastic"` when this path is active.

Both inference endpoints are preconfigured on the cluster by the Elastic Inference Service:
hosted by Elastic, no separate API key, no cold start.

Switching embedding model requires a reindex — `semantic_text` fixes its `inference_id` in the
mapping. [`backend/scripts/reindex_semantic.py`](../backend/scripts/reindex_semantic.py) creates
`<index>-v2`, reindexes with a script that strips the semantic fields so `copy_to` regenerates
them, keeps document ids, deletes nothing, and prints the `.env` lines to switch over. Dry run by
default; `--go` to execute.

## Index 1 — `hereafter-life-events-v2`

One document per event. Real events are `branch_id: "main"`; a simulated path's visible events
carry that path's id.

```
id, person_id, source, branch_id, domain, event_type, origin   keyword
date                                                           date
confidence                                                     float
payload                                                        object, enabled: false
text                                                           text, copy_to → text_semantic
text_semantic                                                  semantic_text (jina-embeddings-v5-text-small)
```

### Append-only writes

`append` issues a bulk `create` (`op_type=create`, `raise_on_error=False`, `refresh="wait_for"`).
An id that already exists is rejected and returned to the caller as rejected; the stored document
is unchanged. Event ids are deterministic hashes of their content, so re-offering the same file
is a no-op. There is no update call anywhere in the codebase, and the HTTP API exposes no PUT,
PATCH or DELETE on main.

### Retrieval — `_fuse`, used by `hybrid_search`

Three stages, each falling back to the previous one on failure:

1. `text_similarity_reranker` — `inference_id` = `.jina-reranker-v3.5`, `field: "text"`,
   `rank_window_size = max(4 × size, 20)`.
2. `rrf` retriever, `rank_window_size: 50`, fusing:
   - `standard` — BM25 `match` on `text`
   - `standard` — `semantic` query on `text_semantic`
   
   both with `filter` on `person_id` and `branch_id`.
3. BM25 alone.

Falls back to stage 2 if no rerank endpoint is configured, and to stage 3 if RRF or the
inference endpoint is unavailable. Each fallback is logged.

### Aggregations

| Method | Aggregation | Used for |
|---|---|---|
| `domain_histogram` | `date_histogram` on `date`, `calendar_interval: year`, with a nested `terms` on `event_type`, plus a top-level `terms` | Activity density; the agent's "pace over time" tool |
| `track_record` | `filters` — `goal_kept` vs `goal_kept ∪ goal_dropped` | Personal base rate, used only at n ≥ 5 |
| `counts_by_source` | `terms` on `source` | `/inventory` |
| `origins` | `terms` on `origin` with a `max` sub-aggregation on `date` and a `terms` on `source` | What each upload contributed |

### Deletions

`forget(person_id, origin)` and `erase(person_id)` are `delete_by_query` with `conflicts="proceed"`,
`refresh=True`. `erase` runs across all three indices. These are the only deletions in the system
and require the owner's bearer token.

## Index 2 — `hereafter-evidence-v2`

Researched figures, statistics behind simulated events, and real events used as narrative
callbacks. Written with `_op_type: index` (not `create`) — this is public fact, revisable.

```
id, person_id, branch_id, kind, source_url     keyword     retrieved_at   date
claim, snippet, question                       text, copy_to → claim_semantic
claim_semantic                                 semantic_text (jina-embeddings-v5-text-small)
source_title, used_for                         text
value, unit, figure                            keyword, index: false
```

### `remembered(question)` — recall before crawl

Same three-stage retrieval as the life log, reranked on the `question` field, filtered to
`kind: "researched"` and `exists: question`. Not scoped to a person: researched figures are
public fact and are shared across everyone, so a question answered once is answered for all.

### The reuse gate — `question_match` + `research.py:_best_recall`

Retrieval returns candidates; it does not decide reuse. `question_match` calls
`es.inference.rerank(inference_id=.jina-reranker-v3.5, query=<incoming question>, input=[<stored
questions>])` and returns the scores. The highest-scoring candidate is reused only above
`HEREAFTER_REUSE_THRESHOLD`.

Measured against the live evidence index:

| Incoming question | Jaccard ≥ 0.6 (previous gate) | Rerank score | Outcome |
|---|---|---|---|
| how often do students who sleep badly get sick or exhausted | 0.12 — crawl | +0.24 | reuse 50% |
| sleep deprivation health consequences for college students | 0.14 — crawl | +0.21 | reuse 14.7% |
| how many software developers experience burnout | 0.08 — crawl | +0.35 | reuse 53% |
| do Waterloo CS undergrads actually finish the degree | 0.15 — crawl | +0.30 | reuse 91.3% |
| median one-bedroom rent in San Francisco | 0.00 — crawl | −0.16 | crawl |
| how many university students own a car | 0.15 — crawl | −0.10 | crawl |
| average commute time in Toronto | — crawl | −0.11 | crawl |

7/7 correct; the lexical gate it replaced scored 3/7 and passed only verbatim repeats. The
separation band is 0.31 wide (lowest reuse +0.21, highest non-reuse −0.10).

`question_match` returns `[]` when no reranker is configured or on `LocalStore`, and the caller
falls back to the Jaccard comparison, so the no-credentials mode still runs.

## Index 3 — `hereafter-runs`

Simulation output: 1,000 runs × dated steps × possible events, bulk-indexed in the background as
one keyword-only document per event occurrence. Capped at 40,000 documents per path revision.
No embeddings; this index exists for aggregation.

```
person_id, scenario_id, branch_id, event_key, domain, basis   keyword
revision, run, step                                           integer
at                                                            date
```

Document id is `{branch_id}-{revision}-{run}-{step}-{event_key}`. Superseded revisions remain in
the index and never match, because every query filters on the branch's current revision.

| Aggregation | Parameters | Endpoint |
|---|---|---|
| `significant_terms` on `event_key` | foreground = this path at its current revision; `background_filter` = that path plus all siblings of the same decision; `size: 5`, `min_doc_count: 20` | `GET /compare` → `distinctive` |
| `rare_terms` on `event_key` | `max_doc_count: 100` | `GET /lives?which=rare` |

Both return `None` on `LocalStore` or when the background bulk has not landed, and the caller
falls back to numpy over the in-memory result.

## Agent Builder

[`backend/scripts/agent_builder_setup.py`](../backend/scripts/agent_builder_setup.py) registers
five tools and one agent, idempotently (`--remove` deletes them). The agent holds tool
references, so setup deletes and rebuilds the agent around the tool writes.

| Tool | Type | Query |
|---|---|---|
| `hereafter.latest_in_domain` | esql | `WHERE person_id == ?person_id AND branch_id == "main" AND domain == ?domain \| SORT date DESC \| LIMIT 10` |
| `hereafter.domain_histogram` | esql | `EVAL year = DATE_FORMAT("yyyy", date) \| STATS events = COUNT(*) BY year, event_type` |
| `hereafter.search_life_events` | esql | `METADATA _score \| WHERE person_id == ?person_id AND match(text_semantic, ?query) \| SORT _score DESC \| LIMIT 8` |
| `hereafter.recall_evidence` | esql | `METADATA _score \| WHERE kind == "researched" AND match(claim_semantic, ?query) \| SORT _score DESC \| LIMIT 8` |
| `hereafter.distinctive_events` | esql | `WHERE branch_id == ?branch_id \| STATS lives = COUNT(*) BY event_key \| SORT lives DESC` |

Two implementation notes:

- **All five are ES\|QL, none is `index_search`.** An `index_search` tool accepts only a natural
  language query and applies no filter, so it reads across every person in the index. In the
  first run with one, the agent detected results it could not attribute and began inserting
  `person_id demo` into the query *text* to compensate. `?person_id` as an ES\|QL parameter is a
  filter the agent cannot omit.
- **`SORT` precedes `KEEP`.** `KEEP` drops `_score`, and sorting on it afterwards fails with
  `Unknown column [_score]`.

### The planner

`HEREAFTER_STATE_PLANNER=elastic` routes `state.py`'s query planning to the agent.
`agent_builder.plan` POSTs to `/api/agent_builder/converse`, then walks `steps`:

- `type: "reasoning"` steps carry `tool_call_group_id` and the model's reasoning for that round.
- `type: "tool_call"` steps carry `tool_id`, `params`, and the same group id.

Tool calls are mapped through `TOOL_TO_STORE` to store methods and keyword arguments
(`person_id` is dropped — `store` takes it separately; `query`/`nlQuery` become `text`). Tools
with no store equivalent are logged and skipped. The reasoning from each group is attached to
that group's queries, so `AgentStep.reason` on `GET /trunk` carries the agent's own explanation
and `AgentStep.planner` reads `elastic`.

**The agent's own tool results are discarded.** Only its choices are used; the queries are
re-executed through `store` so `state.reduce_events` receives typed `LifeEvent` objects. Any
failure — unreachable cluster, no tool calls, malformed response — returns `None` and the caller
falls through to the `llm` planner, then the `rules` planner.

Measured on the demo log:

| Planner | Wall time | LLM calls | Result |
|---|---|---|---|
| `elastic` | 42 s | 4 | identical state vector |
| `llm` | 9 s | — | identical state vector |

Default is `llm`; `/trunk` is on first load. An earlier version of the agent took 80 s and 21 LLM
calls, most of it the `index_search` tool generating its own queries and the agent re-searching
slots that were legitimately empty.

### MCP

The same five tools are served over `/api/agent_builder/mcp` (41 tools total on the endpoint,
including Elastic's built-ins):

```bash
KB=${ELASTICSEARCH_URL/.es./.kb.}
curl -s -X POST -H "Authorization: ApiKey $ELASTICSEARCH_API_KEY" -H "kbn-xsrf: true" \
  -H "Accept: application/json, text/event-stream" "$KB/api/agent_builder/mcp" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

## Current state of the cluster

```
hereafter-life-events-v2      634 docs
hereafter-evidence-v2         136 docs
hereafter-runs            444,037 docs
```

Verified against the live cluster:

- A bulk `create` against an existing event id is rejected; the stored document is unchanged.
- `"relocated to a new town for school"` returns `"moved from Mississauga to Waterloo for
  university"` (1.212) then `"began a computer science degree at Waterloo"` (0.946) — no terms in
  common with the query.
- The reuse gate scores 7/7 on the table above.
- `significant_terms` returns distinctive event keys for the demo paths.
- The Agent Builder planner produces the same state vector as the `llm` planner.

Scope note: the demo person has 9 events on `branch_id: "main"`. Rerank quality on the life log
is not meaningfully measurable at that size; the measured gain is on the evidence index.

## Limits

- Event `text` cannot be encrypted at rest, because retrieval reads it. The index is
  pseudonymous: random person ids, no names or emails.
- `payload` is `enabled: false` — stored, not indexed. Anything needing a filter is a top-level
  keyword field.
- Evidence contributed by a person is removed when that person erases themselves, including from
  the shared pool.
- The 40,000-document cap per path revision means very long paths are sampled, not exhaustive,
  for the two `hereafter-runs` aggregations.

## Reproduce

```bash
cd backend
.venv/bin/python -m scripts.reindex_semantic              # dry run; --go to execute
.venv/bin/python -m scripts.agent_builder_setup           # register tools + agent; --remove to delete
.venv/bin/python -m pytest -q                             # 104 tests, LLM off, LocalStore

# the agent's logged query choices and the reconciliation rulings
curl -s -H "Authorization: Bearer $TOKEN" "http://127.0.0.1:8642/trunk?person_id=$PERSON_ID" \
  | jq '.agent_log, .reconciliation'
```
