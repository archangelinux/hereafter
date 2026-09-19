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

### 1.2a The vocabulary, settled — *building*
"Commit a what-if" and "decide inside this life" confused the person who designed the product,
so they are gone. The whole vocabulary, as it appears in the UI:

| Word | Meaning |
|---|---|
| **main** | What really happened. |
| **decision** | A fork: a node with two or more paths. |
| **path** | One option, lived forward. |
| **step** | One thing on a path. The first step is the choice itself. |
| **HEAD** | The path you have selected; its first step is what a merge commits. |
| **Commit** | Add one step to the path you are on — typed, or by picking one of the listed possibilities ("assume this happens"). The path stays a single line; everything after re-simulates and the percentages update. Undoable. |
| **Branch** | Split the path you are on, at this point, into two or more paths — a decision on the path. You can branch off a commit. Undoable. |
| **Undo** | Remove your last commit. |
| **Switch** | Move to another path. |
| **Merge** | Make HEAD's choice real on main. Only that first step. Permanent. |

The rule the UI teaches once: *Commit adds a step. Branch splits the path. Both can be undone —
only Merge is permanent.*

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

### 1.4a A decision is a labelled node with paths — *built (API); UI building*
**Decision.** Creating a decision is as plain as a commit dialog: a short **decision** label (the
node), then two or more **path** labels (the options), in the person's own words. Nothing else —
no prompt sentence, no examples, no option descriptions, no dates, no horizon or kind pickers.
Whether it is a big life decision or a small day-to-day one is judged by Hereafter and shown as a
tag on the ticket that the person can flip. Tickets appear plainly, as typed, like rows in an
issue tracker; anything can be corrected inline afterwards.
**Why.** "there's no prompt for dilemmas that happen in my life. i create my own tickets and they
show up plainly — it is the narration of subsequent events that is written out in an
entertaining interesting way." All the writing effort belongs in the narration; every other
surface should be as terse as a developer tool.
**Rejected on the way.** (1) The guided composer sheet of 5.3 — "way too much". (2) A single
free-text "what are you deciding?" line with the options parsed out of it — still a prompt, and
less explicit than naming the paths. The API keeps accepting that one-line form (`text`), but the
UI does not use it.

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

### 3.3a Assistant conversation exports; forgetting one offering — *built*
**Decision.** A Claude or ChatGPT export is accepted like any other offering. Only the person's
own side is read; assistant replies and account files are never opened; nothing raw is persisted.
Every event records its `origin`, the inventory lists offerings with how much each contributed,
and **forget** removes one offering's events from main.
**Why not persist the raw export.** It is everything someone ever asked an assistant — far more
than Hereafter needs, and a liability to hold. What matters (what happened, what they are
turning over) survives as structured events; the file can always be offered again.
**On immutability.** Main still cannot be *edited*. Forget and erase are the owner withdrawing
what they gave, not rewriting what happened.

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

### 5.6 Big decisions and small ones look different; paths flow; text is readable — *building*
**Decision.**
- Every scenario is **big** (a life decision) or **small** (a day-to-day action or dilemma).
  Habit-style scenarios are not used as examples: they do not paint a clear picture.
- **Big**: a large round plaza on main; options leave in entirely different main directions as
  full-width paths; when one is merged, *main itself turns* along it and the others stay, greyed.
- **Small**: a small circle on main; options are thin, short offshoots; a merged one loops back
  into main like a thin cup handle; unchosen ones remain as short grey stubs. Main does not turn.
- **Paths are fluid**: one smooth continuous flowing band. Circles appear *only* at decisions —
  the rows of stepping stones of 5.4 read as "ugly and confusing" once many paths were on screen.
  No islets under the path; sky, clouds, palette and the small figure stay.
- **Text**: one enforced type scale, nothing under 12px, reading text always full-strength
  #5C5347 with a single secondary tone for metadata — no faint or blurred text; state is shown
  with a word, not by fading. **Dates only**: no "week 3" or "day 3" anywhere.
**Why.** With several scenarios open, everything looked alike: the eye could not tell a life
decision from tonight's dilemma, and the metaphor (a merge changes main; a small choice is a
detour) was not visible in the geometry.

### 5.7 The HUD is one layout system, sized for real windows — *building*
**Decision.** The HUD is rebuilt as a single grid shell (left rail, free centre, right rail,
narration band) on one 8 px spacing scale with identical card chrome, compact type (body 14,
narration 16, labels 12), and breakpoints from about 700 px to 1700 px wide. Nothing is placed by
magic numbers, nothing can overlap, and the merge control is never dropped. The first screen is a
compact plain form in ordinary words ("About you", "Files", "Continue").
**Why.** Everything had been designed and checked only at 1440×900. In a normal-sized window
the right-hand column — including merge — vanished, panels overlapped, and type specified at
16–18 px filled its containers: "everything is way bigger or squished and doesn't fit nicely".
**Lesson.** Verify UI at the sizes people actually use, not one comfortable desktop size.

### 5.8 Live a path on the left, merge HEAD on the right — *building*
**Decision.** Selecting a path and living it through (the figure walks, the narration advances) is
exploration. The right-hand panel is where a decision is actually made: it lists the decision's
paths with a `HEAD` marker on the one selected, and its merge button commits **only the first
step of that path — the choice itself** — to main. Nothing of the simulated future becomes real:
main advances by one step, the rest of the chosen path stays a projection, siblings grey out.
Confirmation is typed, in place, in the panel.

### 5.9 Probabilities are shown, ordered, and explained — *building*
**Decision.** Likelihood words are replaced by probability values. "What could happen" is ordered
most to least likely with a percentage per event; each opens to a breakdown — base rate and its
source (or the estimate's range), the personality adjustment per trait, dependencies, and "happened
in N of 1,000 simulated lives" — and a model card (`GET /model`, `docs/MODEL.md`) states the whole
method, every constant, and its limits. The narration prose stays number-free.
**Supersedes.** The original "no numbers anywhere" rule and 2.7's words-only surfaces, at the
person's explicit request.
**The model, in one line.** adjusted = logistic(logit(base rate) + Σ direction × β × z × confidence),
then dependencies, then the share of 1,000 sampled lives. β is a published effect where one exists;
otherwise a fixed small constant (0.20 log-odds per SD) whose *direction* is a judgement and whose
*size* is not — and the UI says which.

### 5.10 The demo has to make sense: the person's verdict and what changes — *building*
**Verdict.** "i don't like this demo it doesn't even make sense at all and it's not logical" —
and, asked what, all four: the made-up story, what happens on a path, too much at once, the flow.
**What was actually wrong** (from reading the live demo): a job-offer path with a 40-year horizon
whose lived life was five events, out of causal order ("you miss home" before "you find a room"),
with a state passed off as an event, a background-table baby in the middle, the job itself never
starting, and thirty-four empty years; a two-event housewarming; a sample person with three big
decisions, a nested one, a stale one and a picked moment all on screen at once.
**Decision.**
- *Paths are causal stories.* Step zero of every path is the choice itself (HEAD — the one step a
  merge commits). Possible events are consequences of that option, in phases (right away,
  settling in, later), with `after` / `requires` ordering enforced in the sampler; moments, not
  states; nothing generic.
- *Horizons fit.* Small: hours to weeks. Big: about three years (five at most), dated steps weekly
  then monthly then quarterly. No multi-decade branches.
- *The life you read is representative*: the run closest to "every event at 50% or more happens,
  the rest do not" — not the sparsest run. (Replaces the medoid of 2.6 for outcome models.)
- *Background tables off by default.* They read as noise inside a personal story.
- *Narration is consistent*: a per-branch story bible and a running "story so far".
- *One decision in focus.* Everything else collapses to a circle on main. Nested, stale, picked
  and rare things appear only when looked for.
- *A guided flow*: one plain next-step line at each stage, gone once learned.
- *Your own life is the demo.* A returning person lands on their own main; the sample is one
  simple coherent story, reachable only on request.
- Panels have no borders, only shadows.

### 2.9 Four measures, as change from now — *building*
**Decision.** Every path tracks health, joy (short-term happiness / dopamine), fulfilment
(long-term) and money as a **difference from where the person is now** (+ / −), never as an
absolute score. Each possible event carries a small effect (−2…+2) on each measure; the sampler
accumulates them per simulated life — joy as a fast-decaying pulse, health and fulfilment building
and persisting, money both on the scale and, where real figures exist (salary, rent, tuition, the
person's own income and net worth), as a currency ledger — and reports the mean with a 10–90 % band.
**Why deltas.** An absolute "health score" would need a baseline nobody can measure; a change from
now is what a decision actually does, it needs no invented starting number, and it lets two paths
be compared directly.
**Honesty.** Effects are judgements about what an event means (not about whether it happens),
except money backed by evidence. The model card says so.

### 5.11 The 3D world must be clean up close — *building*
Bands meet decision circles flush, every end is finished (capped, tapered into mist, or hidden in a
junction), no hollow cross-sections, no ribbed or stacked translucent meshes, the HEAD ring and
event inlays sit exactly on the band, the figure stands on the centreline. Verified with close-up
screenshots of every join and end, not from overview distance.

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
