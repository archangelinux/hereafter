# Hereafter API contract

Backend: FastAPI on `http://127.0.0.1:8642`. The frontend dev server proxies `/api/*` to it
(prefix stripped). All bodies are JSON. Dates are ISO `YYYY-MM-DD`.

"Now" is always the server clock. No endpoint accepts a "now" value and no endpoint edits or
deletes an event on `main`.

## Types

```
LifeEvent {
  id: string
  person_id: string
  source: "scraped" | "passive" | "told" | "simulated"
  branch_id: "main" | <branch id>
  date: string
  domain: "career" | "housing" | "relationship" | "health" | "money"
  event_type: string            // e.g. job_start, job_change, city_move, marriage, divorce, birth,
                                // home_purchase, income_shift, death, education, goal, decision
  payload: object               // event-specific; never required for rendering
  confidence: number            // 0..1
  text: string                  // plain structured summary, always present (LLM-free)
}

StateVector {
  year: number, age: number, city: string, education: string, field: string,
  employment: "employed" | "unemployed" | "student" | "retired",
  income_band: "low" | "lower_middle" | "middle" | "upper_middle" | "high",
  relationship_status: "single" | "married" | "divorced" | "widowed",
  housing: "renting" | "owning" | "with_family",
  activity_proxy: number        // 0..1 social/activity density
  children: number, alive: boolean
}

Branch {
  id: string, person_id: string, label: string, forked_at: string,
  assumption: object,           // e.g. {"city": "San Francisco"}
  precondition: string | null,  // e.g. "offer_deadline: 2026-09-26"
  status: "open" | "merged" | "faded" | "expired",
  carried_event_id: string | null
}

BranchView {
  branch: Branch
  years: [{ year: number, solidity: number /* 0..1, cross-run agreement */,
            state: StateVector, events: LifeEvent[] }]
}
```

## Endpoints

| Method | Path | Body / query | Returns |
|---|---|---|---|
| GET | `/health` | | `{ok, llm_enabled, store: "elastic" \| "local", now}` |
| POST | `/ingest` | **multipart/form-data**, see below | `IngestResult` — always 200 |
| GET | `/trunk` | `?person_id=` | `{person, now, events: LifeEvent[], state: StateVector, agent_log: AgentStep[]}` |
| POST | `/simulate` | `{person_id, label, assumption, precondition?, horizon_years?}` | `BranchView` |
| GET | `/branches` | `?person_id=` | `{now, branches: BranchView[]}` — rechecks expiry first |
| POST | `/merge` | `{branch_id}` | `{merged: Branch, faded: Branch[], told_event: LifeEvent}` |
| POST | `/carry` | `{branch_id, event_id}` | `{goal_event: LifeEvent, branch: Branch}` |
| GET | `/narration` | `?branch_id=` | `{branch_id, complete: boolean, lines: {[event_id]: string}}` |

`AgentStep = {step, tool, args, reason, hits, planner: "llm" | "rules"}` — the retrieval agent's
logged query choices while building the state vector.

### `/ingest` — the Offering (one path for everything)

Multipart form fields, all optional except `person_id`, any combination:

| Field | Meaning |
|---|---|
| `person_id` | required |
| `display_name`, `birth_year`, `sex` (`M`\|`F`) | person metadata |
| `text` | freeform words: life story, a decision on their mind, pasted MBTI / Big Five, pasted resume. Also what "tell Hereafter something" sends. URLs inside it are picked out and crawled. |
| `handles` | JSON string `{github?, linkedin?, site?, instagram?}` |
| `links` | JSON string array of URLs |
| `live_source` | `github` \| `site` — the one handle crawled live; the rest load from cache |
| `files` | zero or more uploads: chat exports (.txt/.zip), resume (PDF/text), anything else |

```
IngestResult {
  person_id: string
  events_added: LifeEvent[]
  inputs: [{ name: string,
             kind: "handles" | "link" | "freeform" | "chat_export" | "resume" | "personality" | "unknown",
             outcome: string }]          // what the router made of each thing offered; prose, never an error
  personality: Personality | null
  reconciliation: [{ slot: string, chosen: string, over: string[], reason: string }]
}

Personality { O, C, E, A, N: number /* z-scores */, confidence: number, mbti: string | null }
```

`/ingest` never returns an error for bad input: a blocked link becomes a low-confidence glimpse or
a breadcrumb, an unreadable file is indexed as freeform. Raw chat messages are parsed in memory
and discarded; only structured events are stored. The UI shows `mbti` back to the user when they
gave one and never shows the trait numbers. `GET /trunk` returns the same `personality` on
`person`, and the latest `reconciliation` log alongside `agent_log`.

Links and handles are crawled only for the `person_id` that submitted them.

`/narration` is poll-only. The UI must render `LifeEvent.text` immediately and swap in the
narrated line if and when it appears. With `HEREAFTER_LLM=off` it returns `complete: true` and
no lines.

`/carry` is allowed once per branch, and only on a faded or expired branch.

A demo person `demo` is seeded on first start so the scene is never empty.

---

# v2 — scenarios, commits, chapters, evidence, security

Read `docs/PRODUCT.md` first. Everything above still holds except where this section changes it.
UI and API vocabulary: main, scenario, option, branch, commit, undo, switch, compare, merge, pick,
log. Never "git".

## Auth

`POST /people {display_name?, birth_year?, sex?}` → `{person_id, token}`. `person_id` is random.
Every other route requires `Authorization: Bearer <token>` and rejects a token that does not
belong to the `person_id` being touched (401/403). The seeded demo person is `demo` with token
`demo`. `/health` is open.

## New and changed types

```
Option   { id, title, details, deadline: string|null }
Scenario { id, person_id, situation, created_at, options: Option[], branch_ids: string[],
           status: "open" | "decided", decided_branch_id: string|null }
Commit   { id, branch_id, year, message, patch: object, created_at }   // hypothetical; undoable

Branch  += { scenario_id: string|null, option_id: string|null, commits: Commit[],
             research: "none" | "pending" | "running" | "done" | "failed",
             revision: number }                 // bumps whenever the branch is re-simulated
           status gains "stale" (replaces "expired"; same meaning)
BranchYear += { outlook: { [aspect]: { share: number, words: string, value: string } } }
             // aspects: alive, city, employment, income_band, relationship, housing, children
             // value = the medoid life's value; share = fraction of the 1,000 runs that agree;
             // words = "almost always" | "usually" | "as often as not" | "sometimes" | "rarely"

Evidence { id, branch_id: string|null, kind: "researched" | "statistic" | "personal",
           claim: string,                        // one sentence, human readable
           value: string|null, unit: string|null,
           source_title: string, source_url: string|null, retrieved_at: string,
           snippet: string|null,                 // the sentence it came from
           used_for: string|null,                // which simulator parameter it set, in words (incl. the arithmetic)
           reference_class: string|null,         // the studied population the figure is really about, one phrase
           gap: string|null }                    // one plain sentence: how that population differs from this person

Chapter  { branch_id, revision, from_year, to_year, title,
           status: "writing" | "ready",
           paragraphs: [{ text: string, evidence_ids: string[] }] }

ResearchStep { at, state: "searching" | "reading" | "found" | "skipped" | "done",
               message: string, url: string|null, session_url: string|null }
```

## Endpoints

| Method | Path | Body / query | Returns |
|---|---|---|---|
| POST | `/people` | `{display_name?, birth_year?, sex?}` | `{person_id, token}` |
| POST | `/scenarios` | `{person_id, situation, options: [{title, details, deadline?}]}` (2–4 options) | `{scenario: Scenario, branches: BranchView[]}` — returns as soon as each branch has a first simulation; research continues in the background and re-simulates (`revision` bumps) |
| GET | `/scenarios` | `?person_id=` | `{scenarios: Scenario[]}` |
| GET | `/research` | `?branch_id=` | `{branch_id, research, steps: ResearchStep[]}` — poll while `research` is pending/running |
| POST | `/branches/{id}/commits` | `{year, message}` | `BranchView` — the message is the person's what-if in their own words; structure is extracted, the branch re-simulated from that year |
| POST | `/branches/{id}/undo` | `{commit_id?}` (default: latest) | `BranchView` |
| GET | `/compare` | `?a=&b=[&c=]` | `{branches: Branch[], checkpoints: [{year, age, rows: [{aspect, differs: boolean, values: [{branch_id, value, words, share}]}]}]}` — checkpoints every five years |
| GET | `/chapters` | `?branch_id=&year=` | `Chapter` containing that year. Written lazily and cached per `revision`; `status: "writing"` comes back immediately with plain-text paragraphs, poll until `ready`. With the LLM off it is `ready` at once, built from structured text |
| GET | `/evidence` | `?branch_id=` or `?ids=a,b,c` | `{evidence: Evidence[]}` |
| POST | `/merge` | `{branch_id, confirm}` | as before; **400 unless `confirm` equals the branch label exactly**. Irreversible. Marks the scenario decided |
| POST | `/carry` | unchanged | "pick" in the UI |
| GET | `/inventory` | `?person_id=` | `{sources: [{source, count, newest, examples: LifeEvent[]}], handles: [...], cached_pages: number, sent_to_llm: string[], stored_nowhere: string[]}` |
| POST | `/erase` | `{person_id, confirm: "erase"}` | `{erased: {events, evidence, branches, cached_pages}}` — removes everything about the person everywhere. The only deletion in the system |

`/simulate` remains for a single ad-hoc branch. `/branches` returns the new fields. Undo never
touches main; nothing but `/erase` ever removes a main event.

---

# v2.1 — any decision, any size (read PRODUCT.md "Any decision, any size")

Deltas on top of v2. Nothing else changes.

```
LifeEvent.domain      free-form lowercase life-area tag (work, money, health, body, mind, love,
                      family, friends, learning, growth, home, play, food, ...). Not an enum.
LifeEvent.payload     simulated events carry  basis: "sourced" | "estimated" | "background"
                      and evidence_id when sourced.

Scenario += { horizon: { unit: "days" | "weeks" | "months" | "years", count: number } }
            // inferred from the situation; POST /scenarios accepts an optional `horizon` override

PossibleEvent { key, label, domain, basis: "sourced" | "estimated" | "background",
                evidence_id: string|null, words: string }     // words = verbal likelihood
Branch += { model: { events: PossibleEvent[] } }              // what could happen here, and on what basis

BranchView.years[i] += { at: "YYYY-MM-DD", label: string }    // label e.g. "tonight", "week 3", "2031"
            // steps may be days, weeks, months or years apart. Position by `at`, caption by `label`.
            // `year` stays (= year of `at`). `outlook` aspects are now the option's own outcomes
            // (keyed by PossibleEvent.key, plus background aspects on long horizons).
Commit  += { at: "YYYY-MM-DD" }     Chapter += { from_at, to_at }   (a chapter is a span of steps)
```

| Method | Path | Query | Returns |
|---|---|---|---|
| GET | `/lives` | `?branch_id=&which=typical\|rare` | `{which, rarity_words, years: BranchYear[]}` — `typical` is what BranchView already shows; `rare` is the rarest coherent life among the thousand |
| GET | `/chapters` | `?branch_id=&at=YYYY-MM-DD[&which=rare]` | as before; `year=` still accepted |
| GET | `/compare` | unchanged query | adds `distinctive: [{branch_id, label, words, basis}]` — events unusually common in each branch against its siblings (Elastic `significant_terms`) |

---

# v2.2 — clarifying questions, and many scenarios at once

The person never has to explain fully. One sentence and the option names are enough: Hereafter
fills in from what main already says (retrieval), then from live research, and only then asks.

```
Question { id, scenario_id, text, why: string,            // why it matters, one short clause
           choices: string[],                              // 2–5 quick picks; free text also allowed
           applies_to: string[] /* option ids, [] = all */, answer: string|null }
Scenario += { questions: Question[], assuming_branch_id: string|null }
```

- `POST /scenarios` also returns `questions` (0–3, never more). A question is only asked when the
  answer is not already on main (the agent searches first and logs that it did) AND it would
  materially change the branches (e.g. the major, for a choice between universities). Branches
  are simulated immediately without waiting: unanswered questions simply leave those branches
  wider and fainter (lower solidity), which is how the UI shows "more in, clearer futures".
- `POST /scenarios/{id}/answers {answers: {[question_id]: string}}` → `{scenario, branches}`.
  Each answer is appended to main as a told-event (so it is never asked twice, in this or any
  later scenario), the affected outcome models are rebuilt, branches re-simulated, `revision` bumps.
- Many scenarios can be open at once; each is its own fork on main with its own horizon, and they
  are independent by default (no combinatorial explosion). To deliberate one *inside* another,
  pass `assuming_branch_id` on `POST /scenarios`: the new scenario forks from that branch's
  simulated state instead of from now ("assuming I go to Waterloo — do I live in residence?").
- `GET /scenarios` lists them with status and nearest deadline so the UI can show what is still
  being turned over, soonest first.


---

# As built — additive fields the backend also returns (nothing above changes)

```
Branch.model   = { events: PossibleEvent[], mix: { sourced, personal, estimated },   // counts, so the UI can say it plainly
                   widen: number,            // > 0 while a clarifying question that applies to this branch is open
                   life_script: { partner, children, home } }   // which life-script events may appear at all (opt-in)
PossibleEvent += { kind, window: [firstStep, lastStep], bin, probability|null, band, depends_on, reference_class, follow_through }
                 basis may also be "personal" (the person's own track record; needs >= 5 ended commitments on main)
Branch        += { params, fork, horizon, span: Horizon }       // researched parameters; the frozen present; step layout
Evidence      += { question, figure, span_days }                 // what was looked up; the figure exactly as written
Scenario      += { nearest_deadline }                            // GET /scenarios is sorted open-first, soonest deadline first
Commit.patch   = { step, model: { force, prevent, likelier, less_likely }, ...life-course fields on year horizons }
/compare rows += { label }; checkpoints += { at, label }; distinctive items += { key }
/health       += { llm_provider, research }
POST /branches/{id}/commits accepts { message, at } or { message, year }.
Simulated events: payload.basis is "sourced" | "personal" | "estimated" | "background"; event_type is the PossibleEvent key
(or the life-course type for background); "commit" events carry payload.commit_id.
ResearchStep messages also log: the look in the person's own log, "Found in memory" (evidence reused from the index
instead of crawled), figures rejected because they were not in their own quoted snippet, and the life-script check.
```

## Forming (non-blocking scenarios)

`POST /scenarios` answers in well under a second. It returns the scenario (with a provisional, rules-based `horizon`
and `questions: []`) and one **placeholder** branch per option:

```
Branch += { forming: boolean }     // placeholder: forming true, status "open", research "pending", model null,
                                   // revision 0; its BranchView has years: []
```

Everything slow happens in the background, and each landing bumps `revision`: imagining what could happen
(about 30–45 s) -> first simulation (`forming` false, `model` set, `years` filled, the scenario's real `horizon` and
`questions` saved — re-read `GET /scenarios`) -> research -> re-simulation. Poll `GET /branches` (or `/research`) until
`forming` is false; `GET /research` narrates from the first moment ("Imagining what could happen if you choose: …",
then the look in the person's own log, the count of possible events, the life-script check, then searching / reading /
found). While forming, a branch cannot take commits or be merged (409) and `/compare` returns empty checkpoints.
`POST /scenarios/{id}/answers` works the same way: answers are written to main at once, the affected branches come back
with `forming: true` and their previous years still readable, and are rebuilt in the background. It returns 409 while
the scenario is still forming. Background also runs under month horizons of twelve or more (one background year per
twelve steps). `demo` evidence marked kind "researched" was really researched on its `retrieved_at` date and is stored in
`backend/app/seed_data/demo_research.json`; rerun `python -m app.seed_research` to refresh it.

## Scale, and dates instead of step counts

```
Scenario += { scale: "big" | "small" }   // big = a life decision (years, or six months and more, or the person says so);
                                         // small = a day-to-day action or dilemma. Inferred in the same extraction call
                                         // as the horizon; POST /scenarios accepts an optional `scale` override.
```

`BranchYear.label` is always a plain date derived from `at`: "21 September" (with the year when it is not the current
year: "4 January 2027"), just the year on year-scale branches ("2031"), and "today" only for today's date — computed
when read, so it is never stale. There is no "day 3", "week 2", "month 4", "tonight" or "tomorrow" anywhere: not in
labels, compare checkpoints, chapter titles or chapter date captions, and the prompts that propose events and write
narration are told to use dates too. (`Horizon.tonight` is still returned but no longer affects labels.)

---

# v2.3 — assistant conversation exports, and forgetting one offering

- `/ingest` recognises exports of conversations with an AI assistant (Claude's or ChatGPT's
  `conversations.json`, inside the export zip or on its own): input `kind: "ai_chat_export"`.
  Only the person's **own** messages are read (newest conversations first, up to a few chunks —
  the outcome says when older ones were left unread); the assistant's replies and the account
  files in the zip (`users.json`, `projects.json`, …) are never read. The raw export is parsed in
  memory and dropped. What is kept is the same as for any other source: structured events on main.
- `LifeEvent.origin: string` — which offering an event came from (an upload's name, a URL,
  `"your words"`).
- `GET /inventory` adds `offerings: [{origin, count, newest, source}]`.
- `POST /forget {person_id, origin}` → `{origin, removed}` removes everything on main that came
  from that one offering (owner only; not available on `demo`). Narrower than `/erase`, same
  principle. Re-offering the same file later adds the events back; offering it twice never
  duplicates them (event ids are deterministic).

---

# v2.4 — a decision is written like a ticket

`POST /scenarios` accepts `{person_id, text}`: one plain line (or a title line followed by
`- option` lines), exactly as the person would write a ticket or a commit message. The situation
and the 2–4 options are found inside it — by rules when the line lists them ("A, B, or C?",
"A vs B"), otherwise by one small, fast extraction call (an implied yes/no becomes the action and
not doing it). Horizon and big/small are judged by Hereafter. `situation` + explicit `options`
still work; one explicit option now gets its implied alternative instead of a 422; an empty
request is a 400.

## Editing a decision ticket

`POST /scenarios/{id}/edit` → `{scenario, branches}`. Body, any combination:

```
{ situation?: string,                         // rename the decision
  scale?: "big" | "small",                    // stored as the person's choice: Scenario.scale_chosen = true, never re-inferred
  rename?:   { [option_id]: string },         // renames the option AND its branch label; nothing is re-simulated
  deadline?: { [option_id]: "YYYY-MM-DD" | null },   // sets/clears that branch's decide-by precondition; staleness is
                                              // re-decided on the next read (a stale branch whose deadline moves reopens)
  add?: [{ title }] }                         // up to four paths in total: each is a new placeholder branch (forming: true)
                                              // that goes through the same background forming + research; siblings untouched
```

409 on a decided scenario, and for `add` while the scenario is still forming; 404 for an unknown option id; 400 for a bad
date or a fifth path. Merge confirmation uses the branch's current (renamed) label.

`Scenario += { scale_chosen: boolean }`. Scale is decided in code, after the LLM: the person's explicit scale always wins;
otherwise a horizon under six months (26 weeks) is `small` and six months or more is `big`; the LLM's own opinion is used
only when no horizon could be inferred at all; failing that, `small`. With the LLM off and no clue in the words, the
horizon defaults to eight weeks (it used to default to forty years).

---

# v2.5 — probabilities, shown and explained

The "no numbers" rule is withdrawn for likelihoods (the person asked for it): every possible
event carries a probability, lists are ordered most to least likely, and every number can be
opened to see exactly how it was made.

```
PossibleEvent += {
  probability: number,          // 0..1: share of the 1,000 simulated lives in which it happens within the horizon
  breakdown: {
    base: { kind: "sourced" | "personal" | "estimated" | "background",
            value: number,                    // the base probability over the event's window
            range: [number, number] | null,   // the band it was sampled from (estimates, loose-fit sources)
            evidence_id: string | null, reference_class: string | null, note: string },
    personality: [{ trait: "O"|"C"|"E"|"A"|"N", trait_name: string, z: number, confidence: number,
                    direction: 1 | -1, beta: number, shift_logodds: number, basis: "published" | "assumed" }],
    dependencies: [{ on: string /* event key */, label: string, multiplier: number }],
    adjusted: number,             // base after the personality shift, before dependencies and sampling
    simulated: number             // = probability
  }
}
BranchView.years[i].outlook[key] += { probability: number }    // cumulative by that step; `words` stays for compatibility
```

`GET /model` → `{version, summary, steps: [{title, text}], constants: [{name, value, meaning}],
limits: string[]}` — the model card, in plain words, for a "how these numbers are made" panel.
`GET /compare` rows and `distinctive` entries carry `probability` alongside `words`.

## v2.5 as built (additive to the v2.5 section)

```
PossibleEvent += { base_probability: number|null,   // the sourced/personal base figure (what `probability` used to hold before v2.5)
                   traits: [{trait, direction}],     // proposed directions only; hazard: a matching life-course transition or null
                   terms:  [{trait, direction, beta, basis}] }   // what the engine actually applied (published beta, or the fixed 0.20)
breakdown.dependencies[i] += { relation: "likelier"|"less_likely"|"prevents"|"requires", note }   // `requires` is a gate: multiplier 1.0
breakdown += { simulated_note }                     // says whether it is "has happened by the horizon" or "at least once" (recurring)
outlook[key].probability                            // cumulative for the option's own events; for background aspects (city, housing…)
                                                    // it equals `share`: the share of lives with the value shown
```

`model.events` is sorted by `probability`, most likely first; the simulation itself uses a canonical order, so display
order never changes the lives. `breakdown.base.value` for an estimate is the midpoint of `range`. `breakdown.personality`
is `[]` when the person has no personality estimate or no trait bears on the event. Branches simulated before v2.5 are
re-simulated once at startup (`revision` bumps). The demo person now has an MBTI type so its breakdowns show shifts.
`GET /model` is open (no token); the same text is `docs/MODEL.md`.

---

# v2.6 — four running measures, shown as change from now

Every path tracks four things as a **difference from where the person is now** (now = 0), never as
an absolute score: `health`, `joy` (short-term happiness / dopamine), `fulfilment` (long-term), and
`money`.

```
PossibleEvent += {
  effects: { health: -2..2, joy: -2..2, fulfilment: -2..2, money: -2..2 },   // integers; 0 = no effect
  money_amount: { value: number, currency: string, per: "once" | "month" | "year", evidence_id: string|null } | null,
  effects_basis: "judgement" | "sourced"      // sourced only when money_amount comes from evidence or the person's own figures
}

Measure = "health" | "joy" | "fulfilment" | "money"
Branch += {
  measures: {
    series: { [m in Measure]: [{ at: "YYYY-MM-DD", mean: number, low: number, high: number }] },  // per dated step; low/high = 10th–90th percentile of the 1,000 lives
    end:    { [m in Measure]: { delta: number, low: number, high: number, marks: "−−−"|"−−"|"−"|"="|"+"|"++"|"+++" } },
    money_end: { value: number, low: number, high: number, currency: string } | null   // only when amounts are known
  }
}
Person += { money: { income: number|null, net_worth: number|null, currency: string } | null }   // optional, given by the person; encrypted at rest
```

- `POST /people` and `POST /ingest` accept optional `income`, `net_worth`, `currency`.
- `GET /compare` adds `measures` per branch (the `end` block) so paths can be compared on the four.
- `GET /model` explains how effects are assigned and accumulated (see docs/MODEL.md).

## Path logic, as built (supersedes earlier notes where they differ)

**Horizons and steps.** Small decisions run hours to a few weeks, evenly stepped. Big ones are modelled where they play out:
`{unit: "years", count: 3}` by default, never more than 5 unless the person passes a `horizon`. Long paths (years, or 6+ months)
step **weekly for the first month, monthly to the end of year one, then quarterly** (3 years = 23 steps). `BranchYear.label` is
always a plain date ("19 June 2028"; year-only labels are gone). Each lived event has its own `date` inside its step (and inside
its own window), never before what it follows — draw events at `event.date`, steps at `at`.

**Step zero is the choice.** `model.events[0]` is `{key: "choice", head: true, basis: "choice", probability: 1, label: "You accept the
offer"}`; it is the first lived event of every life (`payload.head: true`), dated at the decision. It is HEAD: `/merge` writes its
label to main as the told-event's text. It is left out of `/compare` rows and `distinctive`.

**A causal story.** `PossibleEvent += { phase: "right_away"|"settling_in"|"later", days: [from, to] /* days after the decision */,
after: string[], requires: string[], head?: true }`. `after` = not before those happen (or their moment has passed); `requires` =
never without them. Both are validated in code (unknown keys dropped, cycles cut, windows moved later, room left to follow) and
enforced in every simulated life. A base chance means "given what it requires"; bins gained `"almost certainly"` (0.93–0.99) for
the obvious first consequences. `breakdown.dependencies` lists `after`/`requires` with `relation` and `multiplier: 1.0`.
`depends_on` relations are now only likelier / less_likely / prevents.

**The life you read** is the modal life (see `GET /model`), not a medoid; `solidity` is now how settled the thousand lives are at
that step (it no longer depends on which life is shown). `/lives?which=rare` needs at least three events beyond the choice.

**Background** (life tables) is off unless `HEREAFTER_BACKGROUND=on`; with it off, `state` repeats the present and `outlook`
holds only the option's own events.

**Narration.** Each branch gets a stored story bible (setting, neighbourhood, two or three invented named people, real facts from
main) and every `Chapter` carries `recap`; chapters are written in order (the next is only pre-written once the current one is
ready), chapter one opens on step zero. Long paths chapter as: first month, rest of year one, then a year at a time.

**Commits and nested decisions.** `POST /branches/{id}/commits` takes `{message, at|year}` or `{event_key, at}` ("assume this
possibility happens": forced from `at`, or from the start of its window if later; message "<label> happens"; no LLM).
`POST /scenarios` takes `assuming_at` with `assuming_branch_id`: the decision forks from that path's state at that date, carries what
had already happened there as `Scenario.assumed_facts`, starts its branches at that date (`forked_at`), and returns `fork_at`.
Undoing a commit dated on or before a nested decision's `fork_at` is refused with 409 and a plain reason.

## v2.6 as built

`Branch.measures` exactly as specified, plus `money_end.note` (the ledger in words, set against income or net worth when given).
`money_end.currency` is the person's `money.currency` if set, otherwise the currency of the first known amount; only USD↔CAD is
converted. `PossibleEvent += { effects, money_amount, effects_basis, money_kind }` (`money_kind` tells research which real figure
would belong to the moment). `/compare` adds `measures: {[branch_id]: end}` and `money_end: {[branch_id]: money_end|null}`.
`POST /people` and `/ingest` accept `income`, `net_worth`, `currency`; `/ingest` also picks them up from the person's own words
when stated; `/trunk.person.money`, `/ingest.money` and `/inventory.money` return them. With the LLM off all effects are zero.
`Scenario += { scale_chosen, assuming_at, fork_at, assumed_facts }`. The demo person now has three scenarios: `demo-offer` (big,
three paths), `demo-tonight` (small, two paths) and `demo-farewell` (small, decided three weeks ago: one merged path, one faded).
