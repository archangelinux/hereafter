# The decision agent

An agent that helps someone think through a decision by asking **at most three questions**, each one
chosen because its answer would most change what they should do.

It starts knowing what you'd expect from a person's LinkedIn, GitHub, Instagram and chat history.
You give it a decision ("Berlin startup, stay at Acme, or start my own thing?"). It lays out the
routes, works out what it is unsure about, asks the one question that matters most, learns from
your answer, and repeats. At the end you can pick a route and it saves everything it learned.

## Try it (2 minutes)

```bash
cd backend
.venv/bin/pip install -r requirements.txt       # once (adds `rich`, for the tables)
# put OPENAI_API_KEY in the repo's .env

.venv/bin/python -m app.agent --fixtures        # fixture people you have added (the repo ships none)
.venv/bin/python -m app.agent --person <person_id> \
    -q "Should I take the seed-stage startup offer in Berlin, stay at Acme, or start my own company?"
```

While it asks, you can type:

| you type | what happens |
|---|---|
| `1`, `2`… | pick that answer |
| your own words | free-text answer (it reads it, and only believes what you actually wrote) |
| `s` | "not sure": stays unknown, never asked again |
| `/memory` | everything it knows about you, numbered, with where it came from |
| `/why` | why it chose this question (the maths, below) |
| `/routes` | the routes and how each outcome looks right now |
| `e` | stop asking and show where that leaves you |

Look at a finished session again any time: `python -m app.agent --show LATEST`

Run it hands-free (useful for demos and tests): `--answers "1;s;e" --decide 1`.
Use a real person from the app's store instead of a test person: `--person p_abc123`.

## What a real run looks like

From a test person (a backend engineer weighing a Berlin startup, staying, or founding
something). Real output, lightly trimmed:

```
UNKNOWNS: what I'm unsure of, and how much it matters
  unsure about                                             P(true)   worth knowing   changes the leader
→ You have enough savings or income to live while starting the company.   50%   78%   50% of answers
  You can legally create and operate the company where you live.          80%   31%   20% of answers

╭─ Question 2 of at most 3 ───────────────────────────────────────────────────────────╮
│ You asked how much runway a founder should have saved before quitting a job;        │
│ could you live while starting your own company?                                     │
│                                                                                     │
│ Because I read:                                                                     │
│   [10] chat: “how much runway a founder should have saved”                          │
│                                                                                     │
│ If this doesn't hold, “Start my own company” falls apart. Your answer could change  │
│ which option comes out ahead in 50% of cases.                                       │
│   1. Yes, I could cover it     2. No, I couldn't cover it     s. Not sure           │
╰─────────────────────────────────────────────────────────────────────────────────────╯
> 1
Saved to memory as item 15: “Yes, I could cover it”
What that changed:
  Start my own company: +0.039 → +0.116  ▲ +0.077
```

The question quotes something real from the person's own history, asks about the one requirement that
could sink the leading route, and the answer visibly moves it.

## How it decides what to ask

The important part: **a calculation picks the question. The language model only words it.**

1. **Lay out the routes.** For each option the model imagines six things that could happen
   ("you land a co-op term", "you burn out in year one"), each tagged as good or bad and by what part
   of life it touches: money, growth, stability, wellbeing or freedom.
2. **Judge them against you (this is the Jev step).** The model reads your numbered record and scores
   how well each outcome fits you. It also lists **requirements**: hard things that must be true for a
   route to work at all ("you are allowed to work in Germany") and how likely each is to be met given
   what it knows. Where your record is silent it falls back to the base rate for a *typical person* in
   your broad situation (labelled "typical" on screen), never a guess about you.
3. **Score the routes.** Plain code turns that into a likelihood for every outcome (using the repo's
   `probability.py`), and a score per route. A route is worth the average of
   `good-or-bad × likelihood × how much you care about that part of life`. If a requirement is unmet,
   the *good* outcomes that depend on it collapse (you can't get what needs it); the risks of trying
   stay, since failing a requirement doesn't make them go away.
4. **Find what's worth asking.** Every unknown (a requirement it's unsure of, or *what you care
   about most*) gets a value: **how much better would your choice be, on average, if you knew the
   answer?** That is the *expected value of perfect information*. It is zero when no answer could
   change which route is best, so a question that can't matter is never asked. A route that needs
   several requirements at once is valued both as things stand and as if its other requirements hold,
   so the one that could still sink it isn't overlooked.
5. **Ask the top one.** The model writes it, grounded in something it already knows about you. Code
   checks it. You answer. The answer becomes a new numbered memory, everything is re-scored, and it
   tells you what changed.
6. **Stop.** It always asks at least one question. After that it stops at three, or sooner if nothing
   left could change the answer, or when you press `e`.

## Why you can trust the questions (no hallucinations)

| Risk | What stops it |
|---|---|
| The model claims something about you that isn't in your record | **Receipts.** Any claim must cite a numbered item and copy a phrase from it. Code checks the item exists and the phrase is really in it. No valid receipt means no personal claim: a requirement falls back to the typical person's base rate, a score to neutral. |
| A question mentions a number, company or name that appeared nowhere | Code scans every question. Any number or name that isn't in your record, the decision or the routes gets it rejected. |
| A question is vague, leading, or a stranger could have been asked it | Must quote something about *you*, be one question of at most 25 words, and never mention probabilities. |
| The model invents statistics | It never gives one. Every number comes from code. |
| It misreads your free-text answer | An interpretation only counts if the supporting words are copied from your answer. Otherwise the topic stays unknown. |
| The written question fails the checks twice | It is replaced with a plain question that makes no claim about you, and the screen says so. |
| It infers private things (health, relationships, politics…) from social media | The prompts forbid it, and it only ever quotes what is in your record. |
| It asks too much | The cap of three is enforced in code, not in the prompt. |

## What is saved

Every step writes to `backend/sessions/<id>/` (git-ignored):

- `session.json`: the complete state (memory, routes, unknowns, questions, answers), which the UI can load later.
- `memory.md`: the same thing as a readable document: what it knows and where it came from, the
  routes with evidence, what it asked, what each answer changed.

Your answers are saved as new memory items marked **(your answer)**. When you decide on a route, the
session is marked with it, so later work can start from that path with everything already known.

## Where things live

| File (`backend/app/agent/`) | What it does |
|---|---|
| `cli.py`, `render.py` | The terminal chat and its tables. Only presentation. |
| `engine.py` | The loop: start, ask, answer, decide, save. |
| `uncertainty.py` | The maths: scores, expected value of information, when to stop. **No language model.** |
| `verify.py` | The receipts and question checks. **No language model.** |
| `questions.py` | Chooses wording (model), checks it, retries once, falls back. |
| `prompts.py` | Every instruction the model gets, and the shape of what it returns. |
| `context.py` | What the agent knows: loads a real person (or a fixture JSON you add under `fixtures/`); numbers the items. |
| `memory.py`, `model.py` | The markdown memory file; the saved state. |

## Settings that can be tuned

All hand-set, in `uncertainty.py` and `engine.py`:

| Setting | Value | Meaning |
|---|---|---|
| `MAX_QUESTIONS` | 3 | The hard cap. |
| `STOP_REL_EVPI`, `STOP_FLIP` | 12%, 25% | Stop when the best question is worth less than 12% of the gap between routes *and* could change the leading route in fewer than 1 in 4 possible answers. |
| `BASE_WEIGHT`, `PRIORITY_BOOST` | 0.10, 0.40 | How much each outcome counts, and the extra weight on what you care about most. |
| `ANSWERED_MET`, `ANSWERED_UNMET` | 0.97, 0.03 | How firmly your answer settles a requirement (people misremember). |

## Testing

```bash
cd backend
.venv/bin/python -m pytest -q tests/test_agent.py   # offline, no key needed: 22 tests
```

The tests use a scripted fake in place of the model and check the parts that matter: quotes must be
verbatim, invented names and numbers are rejected, a requirement with no evidence uses the typical base rate, not the model's claim, a question
that can't change the outcome isn't asked, the cap of three, skipped questions never repeat, a made-up
free-text interpretation is ignored, and a saved session loads back exactly.

To judge question quality against the real model, run it on a few real people (or fixture files you write)
and check:

- every question quotes something real about that person (the quote is checked, but is it *relevant*?);
- it is one short question a friend could ask, answerable in a few words;
- it is about something that actually matters to the decision, not trivia;
- the answer visibly moves a route, and `/why` shows the reason it was chosen;
- try to break it: answer in your own words, answer something untrue, press `s`, press `e`.

Model output varies a little from run to run (the routes it imagines are not identical), so judge
patterns across a few runs, not one.

## Limits, and what comes next

- **The judge is GPT standing in for Jev.** Its probabilities are the model's own estimates, made
  trustworthy by the receipts rule but not statistically calibrated. When TypeSafe's Jev is available
  it replaces `judge_route` / `judge_priorities` in `prompts.py` (typed values with calibrated
  probabilities); nothing else changes.
- **No live research yet.** Published statistics (Browserbase) are not used here. The repo's existing
  research step can feed real base rates into the outcomes later.
- **Two kinds of unknown.** Requirements and "what matters most". Trade-off unknowns beyond those
  (for example a specific risk tolerance) are not modelled yet.
- **Answers to requirements are treated as fact** (97%), since the person is the authority.
