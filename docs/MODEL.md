# How Hereafter's numbers are made (model 2.6)

Every possible event gets a base chance from the best available source, a small shift for your personality, and is then lived forward a thousand times together with everything it depends on. The probability shown is the share of those thousand lives in which it happened. It is a structured estimate, not a forecast.

This file is generated from `backend/app/model_card.py`, which also serves `GET /model`.

## The five steps

### 1. A base chance for each possible event

Over the event's own window of dates. Sourced: a published figure for the nearest studied group, found on the live web, accepted only if the figure literally appears in the quoted passage, then converted in code to the window (the arithmetic is kept on the evidence). Personal: your own record of commitments kept, used only when your log holds at least five. Estimated: no published figure was found, so only a verbal bin is known; the bin is a fixed numeric range, each simulated life draws its own value inside it, and the midpoint is reported as the base. The first step of every path is the choice itself, which simply happens. (A background of national life tables — friends' weddings, parents, money drift — exists but is switched off unless asked for: people found it noise.)

### 2. A shift for your personality

In log-odds: adjusted = logistic(logit(base) + sum of direction × beta × z × confidence), over at most two Big Five traits per event. z is your trait score in standard deviations and is shrunk by how much the estimate is trusted (an MBTI type is trusted little). Where a published, statistically significant effect exists for a matching life-course transition, that published beta is used. Otherwise only the DIRECTION is a judgement (made when the event is proposed) and the size is one fixed constant. No personality estimate means no shift at all.

### 3. What depends on what

A path is a causal story, checked in code. An event can come only AFTER others (not before they happen, or before their moment has passed), can REQUIRE others (never without them), and can be made likelier (×2), less likely (×0.5) or impossible (×0) by others. A base chance means: given that what it requires has happened. These rules act inside each simulated life as it unfolds, which is why the chance of a late event is lower than its base.

### 4. A thousand lives

Each life is sampled step by step with numpy from a seed fixed by your inputs, so the same question always gives the same answer. The probability shown for an event is the share of lives in which it happened by the horizon (for something that can recur: at least once). Lists are ordered by it. The life you read is the MODAL life: everything that happens in at least half of the lives happens, the rest does not, plus a typical number of the less-than-even things; it is the one simulated run closest to that, with the most typical timing. Each moment gets a date inside its own window, never before what it follows. The rare life is a run far from the modal one that still has at least three events in it. No language model takes part in this step, and a stored model re-runs with the language model switched off.

### 5. What the language model does, and does not

It proposes what could happen, names the nearest studied group to look up, names which traits bear on an event and in which direction, copies figures out of pages (checked in code), and writes the narrative around the sampled skeleton. It never supplies a probability or the size of any effect, and it never decides what happens.

### 6. Four measures, as change from now

Every path tracks health, joy (short-term happiness), fulfilment (the long-term kind) and money as a DIFFERENCE from where you are now — now is zero; there is no absolute score. When an event is proposed it is given an effect on each, an integer from −2 to +2 and zero for most: a judgement about what that moment means if it happens, never about whether it happens. Inside each simulated life the effects of what actually happened are added up step by step: joy is a pulse that fades within days; health persists and fades slowly; fulfilment and money stay. What is shown is the average of the thousand lives with the band that holds the middle four fifths of them, and at the end a mark from −−− to +++. Money is the one exception to judgement: where your own words or a researched source give a real figure (a salary, a rent, a loan), it runs through a separate ledger in currency from the day that moment happens, and is set against your income or net worth only if you chose to give them.

## Every constant

| Constant | Value | What it means |
|---|---|---|
| Verbal bins | “almost certainly” 0.93–0.99, “rare” 0.02–0.10, “sometimes” 0.15–0.35, “as often as not” 0.40–0.60, “usually” 0.70–0.90 | The numeric range behind each word when no published figure exists. Hand-set. |
| Assumed personality effect | 0.20 log-odds per SD | A small effect, about the size typically found between personality traits and life outcomes (r ≈ 0.1). The direction is a judgement; the size is fixed. |
| Published personality effects | data/personality_effects.csv, significant rows only | Used instead of the assumed size when an event is a marriage, divorce, birth, move, job change or death. |
| Loose-fit band | ±0.15 | When the studied group fits you poorly, each life draws the base from this band around the published figure. The figure itself is never adjusted. |
| Open-question widening | 0.08 per open question (at most two) | While a clarifying question is unanswered, every range on that path is stretched by this much. |
| Dependency multipliers | likelier ×2, less likely ×0.5, prevents ×0, requires = gate | How one event changes another's chance once it has happened. Hand-set. |
| Simulated lives | 1000 | Runs per path; probabilities are shares of these. |
| The life you read | modal life; extras weight 0.35 | The one simulated run closest to 'everything at least even happens, nothing else does', each event weighted by how far it is from a coin flip, held to the average number of less-than-even events; ties go to the most typical timing. Never an average of lives. |
| Horizons | big decisions 3 years, at most 5 unless you say otherwise | A decision is modelled over the stretch where it plays out. Long paths step weekly for the first month, monthly to the end of year one, then quarterly. |
| Background fit band | ±25% in Canada, ±50% elsewhere | Each life scales each national-average hazard by its own factor in this band. |
| Background | off by default (HEREAFTER_BACKGROUND=on); when on, at most about a quarter of visible events | National averages are weather, not plot. When on: long horizons only; marriage, children and buying a home appear only if your own words show they are wanted or already yours. |
| Effect scale | −2 … +2 per event and measure; 0 for most | A five-point judgement made when an event is proposed. Sourced only for money amounts that come from your words or a cited page. |
| How long an effect lasts | joy: half-life 10 days; health: half-life 2 years; fulfilment and money: no decay | Hand-set. A good night fades in days; what wears you down or builds you up lingers; meaning and money stay. |
| Band around a measure | 10th–90th percentile of the simulated lives | The low and high shown beside each average. |
| Marks | |change| ≥ 0.5, 1.5, 3 → one, two, three marks; “=” below the first | How the end-of-path change is summarised as − / = / +. |
| USD to CAD | 1.37 | One fixed conversion for US pay and prices. |
| National home price baseline | CAD 700,000 | Hand-set, approximate; a researched local price is compared with it. |
| Big or small | six months | A decision that plays out over six months or more is big; under that, small. Your own choice overrides it. |

## Limits

- Most base rates are estimates. When no published figure is found — which is most of the time — the number comes from a word and a hand-set range.
- A reference class is not you. A sourced figure describes a studied group that differs from you in stated ways; it is used as published, never tailored.
- Personality directions are judgements, and their size is one fixed assumed constant. They are not measured for you or for this event.
- Personality effects are small. With an MBTI type the estimate is trusted so little that shifts are often a percentage point or less.
- MBTI maps onto four of the Big Five only, through correlations checked against a secondary source; neuroticism is unknown from it.
- Several published effects rest on a single study, from the United States or Australia.
- The optional background tables are Canadian national averages, read from today's cross-section as if it were a future; they are off by default.
- What can happen on a path is itself a proposal: a plausible causal story, not an exhaustive one. Things nobody listed cannot happen in the simulation.
- Everything here is association, not cause. A shift does not mean your personality makes the event happen.
- Dependencies and their multipliers are hand-set and coarse.
- A thousand runs carry sampling noise of about one and a half percentage points around fifty percent.
- The four measures are not clinical and not financial advice. Their inputs are five-point judgements, so their size means 'more' or 'less', not an amount of health or happiness; only the money ledger is in real units, and only for the figures that are known.
- The narration is fiction written around a sampled skeleton. Its details are invented; only the events, dates and cited facts come from the model.
