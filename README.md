<p align="center">
  <img src="hero.png" alt="Hereafter — version control for your future" width="800" />
</p>

# Hereafter

Version control for your life. The past is an immutable trunk of light; the present moves forward
on its own; from "now" you walk down statistically simulated futures before choosing one in real
life. Paths you don't take fade. Paths you wait too long on expire.

## Inspiration

Shoutout to **BitLife**, **Git version control**, and **Everything Everywhere All At Once**.

In life, especially as young adults, we have many decisions big and small that we reflect on every
day — whether that's choosing higher education and career paths, to even the smallest social
dilemmas. Or your meal plan that day, or whether you should study or go to a hackathon.

The irony of version controlling our futures is that we can't roll back from the present moment in
real life. So we make do with the FUTURE. We can LIVE THE MULTIVERSE — backed by probability,
published statistics, and evidence read live off the web and quoted — to help us make our decisions
and reflect on our journeys. 

Branch/switch new realities, commit to experience possible events, merge to meet back at reality once your decision has been made irl.  

## What it does

1. **Builds a life out of unstructured input** — social links, chatbot exports, documents, and any
   other context you want to give it. One pipeline, one schema, out the other side as dated sourced
   events.
2. **Tells you who it thinks you are, and lets you argue.** Every line comes with where it came from
   and how sure it is; where sources disagreed it says which one it believed and why, and you can
   correct it.
3. **The user inputs a decision they are trying to make**, with 2–4 choices / possible realities.
   The choices are always theirs.
4. **Researches each reality live** through a cloud browser, quoting and verifying every figure.
5. **Simulates a thousand lives per reality** and draws the most typical one, solidity = cross-run
   agreement. Faint means genuinely uncertain.
6. **Lets you walk the futures** — commit a further what-if, revert it, branch again, compare paths.
   Nothing touches `main` until you merge.
7. **Asks a few clarifying questions**, each chosen by arithmetic because its answer would most change
   what you should do.

## The decision agent (terminal)

Give it a person's context (LinkedIn, Socials, chat history) and a decision, and it asks at
most three questions, each chosen by arithmetic because its answer would most change what to do, then
saves everything it learned. Try it: `cd backend && .venv/bin/python -m app.agent --person <person_id> -q "Berlin startup or stay at Acme?"`.
Full guide in [docs/AGENT.md](docs/AGENT.md).

## Run it

```bash
# backend — http://127.0.0.1:8642
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --port 8642

# frontend
cd frontend
npm install && npm run dev     # http://localhost:5642
```

The app starts empty: no seeded person, no sample decisions. You tell it about yourself on first run.
With no `.env` at all this runs on the local event store with the LLM off. Copy `.env.example` to `.env` to
switch on Elastic, Browserbase and the LLM.

**The "not a wrapper" proof:** `HEREAFTER_LLM=off`. Every future is still simulated, every path
still has solidity, expiry, merge and carry still work; events simply render as their raw
structured `text`. `backend/tests` runs entirely in this mode.

```bash
cd backend && .venv/bin/python -m pytest -q
```

## The demo (no backend, no keys)

`http://localhost:5642/?demo` (after `npm run dev` in `frontend/`) plays a scripted walkthrough that never touches the network or a real person's data:

1. Pick GitHub, LinkedIn and Instagram, then **Continue**: a short "Connecting your accounts" screen, then the main page with "What I learned about you".
2. Press **N**, then **Enter**: the composer types *"I like this girl at hackathon. What should I do?"* and its three options; **Enter** again branches.
3. The paths grow and **The numbers** opens: the chance she is interested (a Bayesian update: a starting point times one likelihood ratio per fact), a payoff for each choice in each possible world, and the **expected value** of each with its spread. Two questions ("has she made eye contact?", "is she with someone?") update the odds live, ending in a recommendation that can flip to "don't approach".

`?demo&preload` opens with the question already asked. The maths is real and tested (`npm run test:decision`); the profile and the loading animation are scripted sample data.
Every figure is tagged **published** (with the source and the sentence it was read in) or **assumption** (a demo input: the starting probability, the likelihood ratios, the payoffs). It is an illustrative model, not dating advice.

## How each piece of the stack is used

**Elastic** — the context layer, and the thing that decides whether work happens. Elastic Cloud
Serverless 9.6: three indices, two Elastic Inference Service endpoints, one Agent Builder agent with
five ES|QL tools. Hybrid retrieval is a `text_similarity_reranker` (Jina v3.5) over an `rrf`
retriever fusing BM25 with a `semantic` query on a `semantic_text` field (Jina embeddings v5,
1024-dim) — three stages, each degrading into the previous one and logging it. Append-only is
enforced in the mapping (`op_type=create`), not the application. The reranker is also used as a
*decision function*: `es.inference.rerank` scores an incoming research question against stored ones
and a score above `0.2` is the difference between reusing evidence and firing a crawl (7/7 correct
against 3/7 for the lexical gate it replaced). And every one of the 1,000 runs per branch is indexed
(444,037 docs), so "what is distinctive about this life" is a `significant_terms` aggregation
against sibling branches rather than a numpy loop. And a scheduled **Workflow** (`hereafter-evidence-audit`,
every 24h plus manual) keeps the memory honest: the reuse gate judges *meaning* and has no sense of time,
so the workflow marks researched evidence older than `HEREAFTER_EVIDENCE_MAX_AGE_DAYS` as `stale`, clears
the flag on anything fresh, and writes an audit doc. `remembered()` filters stale evidence out of recall,
so an aged-out figure is re-researched instead of reused — a job on the cluster deciding whether the app
goes to the network. It writes only to the evidence and audit indices, and a test asserts that against the
rendered YAML. Full detail: [docs/ELASTICSEARCH.md](docs/ELASTICSEARCH.md).

**Browserbase** — how the system reads the world. Two jobs: the cold-start crawl of the person's own
public footprint, and field research on every option at the moment you branch. Every page is graded
substantial / thin / breadcrumb and **no tier is an error**. Stagehand handles the one page Playwright
cannot — a signed-in LinkedIn work history — and has no side door: its output goes through the same
extraction, cache and consent gate as any other page. Full detail: [docs/BROWSERBASE.md](docs/BROWSERBASE.md),
[docs/STAGEHAND.md](docs/STAGEHAND.md).

**OpenAI** — all the hard reading. It turns uploads into dated structured events, proposes what could
happen on each path and names the reference class worth researching, picks which Elastic queries to
run, judges every possible event against the person's record, writes the agent's questions, and
narrates a branch into chapters. Every call carries a Pydantic schema and parses into a typed object;
there is no free-text parsing anywhere. What it never does is decide a number: `llm.py` has no store
import, no client and no credentials, and the judge's output schema has no probability field, so it
structurally cannot say how likely something is. `HEREAFTER_LLM=off` is therefore a reproducibility
guarantee rather than a feature — a decision already built re-runs identically forever — not a claim
that the product works without it.

**The agent** — `backend/app/agent/`. A calculation picks the question (expected value of perfect
information over the unknowns); the model only words it, and code checks the wording. Full detail:
[docs/AGENT.md](docs/AGENT.md).

## How it is put together

| | |
|---|---|
| `data/*.csv` | Eleven transition tables reduced from Statistics Canada downloads. `data/SOURCES.md` cites each one, states every transformation, and lists the engine's hand-set constants; `data/build/` rebuilds them (`fetch → build → check`). **Feeds the life-course background only, which is off by default** — see `sim/engine.py` below. Nothing on a short decision reads them. |
| `backend/app/sim/outcomes.py` | The generic sampler for any decision of any size: an option's outcome model (possible events over dated steps, each `sourced`, `personal` or `estimated`) lived forward a thousand times. No LLM import; a stored model re-runs identically. |
| `backend/app/scenarios.py`, `outcome_model.py`, `research.py` | A scenario and its options become branches: the LLM proposes what could happen and the nearest researchable reference class, Browserbase finds and reads a published rate, code verifies the figure is literally in its own snippet and converts it, clarifying questions (at most three, never blocking) are asked only after main has been searched. |
| `backend/app/jev.py`, `probability.py` | Jev reads each proposed event against the person's own log (Elastic) and returns a category, 1–5 scores (personal fit, experience fit, difficulty, accessibility, evidence strength) and yes/no/unknown checks on hard prerequisites. It never gives a probability. `probability.py` is plain code: it takes the event's base rate (published, personal or a verbal bin), moves it by a bounded amount using Jev's category-weighted scores, caps it if a hard prerequisite is unmet, and returns likelihood, range, difficulty, confidence and the evidence behind them. The simulator runs on that likelihood. `GET /assessment?branch_id=` shows it. |
| `backend/app/chapters.py`, `evidence.py` | A branch read as chapters with margin notes, and what those notes point to. |
| `backend/app/security.py` | Bearer token per person (hashed), Fernet encryption at rest for the person record, page cache and chapter prose; `/inventory` and `/erase`. |
| `backend/app/sim/engine.py` | The Monte Carlo engine. Pure numpy. 1,000 runs per branch, seeded from the fork state and the assumption, so the same question always gets the same futures. The visible path is the medoid run; per-year solidity is cross-run agreement with it. It also holds the life-course background (weather, not plot) over the StatCan tables — **opt-in and off by default** (`HEREAFTER_BACKGROUND=on`), and even then only under horizons of a year or more, with life-script events opt-in and a capped share. It is off because people found it noise: a peer's wedding has no business appearing inside a month you asked about not drinking. |
| `backend/app/store.py` | Life events in Elasticsearch: `create`-only writes (the past cannot be edited — there is no update or delete anywhere), hybrid BM25 + dense retrieval through an RRF retriever over a `semantic_text` field (Jina v5 embeddings) finished by a Jina cross-encoder rerank, date-histogram + terms aggregations. A SQLite stand-in with the same surface runs when Elastic isn't configured. |
| `backend/app/workflows.py` | The evidence audit: a scheduled Elastic Workflow that marks researched figures stale once they age out, so `remembered()` stops reusing them and the next path that needs one looks it up again. `GET /evidence/health`, `POST /evidence/audit`. |
| `backend/app/state.py`, `agent_builder.py` | The retrieval agent. It chooses which store queries to run to fill the present-day state vector, logs each choice, then reconciles conflicting sources by recency and confidence and logs each ruling. Both logs come back on `GET /trunk`. The planner is Elastic's own Agent Builder agent, the planner in `llm.py`, or a rules planner with no model at all — `HEREAFTER_STATE_PLANNER` picks, and the log names whichever ran. |
| `backend/app/ingest/` | The Offering. `router` labels each input, every label goes through the same `_extract` call, `links` is the per-link Browserbase pipeline (substantial / thin / breadcrumb), `chat` measures chat exports and discards them. Nothing here returns an error to the user. |
| `backend/app/llm.py` | The only three things the LLM may do: extract, pick retrieval queries, narrate a log the simulator already decided. Provider follows the key in `.env`: OpenAI (`OPENAI_API_KEY`, default `gpt-5.5`) or Anthropic (`ANTHROPIC_API_KEY`, default `claude-opus-5`); override with `HEREAFTER_LLM_MODEL`. |
| `frontend/` | One React Three Fiber scene and a thin text overlay. All design tokens live in `src/theme.ts`. |
| `docs/API.md` | The contract between the two. |
| `docs/ELASTICSEARCH.md` | Every index, mapping, retriever and aggregation, who issues which query, and the Agent Builder tools. |
| `docs/BROWSERBASE.md` | Both crawl jobs, the readability tiers, and the research pipeline. |
| `docs/STAGEHAND.md` | What Stagehand does here: reads a signed-in LinkedIn profile (Show all, then structured jobs and schools), how a signed-in context is made, and why the rest stays on Playwright. |

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

## Challenges, and what we learned

**Nothing specific enough to matter has a statistic.** No study exists about *your* ex or *your*
first year in a new city. So for each possible event the system names the nearest **reference class**
that does get studied and researches that instead. Where the fit is loose it widens the sampling band
rather than adjusting the number — adjusting a published figure toward a person is exactly the
invisible fudge this project exists to avoid.

**We built a demographic simulator, measured it, and switched it off.** The eleven StatCan tables
work and are properly cited, and they answer almost none of the questions people actually bring.
Nobody deciding whether to text someone back is helped by the national annual probability of moving
province. That failure is the direct reason the reference-class research pipeline exists.

**The Agent Builder agent leaked across people before we constrained its tools.** An `index_search`
tool accepts only a query string and applies no filter, so it read across every person in the index —
and the agent, noticing results it could not attribute, started writing `person_id demo` into the
*query text* to compensate. Invisible in the outputs, obvious in the tool-call parameters. All five
tools are now ES|QL with `?person_id` as a bound parameter the agent cannot omit. Read agent traces,
not agent answers.

**A system is trustworthy in proportion to what its model is structurally unable to do.** Every
constraint here started as a sentence in a prompt and ended as a line of code: the simulator has no
`llm` import, the judge's schema has no probability field, the planner returns an enum of three
tools, the question cap is a loop bound.

**Degrade, don't fail.** Name the partial outcomes and give each one a behaviour. A login-walled
LinkedIn is a breadcrumb. A missing reranker is plain RRF. A dead cluster is SQLite. A dead model is
raw structured text.
