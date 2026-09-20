<p align="center">
  <img src="hero.png" alt="Hereafter: version control for your future" width="800" />
</p>

# Hereafter

Append-only life log plus git-style branching over simulated futures. You pick 2-4 options; the
system researches published rates, scores them against your record in code, and Monte Carlo
samples 1,000 lives per branch. Nothing writes to `main` until you merge.

LLM never assigns a probability. Simulator never imports `llm`. Store has no update or delete.

## Pipeline

1. Ingest (links, docs, chat exports) → dated sourced events.
2. Reconstruct present state: hybrid retrieval, then reconcile conflicts by recency and confidence.
3. Branch on a decision. LLM proposes events and a researchable reference class; Browserbase
   quotes a published rate; code verifies the figure is in the snippet.
4. Jev scores each event against the log (category, 1-5 fits, hard prerequisites). `probability.py`
   turns that plus the base rate into a bounded likelihood. Jev has no probability field.
5. 1,000 seeded numpy runs per branch. Visible path is the medoid; solidity is cross-run
   agreement. Faint = genuinely uncertain.
6. At most three clarifying questions, chosen by EVPI. Commit / revert / compare; merge is explicit.

## Stack

| | |
|---|---|
| Elastic Cloud Serverless 9.6 | Append-only (`op_type=create`). Hybrid BM25 + Jina v5 `semantic_text` (1024-d) fused by RRF, then Jina v3.5 rerank. Rerank > `0.2` reuses stored evidence instead of crawling. Agent Builder: five ES\|QL tools, `?person_id` bound. Workflow `hereafter-evidence-audit` (24h) flags evidence older than `HEREAFTER_EVIDENCE_MAX_AGE_DAYS` stale. Indexed sim runs (`significant_terms` vs sibling branches). SQLite stand-in if unset. [docs/ELASTICSEARCH.md](docs/ELASTICSEARCH.md) |
| Browserbase | Public-footprint crawl and per-option research. Pages graded substantial / thin / breadcrumb; no tier is an error. Stagehand reads signed-in LinkedIn only; same extract/cache/consent path. [docs/BROWSERBASE.md](docs/BROWSERBASE.md), [docs/STAGEHAND.md](docs/STAGEHAND.md) |
| LLM (OpenAI `gpt-5.5`) | Extract, plan retrieval queries, propose events + reference class, word agent questions, narrate a finished log. Every call is a Pydantic schema. `llm.py` has no store, client, or credentials. `HEREAFTER_LLM=off`: sim, solidity, expiry, merge still run; events render as structured `text`. |
| Agent | `backend/app/agent/`. EVPI picks the question; the model only words it. [docs/AGENT.md](docs/AGENT.md) |

Degrade, don't fail: missing reranker → RRF; dead cluster → SQLite; dead model → raw structured text; login-walled LinkedIn → breadcrumb.

## Run

```bash
# backend  http://127.0.0.1:8642
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --port 8642

# frontend  http://localhost:5642  (proxies /api → :8642)
cd frontend
npm install && npm run dev
```

No seed data. Empty `.env` = SQLite + LLM off. Copy `.env.example` for Elastic, Browserbase, LLM.

```bash
cd backend && .venv/bin/python -m pytest -q
cd backend && .venv/bin/python -m app.agent --person <person_id> -q "Berlin startup or stay at Acme?"
```

## Invariants

- Past is append-only. Store is `append` + query. ES writes `op_type=create`. API has no PUT, PATCH, or DELETE.
- `now` is the server clock. No route accepts a date for it.
- Simulator never imports `llm`. Narration may not add, remove, or move events.
- Crawler loads only URLs from `handles` submitted by the person being crawled. No link following.
- Chat exports are not stored. Parsed in memory, reduced to owner events + a connectedness signal, dropped.
