# Browserbase in Hereafter — technical README

Browserbase is how Hereafter reads the web on a person's behalf. It does two jobs, both of which
need a real browser rather than a plain HTTP fetch:

1. **Cold start** — reading the person's *own* public footprint (their site, profile pages) into
   events on main.
2. **Field research** — at the moment a decision is created, finding and reading real pages about
   each path (published rates for the nearest studied group; pay, rent, program length), quoting
   them, and feeding the figures to the simulator.

Code: [`backend/app/ingest/links.py`](../backend/app/ingest/links.py) (sessions, page reading,
tiers, cache) and [`backend/app/research.py`](../backend/app/research.py) (search, research
orchestration). SDK: `browserbase` 1.x for sessions and search, `playwright` connected to the
session over CDP.

## Configuration

`.env`, read in `backend/app/config.py`:

| Variable | Meaning |
|---|---|
| `BROWSERBASE_API_KEY` | API key. |
| `BROWSERBASE_PROJECT_ID` | The project's **ID** (a UUID — not its name). |
| `HEREAFTER_RESEARCH` | `on` (default) / `off`. |
| `HEREAFTER_RESEARCH_BUDGET` | Seconds of research per path (default 75; multiplied by the number of paths). |

`GET /health` reports `"research": true` when the key, the project and the LLM are all present.
Without Browserbase credentials, link reading falls back to a plain HTTP fetch (development only)
and research is skipped — a path then simply keeps its first simulation.

## How a page is read (both jobs)

```
Browserbase().sessions.create(project_id=…)            # one cloud browser
playwright.chromium.connect_over_cdp(session.connect_url)
tab.goto(url, wait_until="domcontentloaded")
tab.evaluate(READABILITY_JS)                           # runs in the page
```

`READABILITY_JS` takes the main content region (`article`, `main`, `[role=main]`, else `body`),
removes navigation, headers, footers, forms and hidden nodes, and returns the visible text plus
the metadata that survives login walls (`<title>`, `og:title`, `og:description`). Every page is
then graded into one of three tiers, and **no tier is an error**:

| Tier | Condition | What happens |
|---|---|---|
| **substantial** | ≥ 600 characters of content | Goes to the normal extraction call. |
| **thin** | Login wall or block, but a title / bio card / og: tags surfaced | Kept as low-confidence material (confidence capped at 0.35). |
| **nothing** | Nothing surfaced | The URL itself is kept as a "breadcrumb". |

The `hereafter` Browserbase project allows one concurrent session, so every session in the app is
taken under one lock (`links.session_lock`), shared by the crawl and by research.

## Job 1 — cold start (`links.py`, called from `ingest/pipeline.py`)

- **Consent is enforced in code.** The only URLs ever loaded are rows the person submitted about
  themselves (`handles` table, `submitted_by = person_id`), expanded by fixed templates
  (`github.com/<handle>`, `linkedin.com/in/<handle>/`, the site URL…). No link found on a page is
  ever followed.
- One session per handle or link; pages are read through the tiers above; the LLM then extracts
  dated events about that one person (extraction only — it never invents).
- Page text is cached on disk **encrypted** (Fernet, `HEREAFTER_DATA_KEY`) per person, so a demo
  survives bad wifi and a re-read does not re-crawl. `POST /erase` removes the cache.
- Seen live: a personal site read in full (20+ events); a LinkedIn profile blocked → breadcrumb,
  as designed; a public GitHub page read in about seven seconds.

## Job 2 — field research on every path (`research.py`)

Runs as a background task right after `POST /scenarios` (and again for a path added later). The
pipeline, per decision:

1. **Plan** (LLM, choosing what to look up — never the answer). For each possible event that is
   still an *estimate*, the proposal has already named the nearest **reference class** that gets
   studied and a search query ("completion rates in dry-month studies"); up to four per path. For
   long decisions, up to three questions about concrete facts (pay for that role in that city,
   rent, program length).
2. **Recall first.** Hybrid search over the Elastic evidence index for the same question; a match
   is reused and logged as "Found in memory" — no crawl. (See `docs/ELASTICSEARCH.md`.)
3. **Search** with the Browserbase Search API: `bb.search.web(query=…, num_results=5)`. Forums and
   social hosts are skipped; the top result is read, and a second one if time allows.
4. **Read** every chosen page in **one Browserbase session for the whole decision**, through the
   same readability tiers, inside the time budget. Each step is logged with the session's URL
   (`https://www.browserbase.com/sessions/<id>`) so the UI's research feed can link to the replay.
5. **Extract** (LLM): for a reference class, the published rate and *the sentence it came from*;
   for a fact, the figure, unit and sentence.
6. **Verify in code.** A rate is accepted only if the figure literally appears in its own quoted
   snippet and parses as a percentage or ratio. Conversion to the simulator's per-step hazard is
   plain arithmetic, recorded on the evidence (`used_for`). A loose fit between the studied group
   and the person widens the sampling band (±0.15) instead of adjusting the number.
7. **Apply and re-simulate.** Accepted evidence is written to Elastic; the path's estimated events
   become *sourced*, facts set simulator parameters (salary → income, a home price → housing cost
   ratio, program length → when study ends; rents deliberately set nothing), the path's
   `revision` bumps and it is re-simulated. If anything fails, the path keeps its first
   simulation and says so.

`GET /research?branch_id=` returns the live feed (`searching` → `reading` → `found` / `skipped` →
`done`) that the UI shows while paths form.

Seen live: for "a month without drinking", the completion figure "between 61 and 64%" of Dry
January registrants was found, quoted and accepted from a journal article
(doi.org/10.1186/s12954-022-00603-x); a second figure was rejected by the snippet check; a later
decision about the same thing reused the stored figure without crawling. For the demo's San
Francisco path: a median home sale price, a median one-bedroom rent (apartmentlist.com) and Muni
fares (sfmta.com), each with URL and quote.

## The `browse` CLI

Installed globally (`npm i -g browse`) for manual checks — e.g. `browse cloud projects list` to
confirm the key and find the project ID, or `browse open <url> --remote` to see how a page loads
in a Browserbase session. The application itself does not depend on it.

## Limits, stated plainly

- Published *rates* that pass the figure-in-snippet check are rare; most possible events remain
  labelled estimates. Researched *facts* (prices, rents, fares, tuition) are plentiful.
- One concurrent session on this project means research is sequential per decision; forming a
  decision takes about 45 s to a first simulation and about two minutes to finished research.
- Login-walled profiles (LinkedIn, Instagram) usually yield a glimpse or a breadcrumb, not a
  history. A PDF export of the profile, dropped into Files, works better.
- Only public pages are read: no logins, no cookies, no kept-alive sessions. The one exception is
  opt-in and off by default: with `HEREAFTER_LINKEDIN_CONTEXT` set to a Browserbase context that is
  already signed in to LinkedIn, LinkedIn profiles are read on it through Stagehand
  ([STAGEHAND.md](STAGEHAND.md)).
