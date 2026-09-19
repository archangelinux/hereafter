// Geometry of the line. Time runs upward. Main is lane 0. The scenario in focus peels away to
// the right; every other scenario's branches sit to the left, so many small forks and a few long
// ones can share one main without tangling. Pure functions: drawing and hit-testing agree.
//
// Below now the scale is years. Above now it adapts to the focused scenario's horizon (a night,
// weeks, months, decades), and each step keeps a minimum length so "tonight" is never a speck.

import { scaleOf } from '../derive'
import { belongsOnLine, isByYear, stepDate, yearOf } from '../format'
import type { Basis, BranchView, BranchYear, Horizon, LifeEvent, Scenario } from '../types'

export const PAST_PX_PER_YEAR = 58
const STEP_PX = 58 // a step of the focused scenario, on average
const MIN_STEP_PX = 30
const MIN_BRANCH_PX = 64 // a small decision is still a visible flourish
const CLOSED_PX = 460 // how much of a road not taken stays drawn
const STALE_PX = 84
const OFFSCREEN_PX = 1700 // other scenarios are not drawn beyond this above now

export interface Pt {
  x: number
  y: number
}

export interface Segment {
  index: number
  d: string
  solidity: number
  hidden: boolean
}

export interface LaneNode {
  id: string
  kind: 'event' | 'commit'
  step: number
  at: Pt
  normal: Pt
  label: string
  caption: string
  basis: Basis
  event?: LifeEvent
  /** step zero: the choice itself, which is what a merge records */
  head?: boolean
}

export interface Lane {
  view: BranchView
  scale: 'big' | 'small'
  focus: boolean
  side: 1 | -1
  forkY: number
  endS: number
  rejoinS: number | null
  segments: Segment[]
  hit: string
  nodes: LaneNode[]
  labelAt: Pt
  endAt: Pt
  endNormal: Pt
  /** position at s: 0 is the fork, i + 1 is the end of step i */
  pos: (s: number) => Pt
  /** the lane's x at a given height, so a decision branched off this path can fork from it */
  xAtY: (y: number) => number
}

export interface RareLane {
  d: string
  nodes: LaneNode[]
  labelAt: Pt
}

const UNIT_YEARS: Record<Horizon['unit'], number> = { days: 1 / 365.25, weeks: 7 / 365.25, months: 1 / 12, years: 1 }

const smooth = (u: number) => {
  const c = Math.max(0, Math.min(1, u))
  return c * c * c * (c * (c * 6 - 15) + 10)
}

const pathThrough = (points: Pt[]) => points.map((p, i) => `${i ? 'L' : 'M'}${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ')

function sample(pos: (s: number) => Pt, from: number, to: number): Pt[] {
  const len = Math.abs(pos(to).y - pos(from).y)
  const n = Math.max(2, Math.min(260, Math.ceil(len / 9)))
  return Array.from({ length: n + 1 }, (_, i) => pos(from + ((to - from) * i) / n))
}

function normalAt(pos: (s: number) => Pt, s: number): Pt {
  const a = pos(s - 0.04)
  const b = pos(s + 0.04)
  const len = Math.hypot(b.x - a.x, b.y - a.y) || 1
  return { x: -(b.y - a.y) / len, y: (b.x - a.x) / len }
}

export interface LineLayout {
  lanes: Lane[]
  now: number
  pastFrom: number
  top: number // the highest y drawn (most negative)
  gap: number
  yAt: (t: number) => number
  focusHorizon: Horizon | null
  projected: string | null
  /** one per decision: a large node on main for a life decision, a small one for a day-to-day choice */
  forks: { x: number; y: number; scale: 'big' | 'small'; id: string; collapsed: boolean; label: string }[]
  /** spans where a merged life decision turned main itself aside: [from y, to y] */
  turns: [number, number][]
}

export function layoutLine(opts: { now: string; events: LifeEvent[]; views: BranchView[]; scenarios: Scenario[]; focusId: string | null; width: number }): LineLayout {
  const now = yearOf(opts.now)
  const scenarios = [...opts.scenarios].sort((a, b) => a.created_at.localeCompare(b.created_at))
  const focus = scenarios.find((s) => s.id === opts.focusId) ?? scenarios[scenarios.length - 1] ?? null
  const byId = new Map(opts.views.map((v) => [v.branch.id, v]))

  // the future's scale follows the focused scenario: its whole horizon is about STEP_PX per step
  const focusSteps = focus ? Math.max(...focus.branch_ids.map((id) => byId.get(id)?.years.length ?? 0), 1) : 40
  const focusSpan = focus ? Math.max(focus.horizon.count * UNIT_YEARS[focus.horizon.unit], 1 / 365.25) : 40
  const futurePxPerYear = Math.max(PAST_PX_PER_YEAR, (focusSteps * STEP_PX) / focusSpan)
  const yAt = (t: number) => (t <= now ? (now - t) * PAST_PX_PER_YEAR : -(t - now) * futurePxPerYear)

  // a decision made inside another branch brings that branch along as context, on the right
  const contextId = focus?.assuming_branch_id ?? null
  const rightCount = (focus ? focus.branch_ids.filter((id) => byId.get(id)?.branch.status !== 'merged').length : 0) + (contextId ? 1 : 0)
  const gap = Math.max(92, Math.min(164, (opts.width * 0.6) / (rightCount + 0.5)))

  const lanes: Lane[] = []
  const forks: LineLayout['forks'] = []
  const turns: [number, number][] = []
  let leftCount = 0
  let projected: string | null = null

  for (const scenario of scenarios) {
    const isFocus = scenario === focus
    const scale = scaleOf(scenario)
    const small = scale === 'small'
    const anyOpen = scenario.branch_ids.some((id) => byId.get(id)?.branch.status === 'open')
    let rightLane = 0
    scenario.branch_ids.forEach((id, i) => {
      const view = byId.get(id)
      if (!view || view.years.length === 0) return
      const status = view.branch.status
      const merged = status === 'merged'
      const isContext = id === contextId
      const parent = scenario.assuming_branch_id ? (lanes.find((l) => l.view.branch.id === scenario.assuming_branch_id) ?? null) : null
      const side: 1 | -1 = parent ? parent.side : isFocus || isContext ? 1 : -1
      const laneX = merged ? 0 : parent ? ++rightLane * (isFocus ? gap * 0.82 : 40) * side : isFocus || isContext ? ++rightLane * gap * (small ? 0.62 : 1) : -(1 + (leftCount++ % 4)) * (small ? 34 : 64)
      const fork = Math.min(yearOf(view.branch.forked_at), now)
      // inside another life: leave from a little way up that branch, not from main
      const from = parent ? parent.pos(Math.min(parent.endS, 0.9)) : null
      const forkY = from ? from.y : yAt(fork)
      if (!forks.some((f) => f.id === scenario.id)) forks.push({ id: scenario.id, x: from ? from.x : 0, y: forkY, scale, collapsed: false, label: scenario.situation })

      // knots: the fork, then the end of each step, each at least MIN_STEP_PX beyond the last
      const knots = [forkY]
      for (const step of view.years) knots.push(Math.min(yAt(yearOf(step.at)), knots[knots.length - 1] - (isFocus ? MIN_STEP_PX : 3)))
      const natural = forkY - knots[knots.length - 1]
      if (natural < MIN_BRANCH_PX) for (let k = 1; k < knots.length; k++) knots[k] = forkY - (MIN_BRANCH_PX * k) / (knots.length - 1)
      const yOfS = (s: number) => {
        const c = Math.max(0, Math.min(knots.length - 1, s))
        const k = Math.min(knots.length - 2, Math.floor(c))
        return knots[k] + (knots[k + 1] - knots[k]) * (c - k)
      }
      const sWhere = (px: number) => {
        const k = knots.findIndex((y) => forkY - y >= px)
        if (k <= 0) return knots.length - 1
        return k - 1 + (px - (forkY - knots[k - 1])) / (knots[k - 1] - knots[k])
      }

      const total = knots.length - 1
      let endS = total
      let rejoinS: number | null = null
      if (merged) {
        const decision = opts.events.find((e) => e.event_type === 'decision' && e.payload?.from_branch === id)
        const loop = Math.max(small ? 40 : 110, decision ? forkY - yAt(yearOf(decision.date)) : 0)
        rejoinS = Math.min(total, Math.max(0.35, sWhere(loop) * 0.25)) // only the first step, the choice, is drawn as main
        const continues = isFocus && !anyOpen
        if (continues) projected = id
        endS = continues ? total : Math.min(total, sWhere(small ? 44 : 120))
        // a life decision turns main itself along the chosen lane; a small one is only a handle on it
      } else if (status === 'stale') endS = sWhere(small ? 36 : STALE_PX)
      else if (status === 'faded') endS = sWhere(small ? 44 : CLOSED_PX)
      if (!isFocus) endS = Math.min(endS, sWhere(Math.max(MIN_BRANCH_PX, forkY + OFFSCREEN_PX)))

      const phase = (i + 1) * 1.7 + (isFocus ? 0 : 2.3)
      const pos = (s: number): Pt => {
        const y = yOfS(s)
        const d = forkY - y
        // merged: the choice itself is on main, so the path runs straight on from it, as a projection
        if (merged) return { x: 0, y }
        const meander = Math.sin(d / 120 + phase) * 9 * smooth(d / 260)
        const base = parent ? parent.xAtY(y) : 0
        return { x: base + laneX * smooth(d / (isFocus || isContext ? 150 : 90)) + meander, y }
      }
      const xAtY = (y: number) => {
        let lo = 0
        let hi = total
        for (let k = 0; k < 22; k++) {
          const mid = (lo + hi) / 2
          if (yOfS(mid) > y) lo = mid
          else hi = mid
        }
        return pos(lo).x
      }

      const segments: Segment[] = view.years.map((step, index) => {
        const to = Math.min(index + 1, Math.max(endS, index + 0.001))
        const certain = merged && rejoinS !== null && index + 1 <= rejoinS
        return { index, solidity: certain ? 1 : step.solidity, hidden: index >= endS, d: pathThrough(sample(pos, index, index >= endS ? index + 1 : to)) }
      })

      const byYear = isByYear(view.years)
      const nodes: LaneNode[] = []
      view.years.forEach((step, index) => {
        step.events.forEach((e, n) => {
          const s = index + (0.35 + (0.5 * (n + 1)) / (step.events.length + 1))
          if (s > endS) return
          nodes.push({ id: e.id, kind: 'event', step: index, at: pos(s), normal: normalAt(pos, s), label: e.text, caption: stepDate(step.at, byYear), basis: basisOf(e), event: e, head: !!(e.head ?? e.payload?.head) })
        })
      })
      for (const c of view.branch.commits) {
        const index = Math.max(0, view.years.findIndex((y) => y.at >= c.at || y.year >= c.year))
        const s = index + 0.12
        if (s <= endS) nodes.push({ id: c.id, kind: 'commit', step: index, at: pos(s), normal: normalAt(pos, s), label: c.message, caption: stepDate(view.years[index].at, byYear), basis: 'background' })
      }

      const labelS = merged ? (rejoinS ?? 1) / 2 : Math.min(endS - 0.1, sWhere(isFocus ? 150 + rightLane * 58 : 40))
      lanes.push({
        view, scale, focus: isFocus, side, forkY, endS, rejoinS, segments, nodes, pos, xAtY,
        hit: pathThrough(sample(pos, 0, endS)),
        labelAt: pos(Math.max(0.2, labelS)),
        endAt: pos(endS),
        endNormal: normalAt(pos, endS - 0.05),
      })
    })
  }

  // every decision not in focus is a single circle on main, at the day it was made
  for (const scenario of scenarios) {
    if (forks.some((f) => f.id === scenario.id)) continue
    let y = yAt(Math.min(yearOf(scenario.created_at), now))
    while (forks.some((f) => f.x === 0 && Math.abs(f.y - y) < 18)) y += 18
    forks.push({ id: scenario.id, x: 0, y, scale: scaleOf(scenario), collapsed: true, label: scenario.situation })
  }

  const dated = opts.events.filter(belongsOnLine)
  const firstEvent = dated.length ? Math.min(...dated.map((e) => yearOf(e.date))) : now - 4
  const top = Math.min(-600, ...lanes.map((l) => l.endAt.y))
  return { lanes, now, pastFrom: Math.min(firstEvent, now - 3) - 0.6, top, gap, yAt, focusHorizon: focus?.horizon ?? null, projected, forks, turns }
}

/** The rarest life here: the faintest offshoot from its branch, drawn beside it. */
export function layoutRare(lane: Lane, years: BranchYear[]): RareLane {
  const pos = (s: number): Pt => {
    const p = lane.pos(s)
    const d = lane.forkY - p.y
    return { x: p.x + lane.side * (52 * smooth(d / 120) + Math.sin(d / 47) * 6), y: p.y }
  }
  const total = Math.min(years.length, lane.endS)
  const byYear = isByYear(years)
  const nodes: LaneNode[] = []
  years.slice(0, Math.ceil(total)).forEach((step, index) =>
    step.events.forEach((e, n) => {
      const s = index + (0.35 + (0.5 * (n + 1)) / (step.events.length + 1))
      nodes.push({ id: e.id, kind: 'event', step: index, at: pos(s), normal: normalAt(pos, s), label: e.text, caption: stepDate(step.at, byYear), basis: basisOf(e), event: e })
    }),
  )
  return { d: pathThrough(sample(pos, 0.25, total)), nodes, labelAt: pos(Math.min(total, 2.6)) }
}

export function basisOf(e: LifeEvent): Basis {
  const b = e.payload?.basis
  return b === 'sourced' || b === 'estimated' ? b : 'background'
}

/** Line quality from how many of the thousand lives agree. The engine's range is about 0.6 to 1. */
export function inkFor(solidity: number): { width: number; dash?: string; opacity: number; wash: boolean } {
  const t = Math.max(0, Math.min(1, (solidity - 0.6) / 0.38))
  if (t > 0.72) return { width: 3.4, opacity: 1, wash: false }
  if (t > 0.5) return { width: 2.4, opacity: 0.95, wash: false }
  if (t > 0.3) return { width: 2, dash: '9 6', opacity: 0.9, wash: false }
  if (t > 0.12) return { width: 1.8, dash: '1.5 7', opacity: 0.85, wash: false }
  return { width: 1.4, dash: '1 10', opacity: 0.5, wash: true }
}
