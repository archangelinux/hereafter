# Hereafter — design decisions

A log of the choices that shape the product, why each was made, and what was rejected.
`docs/PRODUCT.md` describes the model as it stands; `docs/API.md` is the contract; this file is
the reasoning. Newest decisions are at the bottom of each section. Status is one of:
**built** (running and checked), **building** (specified, in progress), **dropped**.

Last updated 2026-09-19 (evening): everything marked *built* is running; see
"Known rough edges" at the end for what is not yet good.

---

## 1. What the product is

### 1.1 Version control for your life, without the word "git" — *built*
**Decision.** The interface and copy use the vocabulary of version control — main, branch,
commit, undo, switch, compare, merge, pick, log — and never the word "git".
**Why.** Earlier builds had a scene but no felt metaphor. The vocabulary is the metaphor; the
brand name of a developer tool is not, and would narrow who the product feels meant for.

### 1.2 Commits are light and undoable; merges are heavy and permanent — *built*
**Decision.** A *commit* is a further what-if made inside a branch ("2031: leave to start a
company"). It re-simulates everything after it and can be undone with one click, no ceremony,
because it was never real. A *merge* means "this is what I actually chose": it is appended to
main forever, requires typing the branch's name to confirm, and closes the sibling branches as
roads not taken.
**Why.** This asymmetry *is* the emotional core: exploring costs nothing, choosing costs
everything. The UI must make the two feel as different as they are.
**Rejected.** Treating merge as reversible (it would make main editable, breaking rule 1.3).

### 1.3 The past is append-only; "now" is the server clock — *built*
**Decision.** The event store exposes `append` and queries only. Elasticsearch writes use
`op_type=create`, so an existing id is never overwritten. No route accepts a date for "now".
The one deletion anywhere is **erase** (3.4), which removes a person entirely.
**Why.** "You cannot rewrite your past" has to be true in the storage layer, not just the UI.
Checked: a rewrite of an existing event is rejected by the live Elastic index, and the test suite
asserts the API has no PUT/PATCH/DELETE on main.

### 1.4 Alternatives come from the person — *built*
**Decision.** The person describes a **scenario** in their own words and names 2–4 **options**.
Each option becomes a branch. Hereafter does not invent the options.
**Why.** The first build offered a handful of dropdown fields (city, employment, housing), which
made every choice feel the same. The decision and its alternatives are the person's.

### 1.5 Any decision, any size — *built*
**Decision.** A scenario is anything being deliberated: texting an ex tonight, a month without
drinking, the party or the problem set, lending a friend money, therapy, a university, a move.
Horizons fit the decision (a night → weeks → months → decades); steps on a branch are dated, not
yearly; life areas are free-form tags rather than five fixed domains.
**Why.** Inspired by *Everything Everywhere All at Once*: the product is interesting when it is
personal, granular and unpredictable. A tool that only handles moves and jobs is a careers
calculator.
**Consequence.** A branch can no longer be "a patch on a fixed state vector" (see 2.2).

### 1.6 The person never has to explain fully — *built*
**Decision.** Minimum input is one sentence plus option names. Hereafter fills in from main
(retrieval), then from live research, and only then asks: at most three clarifying questions,
asked only if the answer is not already on main *and* would materially change the branches.
Questions never block — branches draw at once, unanswered questions leave them wider and
fainter, answers firm them up and are appended to main so nothing is asked twice.
**Why.** A form wall kills small decisions. Showing missing information as mist makes the
original tagline literal: *more in, clearer futures*.

### 1.7 Many scenarios at once, independent by default — *built*
**Decision.** Each scenario is its own fork on main with its own horizon. Scenarios do not
multiply against each other. To decide one thing inside another, a scenario may fork from a
branch ("assuming I go to Waterloo — residence or not?").
**Rejected.** Simulating joint lives across all open scenarios (3 × 2 × 4 … explodes, and nobody
can read it).

### 1.8 Rare lives — *built*
**Decision.** Besides the most typical life on a branch, the person can jump to the *rarest
coherent life* among the thousand simulated — drawn as the faintest line, readable like any other.
**Why.** The multiverse feeling comes from the unlikely universes, and they are already there in
the simulation; showing only the typical run throws them away.

---

## 2. How futures are made

### 2.1 The LLM never decides an outcome — *built, and extended*
**Decision.** Three parties, three jobs. The **person** decides scenarios, options and commits.
The **simulator** decides what happens. The **LLM** may only (a) extract structure from messy
input, (b) choose what to look up — Elastic queries, research questions, which clarifying
question to ask, which possible events are worth modelling — and (c) write narrative around a
fixed skeleton of simulated events. It never supplies a probability and is never inside the
sampling loop. `app/sim` cannot import the LLM module (tested).
**Why.** This is the "not a wrapper" claim, and it only holds if it is structural.

### 2.2 Each option gets its own outcome model — *built*
**Decision.** For every option, a model of 8–14 specific possible events with simple
dependencies and a dated horizon, genuinely option-specific (McMaster, Waterloo and UofT get
different researched facts and different events, not one list with the name swapped). A generic
numpy sampler draws a thousand lives from it, deterministically.
**Replaces.** The first engine: a fixed state vector (city, employment, income band, housing,
relationship) advanced yearly through ten national tables. It was correct and useless — nothing
in those tables distinguishes one personal choice from another.

### 2.3 Where a likelihood may come from — *built*
In order of preference, and always labelled:
1. **Sourced** — a published figure found by live research. Accepted only if the number
   literally appears in the quoted snippet (checked in code). Conversion to a per-step hazard is
   plain arithmetic, recorded on the evidence.
2. **Personal** — the person's own track record from their log, when main holds at least five
   relevant real events.
3. **Estimated** — nothing published was found. The LLM may only place the event in a verbal
   bin (rare / sometimes / as often as not / usually); code maps the bin to a fixed range; the
   event is drawn hollow and labelled an estimate everywhere.
4. **Background** — the life-course tables (2.5).
Each branch states its mix plainly.

### 2.4 Research the reference class, never the exact event — *built*
**Decision.** No study exists about your ex or your first year. For each event Hereafter names
the nearest class that does get studied ("you finish the degree" → that program's graduation
rate) and researches that. The figure is used exactly as published; the evidence records which
population it describes and how that differs from the person; a loose fit widens the sampling
band, so poor fit shows as a fainter line rather than false precision.
**Why.** It is the honest answer to "we will never have statistics this specific" — and it is
how forecasters actually work.
**Rejected.** Letting the LLM adjust a published figure "for this person" (that is the LLM
deciding the outcome).

### 2.5 The demographic tables are deep background — *built, demoted*
**Decision.** The Statistics Canada tables (mortality, marriage, divorce, fertility, income,
home ownership, job tenure, migration — all real downloads, cited in `data/SOURCES.md`) run
silently underneath branches of a year or more to supply ageing, peers' weddings, parents, money
drift. They do not run on short decisions and are never the headline. City · housing · employment
comes off the screen.
**Dropped.** Rebuilding the rates on census microdata in Elastic. It would have been the
"really good" version of the background layer, but the background is not where the product is
interesting, so the effort goes to 2.2–2.4 instead.

### 2.5a The background tables are biased, and are treated that way — *built*
**The biases, stated plainly.**
- *Canada-wide averages applied to one person*, wherever they live and whoever they are.
- *Cross-sections read as futures*: the share of today's 60-year-olds who own a home is used as
  if it were a 22-year-old's prospects. For housing especially this is too rosy.
- *A normative life script*: legal marriage only (common-law unions are invisible, so most
  people read as "single"), binary sex tables, fertility applied regardless of who the person
  is or what they want, retirement at 65.
- *Regression to the average*: showing the most typical of a thousand lives drawn from national
  averages produces the average Canadian's life. That is narrowing by construction.
- *Only what a table covers can happen.* The event vocabulary itself is the bias.
- Personality effects come from single studies of US and Australian cohorts.
**Decision.** (1) The tables are one more reference class (2.4): every background event carries
its population ("Canadians of this age, national average") and a gap sentence, and is sampled
from a widened band. (2) Life-script events — marriage, divorce, children, buying a home — are
**opt-in**: they surface on a branch only when the person's own main or scenario shows that the
thing is wanted or already part of their life; otherwise they are not shown. (3) Background
never runs on horizons under a year and never supplies more than a small share of a branch's
visible events. (4) Outside Canada the tables stay on only with the gap stated and the widest
band. (5) The outcome model of the person's actual decision (2.2) always outranks background.
**Why not delete them.** Long branches need time to pass — people age, friends marry, parents
grow old — and these are real published figures. They are kept as weather, not as plot.

### 2.6 One coherent life, plus how the thousand spread — *built*
**Decision.** The visible life on a branch is the medoid run — the single simulated life that
agrees most with the per-step consensus — not a stitched average. **Solidity** per step is the
share of runs that agree with it; the **outlook** gives that share per outcome, in words.
Same inputs always produce the same futures (the seed is derived from the person, the model and
the commits).

### 2.7 Statistics are the evidence; the narrative is the experience — *built*
**Decision.** A branch is read as chapters of rich second-person prose written around the
simulator's fixed events, with callbacks to the person's real past and margin notes tying every
factual claim to evidence (researched / statistic / personal). Hard rules in the prompt: every
simulated event appears; no life event outside the skeleton; texture is welcome; claims about
money and places must cite evidence; no probabilities in the prose.
**Numbers rule, revised.** Main surfaces stay number-free — likelihood is line quality and words
(*almost always, usually, as often as not, sometimes, rarely*). The **evidence drawer**, opened
on request, is the one place figures and sources appear.
**Replaces.** One dry line per event, which read as a log, not a life.

### 2.8 Personality tilts only what research supports — *built*
**Decision.** Big Five estimates tilt a hazard only where a published effect size exists and was
statistically significant in its source, scaled by the confidence of the estimate
(`data/PERSONALITY_SOURCES.md`). MBTI is mapped to low-confidence Big Five and shown back as
MBTI because that is what people know. The MBTI correlations were checked against a secondary
citation only (the paper is paywalled) — noted in the code.

---

### 2.9 Jev judges, our own arithmetic decides how likely — *built*
**Decision.** After the LLM proposes an option's possible events, a fourth LLM job — **Jev** — classifies
each one (career, education, research, entrepreneurship, financial, social, location, health, relationship,
other) and scores it 1–5 for personal fit, experience fit, difficulty, accessibility and evidence strength,
and answers yes / no / unknown to each *hard* prerequisite, all read against the person's own log from
Elastic. It returns no probability. `probability.py`, plain code that cannot import the LLM (tested), takes
the event's base rate (2.3), moves it on the log-odds scale by a bounded amount weighted by category, caps it at
3 % if a hard prerequisite is shown unmet, and returns likelihood, range, difficulty, confidence and the
evidence lines. The sampler runs on that likelihood.
**Why.** "Get into a competitive program" and "you finish the degree" call for different judgements of what
counts, and a published rate says nothing about *this* person. But letting a model's 1–5 opinion become the
probability would break 2.1. Bounding the shift means a published figure is adjusted, never replaced, and the
audit trail (`probability`, `basis`, `evidence_id`) is never overwritten.
**Rejected.** Averaging Jev's scores straight into the probability (unbounded, unauditable); asking Jev for
"a percentage, but only as a sanity check" (the number would leak into the result).
**Limits.** Jev scores once, before research lands; when research turns an estimate into a sourced figure the
estimate is recombined from the stored scores, not re-judged. The constants are hand-set (`data/SOURCES.md`).

## 3. Data, privacy, security

### 3.1 One ingestion path for everything — *built*
**Decision.** Router (rule-based label) → one extraction schema → index → reconcile. Every
source produces the same three outputs: events, state facts, a personality estimate. Conflicts
between sources are settled by recency and confidence, and each ruling is logged. `/ingest`
never returns an error: a blocked link becomes a glimpse or a breadcrumb.

### 3.2 Consent is enforced in code — *built*
**Decision.** The crawler loads only URLs built from rows the person submitted about
themselves, and follows no links found on a page.

### 3.3 Some things are stored nowhere — *built*
**Decision.** Chat exports and uploaded files are parsed in memory and dropped; only structured
events about the owner are kept; other people's names are replaced ("Person A") before any text
reaches the LLM.

### 3.4 Security posture — *built*
**Decision.** Random person ids; a bearer token per person (stored hashed); encryption at rest
for everything outside Elastic (person record, page cache, chapters); CORS limited to the local
frontend; an **inventory** screen (everything known, by source, plus what is sent to the LLM and
what is stored nowhere); and **erase**, the only deletion in the system.
**Known limit.** Event text in Elastic cannot be end-to-end encrypted because search has to read
it; it is kept pseudonymous and minimal instead.
**Before this.** There was no login at all — anyone with a person id could read a trunk.

### 3.5 No blockchain — *decided*
**Decision.** Not used. Personal data must never go on a public, undeletable ledger, which is
also the opposite of erase. The only defensible use is anchoring a *hash* of each merge as a
public timestamp; that is garnish, not security, and stays out unless a prize depends on it.

---

## 4. Sponsors

### 4.1 Browserbase reads the world on the person's behalf — *built*
Two jobs only a real browser can do: the person's own public footprint at the start (tiered:
substantial / thin / breadcrumb), and **field research on every option at the moment of
branching** — the reference-class figures of 2.4, read live, quoted, cited, fed to the simulator,
with the reading shown in the UI as it happens. Checked live: a session crawled a public profile
page in about seven seconds; a blocked page fell through to a breadcrumb as designed.

### 4.2 Elastic is the memory, the evidence base, and the multiverse — *built*
1. **The life log** — create-only writes, hybrid BM25 + dense retrieval (`semantic_text` +
   RRF), an agent that chooses its own queries to rebuild "who you are now". Checked live:
   "relocated to a new town for school" ranked the Waterloo move first with no shared words.
2. **The evidence index** — every researched fact and statistic, hybrid-searchable; searched
   for reusable evidence *before* anything is crawled again, so research accumulates across
   decisions. The narrator retrieves from it; the evidence drawer shows it.
3. **The simulated lives** — every run's events are indexed, so "what is distinctive about this
   branch against its siblings" is a `significant_terms` aggregation and the rarest life comes
   from `rare_terms`.

### 4.3 Composio — *not built*
Passive calendar events onto main. First thing cut, per the original spec; "tell Hereafter
something" covers it.

### 4.4 LLM provider follows the key — *built*
OpenAI when `OPENAI_API_KEY` is set (default `gpt-5.5`), otherwise Anthropic. All three roles
(extract, choose queries, narrate) were run live on OpenAI.

---

## 5. Interface

### 5.1 Three rejected rounds, and what they taught — *history*
1. A dark "night river" of light — replaced by the pastel storybook-morning palette.
2. A literal Monument Valley imitation (block aqueducts, a tower) — "took the spec too
   literally"; and the two paths ran parallel, so the fork could not be seen.
3. Rounded stepping stones on floating islets — "a bunch of AI generated looking circles…
   barely any content or meaning behind any of the actions".
**Lesson.** Decoration without content reads as generated. Every mark must mean something, and a
reference style is a mood, not a blueprint.

### 5.2 A line you can read, beside a page you can live in — *dropped as the main view*
A 2D inked graph on the left with a long reading page on the right. The content was right
(the scenario in the person's words, what could happen with likelihood words and basis, chapters
with margin notes) but the world was gone and it read as a document app: "the other ui was so
much prettier all we want is the richer info but the ui rn is terrible". The branch timeline
itself was liked and survives as the map (5.3).

### 5.3 A calm exploration game: the pastel world, a compact HUD, and a map — *built*
**Decision.** The storybook-morning 3D world returns as the hero, full-bleed and always alive,
redrawn so the life path is **one continuous flowing ribbon** that splits like a river delta at
forks and curves back in at merges — no rows of discs, no repeated shapes as decoration.
Likelihood is how built the ribbon is along its length (stone → translucent → outline → mist).
Events are sparse landmarks; commits are small gates; rare lives are hair-thin dotted offshoots;
roads not taken weather grey; stale ones break off. The coral figure walks the ribbon and the
camera follows.
The rich content arrives as a **compact, game-like HUD** instead of a document: a narration box
a few lines at a time (the whole chapter on request), waypoint cards at landmarks, a small
"what could happen" panel, a quest log (still turning over), a codex (evidence — the only place
with figures), a satchel (picked moments), and a small action bar with merge set apart and
visibly heavier. The **branch timeline** the person liked becomes a proper illustrated **map**:
a corner minimap during play, expandable to full screen; the map and the world are two views of
the same place, and the map is what makes fork/merge legible in three seconds.
**Two modes, one place.** Like a map's layer switch: **Island** (the 3D world) and **Line** (the 2D
branch timeline, full-bleed) are equal views with one toggle. Branch, position, selection and the
whole HUD carry across; Line is the fallback where WebGL is unavailable.
**Tone.** Alto's Odyssey, Journey, Monument Valley's menus — never arcade: no scores, bars,
neon or pixel fonts. Small serif UI, paper-and-ink HUD, everything compact, text tightened.
**Why.** Three rounds taught that beauty without content reads as generated (5.1) and content
without beauty reads as an admin panel (5.2). The game frame lets the world carry the feeling
and the HUD carry the meaning.

### 5.4 Island mode returns to the stepping-stone world — *building*
**Decision.** The continuous-ribbon islands of 5.3 are replaced by the earlier stepping-stone
world, restored as it looked, not reinterpreted: a winding trail of rounded stones on soft
floating islets, a delta split at the figure, stones going from solid to translucent to lavender
rings to mist as likelihood falls. The person's words: "i just want the previous ui". Everything
else in 5.3 stands — the compact HUD, the walking figure, Line mode, the map.
**Lesson.** When someone says an earlier version was prettier, restore it faithfully; do not
answer with a new interpretation of it.

### 5.5 Example paths for a first visit — *building*
**Decision.** Nobody lands in an empty world with a lone figure at now. A first-time visitor
sees two or three example scenarios already branched (one small, one medium, one large) with
chapters and evidence, plus a few example past events so now sits mid-life. They are labelled
as examples ("a borrowed life"), drawn slightly paler, cannot be merged or changed, never reach
the backend, and step aside when the person creates their first real scenario.

---

## 6. Practicalities

- **Ports.** Backend `127.0.0.1:8642`, frontend `5642`. Ports 8000, 8787 and 5173 belong to
  other projects on the development machine; `localhost` is avoided in the proxy because it can
  resolve to an unrelated IPv6 service.
- **Runs with nothing configured.** No `.env` → local SQLite event store, LLM off, seeded demo.
  A stored outcome model re-simulates with the LLM off; that is the demo of 2.1.
- **Secrets.** Real keys live only in `.env` (gitignored); `.env.example` is a blank template.

## 7. Known rough edges (2026-09-19)

- **Forming a scenario is slow.** `POST /scenarios` returns at once with placeholder branches,
  but the first simulation lands after about 45 s (one LLM call proposing each option's possible
  events, at low reasoning effort) and research after about two minutes. A smaller model was
  tried and rejected: it stopped sharing outcome keys across options, which breaks compare.
- **Most events are estimates.** Even after real research the demo's branches carry one sourced
  event each at best; the rest are labelled estimates. Researched *facts* (home prices, rent,
  fares, tuition) are plentiful; researched *rates* that pass the figure-in-snippet check are rare.
  Rents deliberately set no simulator parameter.
- **Island view**: a landmark tag can overlap the "tonight" label on a rare life; the overview was
  not re-checked after the last geometry tweaks. **Line view**: a few label collisions remain.
- **UI flows checked only against the offline sample:** merge ceremony, pick, forming-branch
  animation. The live run covered Offering, scenario, switch, answer, commit, undo, compare, erase.
- Evidence a person's research added to the shared index is removed when they erase.
