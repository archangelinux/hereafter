"""Environment-driven settings. Everything optional: with nothing set, Hereafter runs on the
local store with the LLM off, which is also the "not a wrapper" demo mode."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DATA_DIR = Path(os.getenv("HEREAFTER_DATA_DIR", ROOT / "data"))
CACHE_DIR = Path(os.getenv("HEREAFTER_CACHE_DIR", ROOT / "backend" / "cache"))
SQLITE_PATH = Path(os.getenv("HEREAFTER_SQLITE", ROOT / "backend" / "hereafter.db"))

# HEREAFTER_LLM=off disables every LLM call; events render as raw structured data.
LLM_ENABLED = os.getenv("HEREAFTER_LLM", "on").lower() not in ("off", "0", "false", "no")
# Provider follows whichever key is present (OpenAI wins if both are), unless set explicitly.
LLM_PROVIDER = os.getenv("HEREAFTER_LLM_PROVIDER") or ("openai" if os.getenv("OPENAI_API_KEY") else "anthropic")
LLM_MODEL = os.getenv("HEREAFTER_LLM_MODEL") or {"openai": "gpt-5.5", "anthropic": "claude-opus-5"}[LLM_PROVIDER]
# Proposing what could happen is the slowest call. It may use another model and a lower reasoning effort.
# Measured 2026-09-19: gpt-5.5 default effort ~50 s, effort low ~24-37 s with quality intact; gpt-5.4-mini
# ~8-14 s but it stops sharing outcome keys across options, which breaks compare. So: same model, low effort.
LLM_FAST_MODEL = os.getenv("HEREAFTER_LLM_FAST_MODEL") or {"openai": "gpt-5.5", "anthropic": "claude-opus-5"}[LLM_PROVIDER]
# Reading a one-line decision into situation + options must feel instant: the smallest model.
LLM_TICKET_MODEL = os.getenv("HEREAFTER_LLM_TICKET_MODEL") or {"openai": "gpt-5.4-mini", "anthropic": "claude-haiku-4-5"}[LLM_PROVIDER]
LLM_FAST_EFFORT = os.getenv("HEREAFTER_LLM_FAST_EFFORT", "low")  # OpenAI reasoning effort for that call; empty = provider default

ES_URL = os.getenv("ELASTICSEARCH_URL", "")
ES_API_KEY = os.getenv("ELASTICSEARCH_API_KEY", "")
ES_INDEX = os.getenv("HEREAFTER_ES_INDEX", "hereafter-life-events")
ES_EVIDENCE_INDEX = os.getenv("HEREAFTER_ES_EVIDENCE_INDEX", "hereafter-evidence")
ES_RUNS_INDEX = os.getenv("HEREAFTER_ES_RUNS_INDEX", "hereafter-runs")
# Preconfigured inference endpoints on Elastic Cloud (the Elastic Inference Service: hosted, no
# extra key, always warm). Embeddings back the semantic_text fields; the reranker is a Jina
# cross-encoder run over the fused result window. Set the rerank id empty to drop that stage.
ES_INFERENCE_ID = os.getenv("HEREAFTER_ES_INFERENCE_ID", ".jina-embeddings-v5-text-small")
ES_RERANK_ID = os.getenv("HEREAFTER_ES_RERANK_ID", ".jina-reranker-v3.5")
# Who chooses the store queries behind "who you are now" (backend/app/state.py):
#   elastic = the Agent Builder agent on the cluster; llm = the planner in llm.py;
#   rules = no model at all. Measured on the demo log: elastic ~42 s and 4 LLM calls,
#   llm ~9 s. The agent log on GET /trunk names whichever ran.
STATE_PLANNER = os.getenv("HEREAFTER_STATE_PLANNER", "llm").lower()
STATE_PLANNER_TIMEOUT = int(os.getenv("HEREAFTER_STATE_PLANNER_TIMEOUT", "120"))

BROWSERBASE_API_KEY = os.getenv("BROWSERBASE_API_KEY", "")
BROWSERBASE_PROJECT_ID = os.getenv("BROWSERBASE_PROJECT_ID", "")
# A Browserbase context that is already signed in to LinkedIn. When it is set and still signed in,
# Stagehand reads LinkedIn profiles on it (docs/STAGEHAND.md); otherwise LinkedIn is read as before.
LINKEDIN_CONTEXT = os.getenv("HEREAFTER_LINKEDIN_CONTEXT", "")
# "provider/model", the form Stagehand takes; it makes a model call for every act and extract. OpenAI, with OPENAI_API_KEY.
STAGEHAND_MODEL = os.getenv("HEREAFTER_STAGEHAND_MODEL") or "openai/gpt-5.4-mini"

# The life-table background (friends' weddings and children, parents, money drift) is off unless asked for.
BACKGROUND = os.getenv("HEREAFTER_BACKGROUND", "off").lower() in ("on", "1", "true", "yes")
SIM_RUNS = int(os.getenv("HEREAFTER_SIM_RUNS", "1000"))
SIM_HORIZON_YEARS = int(os.getenv("HEREAFTER_SIM_HORIZON", "40"))

FRONTEND_ORIGINS = os.getenv("HEREAFTER_FRONTEND_ORIGINS", "http://localhost:5642,http://127.0.0.1:5642").split(",")
RESEARCH_ENABLED = os.getenv("HEREAFTER_RESEARCH", "on").lower() not in ("off", "0", "false", "no")
RESEARCH_BUDGET_SECONDS = int(os.getenv("HEREAFTER_RESEARCH_BUDGET", "75"))
# Reranker score above which already-researched evidence answers a new question and is reused
# instead of crawled again. Measured on the demo evidence base: genuine rephrasings score
# +0.21 to +0.71, unrelated questions that share vocabulary score -0.10 to -0.16.
REUSE_THRESHOLD = float(os.getenv("HEREAFTER_REUSE_THRESHOLD", "0.2"))
# A published figure is a fact about a moment. Past this age the evidence audit workflow
# marks it stale, `remembered()` stops offering it, and it is researched again on next use.
EVIDENCE_MAX_AGE_DAYS = int(os.getenv("HEREAFTER_EVIDENCE_MAX_AGE_DAYS", "180"))
