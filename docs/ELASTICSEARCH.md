# Elasticsearch in Hereafter — technical README

Hereafter uses Elastic Cloud (serverless, Elasticsearch 9.6) as three things at once: the
immutable **life log**, the **evidence base** that research accumulates into, and the
**multiverse** — every simulated life — so that "what is distinctive about this path" and "what
is rare here" are aggregations rather than application code.

All Elasticsearch code is in one file: [`backend/app/store.py`](../backend/app/store.py),
class `ElasticStore`. A `LocalStore` (SQLite) with the same method surface is used when
`ELASTICSEARCH_URL` is unset, which is how the test suite and the "no credentials" mode run.

## Configuration

`backend/app/config.py`, read from `.env`:

| Variable | Default | Meaning |
|---|---|---|
| `ELASTICSEARCH_URL` | — | Elastic Cloud endpoint. Unset → `LocalStore`. |
| `ELASTICSEARCH_API_KEY` | — | API key. |
| `HEREAFTER_ES_INDEX` | `hereafter-life-events` | Life log. |
| `HEREAFTER_ES_EVIDENCE_INDEX` | `hereafter-evidence` | Evidence base. |
| `HEREAFTER_ES_RUNS_INDEX` | `hereafter-runs` | Simulated lives. |
| `HEREAFTER_ES_INFERENCE_ID` | `.multilingual-e5-small-elasticsearch` | Preconfigured dense-embedding inference endpoint behind the `semantic_text` fields. |

Client: `elasticsearch` Python client 9.x, `request_timeout=60`, `retry_on_timeout`, two retries.
Bulk writes use a 300 s timeout because the first write after a quiet spell waits for the
embedding model to wake. Indices are created on first start if missing; `GET /health` reports
`"store": "elastic"` when this path is active.

## Index 1 — `hereafter-life-events`: the life log

One document per event, for real events (`branch_id: "main"`) and for the visible events of
simulated paths (`branch_id: <branch id>`).

```
id, person_id, source, branch_id, domain, event_type, origin   keyword
date                                                            date
confidence                                                      float
payload                                                         object, enabled: false (stored, not indexed)
text                                                            text, copy_to → text_semantic
text_semantic                                                   semantic_text (inference_id = e5-small)
```

| What | How | Where |
|---|---|---|
| **The past cannot be edited** | Every write is a bulk `create` (`op_type=create`, `raise_on_error=False`): an id that already exists is left exactly as it was and reported back as rejected. There is no update anywhere in the code. Event ids are deterministic hashes, so offering the same file twice never duplicates. | `append` |
| **Hybrid retrieval** | An `rrf` retriever fusing two `standard` retrievers — BM25 `match` on `text`, and a `semantic` query on `text_semantic` — both filtered by `person_id` and `branch_id`. If the inference endpoint or RRF is unavailable it falls back to BM25 and logs it. | `hybrid_search` |
| **Agentic state building** | To work out "who you are now", an agent *chooses* which of three tools to run — `latest_in_domain` (filtered, sorted by date), `domain_histogram` (`date_histogram` by year with a nested `terms` on `event_type`, plus a top-level `terms`), `hybrid_search` — plans again from what is still unknown, and logs every choice (`AgentStep`). The planner is the LLM when it is on, a rules planner otherwise; what the retrieved events *mean* is plain code, as is reconciling conflicting sources by recency × confidence. Returned on `GET /trunk` as `agent_log` and `reconciliation`. | `backend/app/state.py` |
| **Context for decisions and narration** | When a decision is created, hybrid search pulls the real events most relevant to the situation (so nothing already known is asked again); each chapter pulls a few real events for callbacks. | `scenarios.py`, `chapters.py` |
| **The person's own track record** | One `filters` aggregation over main (`goal_kept` vs `goal_kept`+`goal_dropped`), used as a personal base rate only when there are at least five. | `track_record` |
| **Inventory / forget / erase** | `terms` on `source`; `terms` on `origin` with a `max` date sub-aggregation (what each upload contributed); `delete_by_query` by `origin` (forget one upload) or by `person_id` across all three indices (erase). These are the only deletions in the system and only the owner's token can trigger them. | `counts_by_source`, `origins`, `forget`, `erase` |

## Index 2 — `hereafter-evidence`: the evidence base

Every researched fact (from Browserbase, see `docs/BROWSERBASE.md`), every statistic behind a
simulated event, and every real event used as a narrative callback.

```
id, person_id, branch_id, kind, source_url     keyword        retrieved_at   date
claim, snippet, question                       text, copy_to → claim_semantic
claim_semantic                                 semantic_text
source_title, used_for                         text
value, unit, figure                            keyword, index: false
```

- **Reuse before crawl.** Before anything is searched on the web, `remembered(question)` runs an
  RRF hybrid query (BM25 on `question` + `semantic` on `claim_semantic`, filtered to
  `kind: researched`) across *everyone's* earlier research — it is public fact, not personal
  data — and a sufficiently similar question reuses the stored figure, quote and URL. The UI's
  research feed shows this as "Found in memory". Research therefore accumulates across decisions.
- **Retrieval for narration and the evidence drawer.** `search_evidence` is the same hybrid
  query scoped to one person and path; `evidence` fetches by path or by ids.

## Index 3 — `hereafter-runs`: the simulated lives

After each simulation the sampler's result (1,000 lives × dated steps × possible events) is
bulk-indexed in the background, one small keyword-only document per event occurrence
(`person_id, scenario_id, branch_id, revision, run, step, at, event_key, domain, basis`), capped
at 40,000 documents per path revision. No embeddings here — this index is for aggregation.

| Question | Aggregation | Endpoint |
|---|---|---|
| What is **distinctive** about this path compared with its siblings? | `significant_terms` on `event_key`; foreground = this path's current revision, `background_filter` = all paths of the same decision; `min_doc_count: 20`. | `GET /compare` → `distinctive` |
| What is the **rarest** thing that happens here? | `rare_terms` on `event_key` (`max_doc_count: 100`), used to label the rarest coherent life. | `GET /lives?which=rare` |

Both fall back to numpy when the bulk has not landed yet or on the local store. Superseded
revisions stay in the index but never match, because every query filters on the current revision.

## What is live right now

On the project's cluster at the time of writing: `hereafter-life-events` 163 documents,
`hereafter-evidence` 43, `hereafter-runs` 133,100.

Verified against the live cluster: a rewrite of an existing event is rejected; "relocated to a
new town for school" ranks a "moved to Waterloo" event first with no shared words (the dense side
of the hybrid query doing its job); a figure researched for one decision was found in memory and
not crawled again for the next; `significant_terms` returns distinctive events for demo paths.

## Try it

```bash
# who-you-are-now, with the agent's logged query choices
curl -s -H "Authorization: Bearer demo" "http://127.0.0.1:8642/trunk?person_id=demo" | jq '.agent_log, .reconciliation'

# what is distinctive about each path of the demo's first decision (significant_terms)
H='Authorization: Bearer demo'
IDS=$(curl -s -H "$H" "http://127.0.0.1:8642/branches?person_id=demo" | python3 -c "
import json,sys
bs=[b['branch'] for b in json.load(sys.stdin)['branches']]
two=[b for b in bs if b['scenario_id']==bs[0]['scenario_id']][:2]
print('a=%s&b=%s' % (two[0]['id'], two[1]['id']))")
curl -s -H "$H" "http://127.0.0.1:8642/compare?$IDS" | jq '.distinctive'
```

## Limits, stated plainly

- Event `text` in Elastic cannot be end-to-end encrypted, because search has to read it. It is
  kept pseudonymous (random person ids, no names or emails in the index) and minimal.
- `payload` is stored but not indexed; anything that needs filtering is a top-level keyword.
- Evidence a person's research added to the shared index is removed when they erase themselves.
- The 40,000-document cap per path revision means very eventful long paths are sampled, not
  exhaustive, for the two aggregations.
