# Hereafter

Version control for your life. The past is an immutable trunk of light; the present moves forward
on its own; from "now" you walk down statistically simulated futures before choosing one in real
life. Paths you don't take fade. Paths you wait too long on expire.

## Run it

```bash
# backend — http://127.0.0.1:8642
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --port 8642

# frontend
cd frontend
npm install && npm run dev     # http://localhost:5642/?person=demo
```

With no `.env` at all this runs: local event store, LLM off, a seeded `demo` person with two open
paths. Copy `.env.example` to `.env` to switch on Elastic, Browserbase and the LLM.

**The "not a wrapper" proof:** `HEREAFTER_LLM=off`. Every future is still simulated, every path
still has solidity, expiry, merge and carry still work; events simply render as their raw
structured `text`. `backend/tests` runs entirely in this mode.

```bash
cd backend && .venv/bin/python -m pytest -q
```

## How it is put together

| | |
|---|---|
| `data/*.csv` | Transition tables reduced from Statistics Canada downloads. `data/SOURCES.md` cites each one, states every transformation, and lists the engine's hand-set constants. `data/build/` rebuilds them. |
| `backend/app/sim/outcomes.py` | The generic sampler for any decision of any size: an option's outcome model (possible events over dated steps, each `sourced`, `personal` or `estimated`) lived forward a thousand times. No LLM import; a stored model re-runs identically. |
| `backend/app/scenarios.py`, `outcome_model.py`, `research.py` | A scenario and its options become branches: the LLM proposes what could happen and the nearest researchable reference class, Browserbase finds and reads a published rate, code verifies the figure is literally in its own snippet and converts it, clarifying questions (at most three, never blocking) are asked only after main has been searched. |
| `backend/app/jev.py`, `probability.py` | Jev reads each proposed event against the person's own log (Elastic) and returns a category, 1–5 scores (personal fit, experience fit, difficulty, accessibility, evidence strength) and yes/no/unknown checks on hard prerequisites. It never gives a probability. `probability.py` is plain code: it takes the event's base rate (published, personal or a verbal bin), moves it by a bounded amount using Jev's category-weighted scores, caps it if a hard prerequisite is unmet, and returns likelihood, range, difficulty, confidence and the evidence behind them. The simulator runs on that likelihood. `GET /assessment?branch_id=` shows it. |
| `backend/app/chapters.py`, `evidence.py` | A branch read as chapters with margin notes, and what those notes point to. |
| `backend/app/security.py` | Bearer token per person (hashed), Fernet encryption at rest for the person record, page cache and chapter prose; `/inventory` and `/erase`. |
| `backend/app/sim/engine.py` | The life-course background (weather, not plot): year horizons only, life-script events opt-in, capped share. The Monte Carlo engine. Pure numpy. 1,000 runs per branch, seeded from the fork state and the assumption, so the same question always gets the same futures. The visible path is the medoid run; per-year solidity is cross-run agreement with it. |
| `backend/app/store.py` | Life events in Elasticsearch: `create`-only writes (the past cannot be edited — there is no update or delete anywhere), hybrid BM25 + dense retrieval through an RRF retriever over a `semantic_text` field (Jina v5 embeddings) finished by a Jina cross-encoder rerank, date-histogram + terms aggregations. A SQLite stand-in with the same surface runs when Elastic isn't configured. |
| `backend/app/state.py`, `agent_builder.py` | The retrieval agent. It chooses which store queries to run to fill the present-day state vector, logs each choice, then reconciles conflicting sources by recency and confidence and logs each ruling. Both logs come back on `GET /trunk`. The planner is Elastic's own Agent Builder agent, the planner in `llm.py`, or a rules planner with no model at all — `HEREAFTER_STATE_PLANNER` picks, and the log names whichever ran. |
| `backend/app/ingest/` | The Offering. `router` labels each input, every label goes through the same `_extract` call, `links` is the per-link Browserbase pipeline (substantial / thin / breadcrumb), `chat` measures chat exports and discards them. Nothing here returns an error to the user. |
| `backend/app/llm.py` | The only three things the LLM may do: extract, pick retrieval queries, narrate a log the simulator already decided. Provider follows the key in `.env`: OpenAI (`OPENAI_API_KEY`, default `gpt-5.5`) or Anthropic (`ANTHROPIC_API_KEY`, default `claude-opus-5`); override with `HEREAFTER_LLM_MODEL`. |
| `frontend/` | One React Three Fiber scene and a thin text overlay. All design tokens live in `src/theme.ts`. |
| `docs/API.md` | The contract between the two. |
| `docs/ELASTICSEARCH.md` | Every index, mapping, retriever and aggregation, who issues which query, and the Agent Builder tools. |
| `docs/BROWSERBASE.md` | Both crawl jobs, the readability tiers, and the research pipeline. |

## Rules the code enforces

- **The past is append-only.** The store exposes `append` and queries. Elasticsearch writes use
  `op_type=create`; an existing id is never overwritten. The API has no PUT, PATCH or DELETE.
- **Now is the server clock.** No route accepts a date for "now".
- **The LLM never decides a future.** The simulator never imports `llm`. Narration receives a
  finished event log and may not add, remove or move events.
- **Consent.** The crawler loads only URLs built from rows in `handles` where the submitter is the
  person being crawled, and follows no links.
- **Chat exports are not kept.** Parsed in memory, reduced to a connectedness signal and
  structured events about the owner only, then dropped.
