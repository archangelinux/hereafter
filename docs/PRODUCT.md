# Hereafter — product model (v2)

Version control for your life, without ever saying "git". This document is the shared source
of truth for what the product *means*; `docs/API.md` is how the two halves talk.

## The model

| Word | Meaning | Reversible? |
|---|---|---|
| **main** | What actually happened. An append-only log of real events: scraped, told, passive. | Never edited. |
| **scenario** | A real decision the person is facing, in their own words ("I have an offer in San Francisco; I could also stay for the master's, or take the bank job in Toronto"). | — |
| **option** | One thing they could do, described by them in as much detail as they like: what, where, pay, with whom, by when. 2–4 per scenario. | — |
| **branch** | One option lived forward: a thousand simulated lives from now, shown as one coherent life (the most typical run) plus an **outlook** of how the thousand spread. | Hypothetical. |
| **commit** | A further what-if decision made *inside* a branch at some future year ("2031: leave to start a company"). Everything after it is re-simulated. | **Yes — undo.** It was never real. |
| **switch** | Move your point of view to another branch. You live in one branch at a time. | Freely. |
| **compare** | Two or three branches side by side, aligned by age, showing only where the lives differ. | — |
| **merge** | "This is what I actually chose." The option is appended to main as a real event. Sibling branches become *roads not taken*: kept, readable, closed. | **No. Never.** Confirmed by typing the branch's name. |
| **pick** | Carry one moment from a road not taken onto main as a goal. One per branch. | No. |
| **log** | Main, read as history: date, message, where it came from, how sure. | — |
| **stale** | A branch whose precondition no longer holds (deadline passed, main moved on). It can be read but not merged. | — |

Two asymmetries carry the whole metaphor and must be felt in the UI:
commits on a branch are light and undoable; a merge into main is heavy and permanent.

## Any decision, any size (v2.1)

Inspiration: *Everything Everywhere All at Once*. A scenario is **anything the person is
deliberating** — texting an ex, a month without drinking, the party or the problem set, a
haircut, lending a friend money, therapy, a marathon, a move, a job. Small, personal, granular,
unpredictable. The demographic life-course (age, city, income band, the StatCan tables) is
**deep background**: it still runs silently underneath long branches to supply ageing, peers'
weddings, parents, money drift — it is never the headline and never the only thing a branch is
made of.

So a branch is not a patch on a fixed state vector. Each option gets its own **outcome model**:

- **Horizon fits the decision**: tonight → this week → three months → years. Steps on a branch
  are dated, not yearly.
- **Possible events** specific to this option ("you sleep under five hours", "they reply within
  a day", "you are still not drinking at week four", "the loan is repaid"), in free-form life
  areas (work, money, health, body, mind, love, family, friends, learning, growth, home, play,
  food …), with simple dependencies between them.
- **Where likelihoods come from**, in order: (1) *sourced* — a published rate found by live
  research through Browserbase, accepted only if the figure literally appears in the quoted
  snippet (checked in code), stored as evidence; (2) *estimated* — no published rate found: the
  LLM may only place the event in a verbal bin (rare / sometimes / as often as not / usually),
  code maps the bin to a range, and the event is drawn and labelled as an estimate everywhere;
  (3) *background* — the life-course tables.
- The **simulator** samples a thousand lives from that model. With the LLM off it re-runs any
  stored model deterministically; the LLM is never in the sampling loop.
- **Rare lives**: besides the most typical life, the person can jump to the *rarest coherent
  life* among the thousand — the one-in-a-thousand universe — drawn as the faintest line.

### Nothing this specific has a statistic — so research the reference class

No study exists about *your* ex or *your* first year. For each possible event Hereafter names the
nearest **reference class** that does get studied and researches that instead: "you finish the
degree" → the program's published graduation or retention rate; "they reply within a day" →
reconciliation rates among former partners; "still not drinking at week four" → completion rates
in dry-month studies. The figure is used exactly as published. The evidence records which
population it describes and, in one sentence, how that population differs from the person; when
the fit is loose the event is sampled from a band around the figure, so poor fit shows as a
fainter line instead of false precision. Where main holds at least five relevant real events, the
person's **own track record** is a further reference class (an Elastic aggregation over their
log). Many events will still be estimates; each branch states its sourced / estimated /
background / personal mix plainly.

### The person never has to explain fully

One sentence and the option names are enough. Hereafter fills in from what main already says,
then from live research, and only then asks — at most three **clarifying questions**, each asked
only if the answer is not already on main and would materially change the branches (the major,
for a choice between universities). Questions never block: branches are drawn at once and
unanswered questions leave them wider and fainter; answering firms the lines up, and the answer is
appended to main so it is never asked again. *More in, clearer futures.*

### Many scenarios at once

Each scenario is its own fork on main with its own horizon. They are independent by default —
no combinatorial explosion of joint lives. To deliberate one decision inside another, a scenario
can fork from a branch instead of from now ("assuming I go to Waterloo — residence or not?").
A "still turning over" list shows everything open, soonest deadline first.

Elastic earns its place a third way here: every simulated life's events are indexed, and
**compare is a `significant_terms` aggregation** (what is unusually common in this branch
against its siblings), rarity is `rare_terms`, and the shared evidence base is searched
(hybrid) for reusable evidence *before* anything is crawled again.

## Who decides what

1. **The person** decides scenarios, options and commits.
2. **The simulator** decides what happens: a deterministic Monte Carlo over published statistics,
   parameterised by researched facts about the option. It runs with the LLM off.
3. **The LLM** never decides an outcome. It (a) extracts structure from messy input, (b) chooses
   which things to look up (Elastic queries, research questions), (c) writes the lived narrative
   around a fixed skeleton of simulated events, citing evidence.

## A branch is a life you can read

Walking a branch is reading it: chapters (an era of a few years each) of rich, second-person,
specific prose — where you live, what the days are like, what it costs, who is around — written
around the simulator's fixed events for that era, with callbacks to the person's real past
(retrieved from Elastic) and **margin notes** that tie each factual claim to evidence:

- *researched* — a fact about this option read from the live web via Browserbase (rent, pay,
  program length), with URL, date and the sentence it came from;
- *statistic* — the published table behind a simulated event, and how many of the thousand
  simulated lives agree;
- *personal* — the real event on main that a callback refers to.

Numbers rule, revised: the main surfaces stay number-free (likelihood is drawn as how solid a
line is, and said in words: *almost always, usually, as often as not, sometimes, rarely*). The
**evidence drawer**, opened on request, is the one place figures and sources appear. Statistics
are the evidence; the narrative is the experience.

## What the sponsors do (the one-sentence versions)

- **Browserbase is how Hereafter reads the world on your behalf.** Twice: your own public
  footprint at the start (JS-heavy, login-walled pages a plain fetch cannot read, degraded
  gracefully to glimpses and breadcrumbs), and — the part that matters — *field research on
  every option at the moment you branch*: pay for that role in that city, rents, the program's
  length and outcomes, read live, cited, and fed to the simulator as parameters. The UI shows the
  reading as it happens.
- **Elastic is Hereafter's memory and its evidence engine.** (1) The append-only life log —
  create-only writes are what make the past immutable — with hybrid BM25 + dense retrieval and an
  agent that chooses its own queries to rebuild "who you are now" and reconcile conflicting
  sources. (2) The evidence index: every researched fact and statistic, hybrid-searchable, which
  is what the narrator retrieves from and what the evidence drawer shows. (3) The simulated
  multiverse itself: every run's events are indexed, so "what is distinctive about this life" is a
  `significant_terms` aggregation against sibling branches and the rarest life is `rare_terms`.

## What is stored, and where

| What | Where | Notes |
|---|---|---|
| Life events (main + simulated) | Elastic `hereafter-life-events` | Short factual text + structured payload. No third-party names. Keyed by a random person id, never a name or email. |
| Evidence | Elastic `hereafter-evidence` | Public facts about options; not personal. |
| Person record, scenarios, branches, commits, chapters | SQLite | Name and birth year live only here, encrypted. |
| Crawled page text | disk cache | Encrypted at rest; only self-submitted URLs; erasable. |
| Raw chat exports, uploaded files | **nowhere** | Parsed in memory, other people's names replaced before any LLM call, then dropped. |
| Sent to the LLM provider | — | Page text, the person's own words, de-named chat excerpts, simulated event logs. |
| Seen by Browserbase | — | Public pages only. No logins, no cookies, no kept-alive sessions. |

Security posture: bearer token per person (stored hashed); random ids; encryption at rest for
everything outside Elastic; an **inventory** screen (everything known, by source, with
confidence); and **erase** — the one deletion the system allows: you cannot rewrite your past,
but you can burn the book.

Not used: a blockchain. Personal data must never go on a public, undeletable ledger. The only
defensible use would be anchoring a *hash* of each merge as a public timestamp; that is a
garnish, not security, and is out unless there is a prize attached.

## UI direction (v3)

Content first. The interface is an illustrated **line graph you can read**, not a 3D toy:

- The **line**: main is one thick warm ink line rising from the past to *now*; above now,
  branches peel away as coloured lines with labelled commit nodes (short messages, not dots for
  their own sake). Likelihood is line quality — solid → dashed → dotted → fading wash. A merged
  branch rejoins and main continues along it; roads not taken stay, greyed and closed; stale
  branches are visibly cut. 2D SVG, hand-inked feel, storybook-morning palette. It should read as
  version control in three seconds to someone who has never been told so.
- The **page**: beside the line, the branch you have switched to, as chapters with margin notes.
- The **scenario composer**: "What are you deciding?" then option cards the person fills in.
  While branches form, a live research feed shows what Browserbase is reading.
- **Compare**, **commit a change here / undo**, **merge** (typed confirmation, ceremonial),
  **pick**, **log**, **inventory / erase**.

---

## v3 — the real you, and the ghost

Two figures, and the whole interface follows from which one you are looking at.

| | **The real you** | **The ghost** |
|---|---|---|
| Where | On main, at **now**, always. A plain marker: it separates past, present and future and says nothing else. | Out in the futures. One ghost, one place at a time. |
| Moves when | Only when a **merge** makes a choice real — main advances one step and the real you steps onto it. | Whenever you explore: pick a path, walk it, commit, revert, branch. |
| Shown as | Solid, at the last built stone of main. | Paler, with a thin line home to now, so the tie to reality is always visible. |
| Panel | **Left rail: reality.** Main's decisions, what has been decided, what is still open. A decision started here forks from now. | **Right rail: the futures you are in.** The path the ghost is on, what could happen, commit / revert / branch, and merge. A decision started here forks at the ghost's position. |

**Every branch, and every commit inside it, is an alternative universe.** The ghost is how they
are visited. It can:

- **walk** a path, step by step;
- **commit** a step at where it stands (one more thing that happens on this path);
- **revert** — step back to any earlier point on the path and re-simulate everything after it;
- **branch** at where it stands, splitting that future into further futures;
- **delete** a branch it no longer wants;
- **switch** to another path, leaving the one it was in.

None of it touches main. **Merge** is the one moment the two meet: the ghost's first step becomes
real, the real you steps onto it, and the ghost comes home to the new now.

Two ways to start a decision, and they mean different things:

- from the **left rail** (reality): a decision you face *now*, forking from main;
- from the **right rail** while the ghost is out (branch / commit): a decision inside the future
  you are exploring, forking at the ghost's position.

---

## v3.1 — context is not a log, and what the shapes mean

**What the person offers is context, not history.** A site, an upload, an assistant export: none
of it becomes a dated mark on main. It builds the person's **current state** — who they are now,
their personality estimate, the metrics that matter — which feeds the state vector, what the model
is told when it proposes and judges what could happen, and what research looks up. It is listed
under "your data", where it can be forgotten one offering at a time. Undated, ambiguous dots
disappear from the line by construction.

**The log** is what the person *did*: decisions they merged, and things they told Hereafter with a
date.

**The shapes mean exactly two things, everywhere, in both views:**

| Shape | Meaning |
|---|---|
| **Platform circle** (large = life decision, small = day-to-day) | A **node**: a decision, with its paths leaving it. |
| **Dot** on a path | A **commit**: one step the ghost added to that path. |

Nothing else is a circle or a dot. Simulated events are the steps of the path itself, read as you
walk; they are not marks scattered along it.
