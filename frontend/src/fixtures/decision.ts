// The decision maths behind the demo: a Bayesian update of one number, then expected value per action.
// Pure functions, no React and no dates, so it can be tested on its own (scripts/decision.test.mts).
//
//   P(she is interested) starts at a prior and is multiplied, in odds form, by one likelihood ratio per
//   piece of evidence. Each action pays off differently if she is interested or not; the expected value is
//   the payoff in each state weighted by the posterior.
//
// Every number is tagged: "published" (read in the source, with the sentence) or "assumption" (a demo input).

export type Action = 'talk' | 'ask' | 'follow' | 'bury'
export const ACTIONS: Action[] = ['talk', 'ask', 'follow', 'bury']

export type Kind = 'published' | 'assumption'

export interface Source {
  id: string
  kind: Kind
  /** what this supports, in plain words */
  claim: string
  /** the source, as a person would cite it */
  cite: string
  url: string
  /** the sentence or figure as the source writes it; only present when it was read */
  quote?: string
}

/** Utility points, from the person's own point of view (editable inputs, not measurements). */
export const PAYOFF: Record<Action, { interested: number; not: number }> = {
  talk: { interested: 70, not: -5 }, // a chat opens the door and costs almost nothing if she isn't interested
  ask: { interested: 100, not: -30 }, // a direct invitation: a date if she is, a real sting if not
  follow: { interested: -30, not: -60 },
  bury: { interested: 5, not: 5 },
}

export const LABEL: Record<Action, string> = { talk: 'Talk to her', ask: 'Ask her out', follow: 'Follow her around', bury: 'Bury it and forget about it' }

/** P(interested) before any evidence: an assumption, far below the "about half" that self-selected speed daters say yes to. */
export const PRIOR = 0.25

/** If she is interested she almost always talks back; if not, a civil reply is still the usual response to a direct hello. */
export const RESPONDS = { interested: 0.95, not: 0.6 }

/** How often she says yes when asked out: usually if she is interested, rarely if not. */
export const SAYS_YES = { interested: 0.85, not: 0.05 }

export interface Evidence {
  id: string
  label: string
  /** where this fact came from: an account, or the person's own answer */
  from: string
  /** likelihood ratio: how many times more likely this evidence is if she is interested than if she is not */
  lr: number
  kind: Kind
  /** one plain line on why the ratio is what it is */
  why: string
  /** the same in a few words, for a summary line (optional) */
  short?: string
}

export const odds = (p: number) => p / (1 - p)
export const prob = (o: number) => o / (1 + o)

/** Bayes' rule in odds form. */
export function posterior(prior: number, lrs: number[]): number {
  return prob(lrs.reduce((o, lr) => o * lr, odds(prior)))
}

export function ev(action: Action, p: number): number {
  const f = PAYOFF[action]
  return p * f.interested + (1 - p) * f.not
}

/** Standard deviation of the payoff: how much it swings between the two worlds. Zero for a sure thing. */
export function sd(action: Action, p: number): number {
  const f = PAYOFF[action]
  return Math.abs(f.interested - f.not) * Math.sqrt(p * (1 - p))
}

/** The chance an action ends better than where you started (payoff above zero). Read off the payoff table. */
export function chanceOfGain(action: Action, p: number): number {
  const f = PAYOFF[action]
  return (f.interested > 0 ? p : 0) + (f.not > 0 ? 1 - p : 0)
}

/** The P(interested) at which two actions have the same expected value; null if they never do. */
export function breakEven(a: Action, b: Action): number | null {
  const fa = PAYOFF[a]
  const fb = PAYOFF[b]
  const slope = fa.interested - fa.not - (fb.interested - fb.not)
  if (slope === 0) return null
  const p = (fb.not - fa.not) / slope
  return p >= 0 && p <= 1 ? p : null
}

/** P(she at least talks to you if you go over). */
export const respondsWell = (p: number) => p * RESPONDS.interested + (1 - p) * RESPONDS.not

/** P(she says yes if you ask her out). */
export const saysYesTo = (p: number) => p * SAYS_YES.interested + (1 - p) * SAYS_YES.not

export interface Analysis {
  p: number
  prior: number
  steps: Evidence[]
  actions: { action: Action; label: string; ev: number; sd: number; gain: number }[]
  recommended: Action
  /** the P(interested) above which talking beats burying it */
  threshold: number
  /** where each choice starts to pay: talking over doing nothing, asking over doing nothing, asking over just talking */
  thresholds: { talk: number; ask: number; askOverTalk: number }
  responds: number
  saysYes: number
  /** how far P(interested) is from the threshold, in points: what could still change the answer */
  margin: number
}

export function analyse(steps: Evidence[], prior = PRIOR): Analysis {
  const p = posterior(prior, steps.map((s) => s.lr))
  const actions = ACTIONS.map((action) => ({ action, label: LABEL[action], ev: ev(action, p), sd: sd(action, p), gain: chanceOfGain(action, p) }))
  const best = [...actions].sort((a, b) => b.ev - a.ev)[0]
  const threshold = breakEven('talk', 'bury') ?? 0
  const thresholds = { talk: threshold, ask: breakEven('ask', 'bury') ?? 0, askOverTalk: breakEven('ask', 'talk') ?? 0 }
  return { p, prior, steps, actions, recommended: best.action, threshold, thresholds, responds: respondsWell(p), saysYes: saysYesTo(p), margin: p - threshold }
}
