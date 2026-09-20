// Things the client can work out from a BranchView on its own. Used to fill in newer fields when
// an older backend leaves them out, and by the offline sample.

import { isByYear, stepDate, words } from './format'
import type { Aspect, Branch, BranchView, BranchYear, Chapter, CompareResponse, Outlook, Scenario, StateVector } from './types'

export const BACKGROUND_ASPECTS: Aspect[] = ['city', 'employment', 'income_band', 'housing', 'relationship', 'children', 'alive']

const BACKGROUND_LABEL: Record<string, string> = {
  city: 'where you live',
  employment: 'work',
  income_band: 'money',
  housing: 'home',
  relationship: 'partner',
  children: 'children',
  alive: 'still here',
}

/** What an outlook row is called: the option's own event label, else a background aspect, else the key in words. */
export function aspectLabel(aspect: Aspect, branches: Branch[]): string {
  for (const b of branches) {
    const found = b.model.events.find((e) => e.key === aspect)
    if (found) return found.label
  }
  return BACKGROUND_LABEL[aspect] ?? words(aspect)
}

const COUNT = ['none', 'one', 'two', 'three or more']

function backgroundValue(state: StateVector, aspect: Aspect): string {
  switch (aspect) {
    case 'city':
      return state.city
    case 'employment':
      return words(state.employment)
    case 'income_band':
      return words(state.income_band)
    case 'housing':
      return words(state.housing)
    case 'relationship':
      return words(state.relationship_status)
    case 'children':
      return COUNT[Math.min(state.children, 3)]
    default:
      return state.alive ? 'yes' : 'no'
  }
}

/** When a step arrives without an outlook, the background aspects borrow its overall solidity. */
export function outlookFor(step: Pick<BranchYear, 'state' | 'solidity'>): Outlook {
  const out: Outlook = {}
  for (const aspect of BACKGROUND_ASPECTS) out[aspect] = { share: step.solidity, words: "", probability: step.solidity, value: backgroundValue(step.state, aspect) }
  return out
}

export function normaliseYears(years: BranchYear[]): BranchYear[] {
  return years.map((y) => ({
    ...y,
    at: y.at ?? `${y.year}-12-31`,
    label: y.label ?? String(y.year),
    outlook: y.outlook && Object.keys(y.outlook).length ? y.outlook : outlookFor(y),
  }))
}

export function normaliseView(view: BranchView): BranchView {
  const b = view.branch as Partial<Branch> & Branch
  return {
    branch: {
      ...b,
      status: b.status === 'expired' ? 'stale' : b.status,
      scenario_id: b.scenario_id ?? null,
      option_id: b.option_id ?? null,
      commits: (b.commits ?? []).map((c) => ({ ...c, at: c.at ?? `${c.year}-01-01` })),
      research: b.research ?? 'none',
      revision: b.revision ?? 0,
      model: b.model ?? { events: [] },
      forming: b.forming ?? false,
    },
    years: normaliseYears(view.years ?? []),
  }
}

/** A life decision, or something day to day. The backend says; until it does, the horizon decides. */
export const scaleOf = (s: Pick<Scenario, 'scale' | 'horizon'>): 'big' | 'small' =>
  s.scale ?? (s.horizon?.unit === 'years' || (s.horizon?.unit === 'months' && s.horizon.count >= 6) ? 'big' : 'small')

export const normaliseScenario = (s: Scenario): Scenario => ({ ...s, scale: scaleOf(s), horizon: s.horizon ?? { unit: 'years', count: 40 }, questions: s.questions ?? [], assuming_branch_id: s.assuming_branch_id ?? null })

const UNIT_DAYS = { days: 1, weeks: 7, months: 30.44, years: 365.25 } as const
const GHOST_STEPS = 6

/** A branch that is still forming has no steps yet. Both views sketch it as a faint guide line over the
 *  decision's horizon; these placeholder steps are what they draw, and they are replaced as data lands. */
export function withGuides(views: BranchView[], scenarios: Scenario[], now: string, state: StateVector): BranchView[] {
  return views.map((v) => {
    if (v.years.length > 0) return v.branch.forming ? { ...v, branch: { ...v.branch, forming: false } } : v
    const horizon = scenarios.find((s) => s.id === v.branch.scenario_id)?.horizon ?? { unit: 'years' as const, count: 10 }
    const span = Math.max(1, horizon.count * UNIT_DAYS[horizon.unit])
    const start = new Date(now).getTime()
    const years: BranchYear[] = Array.from({ length: GHOST_STEPS }, (_, i) => {
      const at = new Date(start + ((span * (i + 1)) / GHOST_STEPS) * 86_400_000).toISOString().slice(0, 10)
      return { year: +at.slice(0, 4), at, label: '', solidity: 0.6, state, events: [], outlook: {} }
    })
    return { branch: { ...v.branch, forming: true }, years }
  })
}

/** The deep-background state, in one line of words. Shown small, and only on long horizons. */
export function stateWords(s: StateVector): string {
  if (!s.alive) return 'gone'
  const parts = [s.city, words(s.housing), words(s.relationship_status), words(s.employment)]
  if (s.children > 0) parts.push(s.children === 1 ? 'one child' : `${COUNT[Math.min(s.children, 3)]} children`)
  return parts.join(' · ')
}

export function compareViews(views: BranchView[]): CompareResponse {
  const steps = Math.min(...views.map((v) => v.years.length))
  const long = steps > 12
  const picks: number[] = []
  if (long) for (let i = 4; i < steps; i += 5) picks.push(i)
  else for (let i = 0; i < steps; i += Math.max(1, Math.floor(steps / 5))) picks.push(i)
  const checkpoints = picks.map((i) => {
    const at = views.map((v) => v.years[i])
    const keys = [...new Set(at.flatMap((y) => Object.keys(y.outlook)))].filter((k) => k !== 'alive' || long)
    const rows = keys.map((aspect) => {
      const values = at.map((y, n) => {
        const entry = y.outlook[aspect] ?? { value: '—', words: '', share: 0 }
        return { branch_id: views[n].branch.id, value: entry.value, words: entry.words, share: entry.share, probability: entry.probability }
      })
      return { aspect, differs: new Set(values.map((v) => v.value)).size > 1, values }
    })
    return { year: at[0].year, age: at[0].state.age, label: stepDate(at[0].at, isByYear(views[0].years)), rows }
  })
  const distinctive = views.flatMap((v) => {
    const others = views.filter((o) => o !== v).flatMap((o) => o.branch.model.events.map((e) => e.key))
    return v.branch.model.events.filter((e) => !others.includes(e.key)).slice(0, 3).map((e) => ({ branch_id: v.branch.id, label: e.label, words: e.words, basis: e.basis, probability: e.probability }))
  })
  return { branches: views.map((v) => v.branch), checkpoints, distinctive }
}

/** Chapter boundaries over a branch's steps: a short opening, then spans of five. */
export function spanFor(years: BranchYear[], at: string): [number, number] {
  const i = Math.max(0, years.findIndex((y) => y.at >= at))
  if (i < 2) return [0, Math.min(1, years.length - 1)]
  const from = 2 + Math.floor((i - 2) / 5) * 5
  return [from, Math.min(from + 4, years.length - 1)]
}

/** A chapter with no prose: the structured skeleton, which is also what LLM-off looks like. */
export function plainChapter(view: BranchView, at: string, years: BranchYear[] = view.years): Chapter {
  const [a, b] = spanFor(years, at)
  const steps = years.slice(a, b + 1)
  const byYear = isByYear(years)
  const when = (y: BranchYear) => stepDate(y.at, byYear)
  const paragraphs = steps.filter((y) => y.events.length > 0).map((y) => ({ text: `${sentenceCase(when(y))}. ${y.events.map((e) => e.text).join('; ')}.`, evidence_ids: [] as string[] }))
  if (paragraphs.length === 0) paragraphs.push({ text: 'Nothing the simulation marks as an event. The days go on.', evidence_ids: [] })
  return {
    branch_id: view.branch.id,
    revision: view.branch.revision,
    from_year: steps[0].year,
    to_year: steps[steps.length - 1].year,
    from_at: steps[0].at,
    to_at: steps[steps.length - 1].at,
    title: steps.length === 1 || when(steps[0]) === when(steps[steps.length - 1]) ? sentenceCase(when(steps[0])) : `${sentenceCase(when(steps[0]))} to ${when(steps[steps.length - 1])}`,
    status: 'ready',
    paragraphs,
  }
}

export function normaliseChapter(c: Chapter, years: BranchYear[]): Chapter {
  if (c.from_at && c.to_at) return c
  const inside = years.filter((y) => y.year >= c.from_year && y.year <= c.to_year)
  return { ...c, from_at: inside[0]?.at ?? `${c.from_year}-01-01`, to_at: inside[inside.length - 1]?.at ?? `${c.to_year}-12-31` }
}

const sentenceCase = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s)
