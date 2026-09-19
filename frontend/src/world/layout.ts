// Where everything in the world lies. Pure functions; the scene only draws what this returns.
//
// Main is one strong, flowing band from the past to now. Circles appear on it only where a decision
// is made, and the two kinds of decision are told apart at a glance by thickness, circle and angle:
//
//   BIG (a life decision): a large round plaza. Its options leave in entirely different directions,
//   fanned wide across the forward half of the sky, each a full-width band. When one is chosen, MAIN
//   ITSELF turns and carries on that way; the others stay where they were, grey, sunk, ending.
//
//   SMALL (day to day): a small circle. Its options are thin, short offshoots that leave at a shallow
//   angle and keep close to main. A chosen one loops back into main a little further on, like a thin
//   cup handle; the others stay as short grey stubs. Main does not turn. Consecutive small decisions
//   take alternate sides. Nothing ever crosses.
//
// A decision made inside a branch forks from that branch by the same rules.
// Every lane is a centreline sampled every DS of arc length from its fork (d = 0); its steps are
// laid along it by their real dates, gently compressed so that dense early weeks do not bunch up
// (the first month of a three-year path takes about a fifth of it): `dOfS` maps s (0 = the fork,
// i + 1 = the end of step i) to d.

import { dayLabel, yearOf } from '../format'
import type { Basis, BranchStatus, BranchView, BranchYear, LifeEvent, Scenario } from '../types'
import { accents } from './palette'

export const DS = 0.25
const PAST_UNITS = 1.35 // world units per year of past
const AHEAD = 40
const DEG = Math.PI / 180
export const MAIN_WIDTH = 1.15
const BIG_R = 2.45 // a plaza: between four and five path-widths across
const SMALL_R = 0.95 // small, but with room on its rim for each option to leave from its own place
const QUIET_BIG_R = 1.55 // a life decision that is not the one in focus: still plainly the larger kind of circle
const HANDLE = 3.4 // how far along main a small option's handle reaches

export interface Sample {
  x: number
  y: number
  z: number
}
type Point = Sample & { heading: number }
type Axis = (D: number) => Point

export interface NodeSpec {
  id: string
  kind: 'event' | 'commit'
  step: number
  d: number
  label: string
  caption: string
  basis: Basis | 'personal'
  domain: string
  event?: LifeEvent
}

export interface LaneSpec {
  id: string
  view: BranchView
  status: BranchStatus
  big: boolean
  accent: string
  width: number
  steps: number
  stepLen: number // the average; steps are NOT evenly spaced, use stepEnds / dOfS / stepAtD
  stepEnds: number[] // d at the end of each step
  fullLen: number
  /** the band is drawn between fromD and drawLen once settled */
  fromD: number
  drawLen: number
  /** merged only: how far from the fork it has become main's own stone */
  stoneLen: number
  breaks: boolean // stale: the end has visibly come away
  side: 1 | -1
  small: boolean
  atNow: boolean // an option of the decision the figure is standing on: its name is always shown
  example: boolean // a sample path shown to a first-time visitor: drawn the same, a touch paler
  samples: Sample[]
  built: Float32Array // per sample, 0..1: how BUILT the band is there
  fade: Float32Array // per sample, 1..0: past where the stone gives out, its drawn edges soon go to mist
  tagD: number
  /** the end of the first step: what a merge would commit (HEAD) */
  headD: number
  nodes: NodeSpec[]
  note: string
}

export interface Plaza {
  id: string
  big: boolean
  at: Point
  r: number
  label: string
  decided: boolean
  onMain: boolean
  collapsed: boolean // only its circle is drawn: a quiet mark on main until it is focused
  branchIds: string[]
}

export interface MainSpec {
  samples: Sample[] // from the earliest past to now; the last sample is now
  nodes: (NodeSpec & { at: Point })[]
  seeds: { id: string; at: Sample; label: string; caption: string }[]
}

export interface WorldLayout {
  now: number
  main: MainSpec
  lanes: LaneSpec[]
  plazas: Plaza[]
  frame: Sample[] // what the overview must keep in view
}

const clamp01 = (v: number) => Math.max(0, Math.min(1, v))
const ease = (v: number) => {
  const c = clamp01(v)
  return c * c * c * (c * (c * 6 - 15) + 10)
}
const clip = (s: string, n: number) => (s.length > n ? s.slice(0, n - 1).trimEnd() + '…' : s)

/**
 * How BUILT a stretch is, from how many of the simulated lives agree. The engine's range is about
 * 0.6 to 1, so that band is spread across the whole progression from stone to mist.
 * This is the only place the score is read, and it only ever becomes masonry.
 */
export function builtFrom(solidity: number): number {
  const t = clamp01((solidity - 0.58) / (0.95 - 0.58))
  return t * t * (3 - 2 * t)
}

export function basisOf(e: LifeEvent): Basis | 'personal' {
  const b = e.payload?.basis
  return b === 'sourced' || b === 'estimated' || b === 'personal' ? b : 'background'
}

export function hash01(s: string): number {
  let h = 2166136261
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619)
  h ^= h >>> 16
  h = Math.imul(h, 0x85ebca6b)
  h ^= h >>> 13
  h = Math.imul(h, 0xc2b2ae35)
  h ^= h >>> 16
  return (h >>> 0) / 4294967296
}

/** Position and heading at arc length d along a sampled centreline. Heading 0 runs toward -z; positive turns toward +x. */
export function along(samples: Sample[], d: number): Point {
  const f = Math.max(0, Math.min(samples.length - 1, d / DS))
  const i = Math.min(Math.max(0, samples.length - 2), Math.floor(f))
  const k = f - i
  const a = samples[i]
  const b = samples[Math.min(samples.length - 1, i + 1)]
  const p = samples[Math.max(0, i - 1)]
  const n = samples[Math.min(samples.length - 1, i + 2)]
  return { x: a.x + (b.x - a.x) * k, y: a.y + (b.y - a.y) * k, z: a.z + (b.z - a.z) * k, heading: Math.atan2(n.x - p.x, -(n.z - p.z)) }
}

/** s (0 = the fork, i + 1 = the end of step i) → arc length along the lane */
export function dOfS(lane: Pick<LaneSpec, 'stepEnds'>, s: number): number {
  const ends = lane.stepEnds
  const c = Math.max(0, Math.min(ends.length, s))
  const i = Math.min(ends.length - 1, Math.floor(c))
  const a = i === 0 ? 0 : ends[i - 1]
  return a + (ends[i] - a) * (c - i)
}

/** which step an arc length falls in */
export function stepAtD(lane: Pick<LaneSpec, 'stepEnds'>, d: number): number {
  const i = lane.stepEnds.findIndex((e) => d <= e)
  return i < 0 ? lane.stepEnds.length - 1 : i
}

const sOfD = (ends: number[], d: number) => {
  let k = ends.findIndex((e) => d <= e)
  if (k < 0) k = ends.length - 1
  const a = k === 0 ? 0 : ends[k - 1]
  return k + clamp01((d - a) / Math.max(1e-6, ends[k] - a))
}

const isCollapsed = (s: Scenario) => (s as { collapsed?: boolean }).collapsed === true
const isHead = (e: LifeEvent) => (e as { head?: boolean }).head === true || e.payload?.head === true

/** A life decision or a day-to-day one. Told by the scenario if it says; otherwise by how far it looks. */
export function isBig(s: Scenario): boolean {
  const scale = (s as { scale?: string }).scale
  if (scale === 'big' || scale === 'small') return scale === 'big'
  const h = s.horizon
  return h.unit === 'years' || (h.unit === 'months' && h.count >= 6) || (h.unit === 'weeks' && h.count >= 26)
}

/** Options of a big decision fan across the whole forward half of the sky. */
function bigAngles(n: number): number[] {
  if (n <= 1) return [36 * DEG]
  const gap = Math.min(62, 180 / (n - 1))
  return Array.from({ length: n }, (_, i) => (i - (n - 1) / 2) * gap * DEG)
}

const STATUS_NOTE: Record<string, string> = { open: '', merged: 'merged into main', faded: 'a road not taken', stale: 'stale', expired: 'stale' }

export function layoutWorld(opts: { now: string; events: LifeEvent[]; views: BranchView[]; scenarios: Scenario[] }): WorldLayout {
  const now = yearOf(opts.now)
  const byId = new Map(opts.views.map((v) => [v.branch.id, v]))
  const scenarios = [...opts.scenarios].sort((a, b) => a.created_at.localeCompare(b.created_at))
  const viewsOf = (s: Scenario) => s.branch_ids.map((id) => byId.get(id)).filter((v): v is BranchView => !!v && v.years.length > 0)
  const isOpen = (s: Scenario) => viewsOf(s).some((v) => v.branch.status === 'open')
  const chosenIndex = (s: Scenario) => viewsOf(s).findIndex((v) => v.branch.status === 'merged')
  const fromMain = scenarios.filter((s) => !s.assuming_branch_id && viewsOf(s).length > 0)
  const mainEvents = opts.events.filter((e) => e.branch_id === 'main')

  // ---- the junction at now: the newest open life decision, if there is one
  // An OPEN decision is, by definition, at now. The one in focus (not collapsed; a life decision first,
  // else the newest) IS the now platform: the figure stands on its circle and its paths leave forward
  // from under the figure. Other open decisions sit as circles immediately behind now, newest nearest.
  // Only DECIDED ones sit back in the past, at the date they were decided.
  const openFocus = [...fromMain].reverse().filter((s) => isOpen(s) && !isCollapsed(s))
  const primary = openFocus.find(isBig) ?? openFocus[0] ?? null

  // ---- where each decision sits on main: at its real date, but with room for what it needs, newest nearest now
  const decidedAt = (s: Scenario) => {
    const chosen = viewsOf(s).find((v) => v.branch.status === 'merged')
    const decision = chosen && opts.events.find((e) => e.event_type === 'decision' && e.payload?.from_branch === chosen.branch.id)
    return decision ? yearOf(decision.date) : Math.min(...viewsOf(s).map((v) => yearOf(v.branch.forked_at)))
  }
  const realD = (s: Scenario) => (isOpen(s) ? 0 : Math.min(0, (decidedAt(s) - now) * PAST_UNITS))
  const siteOf = new Map<string, number>()
  let cursor = primary ? -((isBig(primary) ? BIG_R : SMALL_R) + 0.7) : -0.9
  if (primary) siteOf.set(primary.id, 0)
  for (const s of [...fromMain].filter((x) => x !== primary).sort((a, b) => (isOpen(a) !== isOpen(b) ? (isOpen(a) ? -1 : 1) : isOpen(a) ? b.created_at.localeCompare(a.created_at) : realD(b) - realD(a)))) {
    // the open decision in focus sits nearest now, where there is room for its paths
    const big = isBig(s)
    const quiet = isCollapsed(s)
    const reach = quiet ? (big ? QUIET_BIG_R : SMALL_R) + 0.5 : big ? BIG_R + 1.2 : HANDLE + 0.3 // how much of main ahead of its centre it occupies
    const D = Math.min(realD(s), cursor - reach)
    siteOf.set(s.id, D)
    cursor = D - (quiet ? (big ? QUIET_BIG_R : SMALL_R) + 0.6 : big ? BIG_R + 1.4 : SMALL_R + 0.5)
  }

  // ---- main's axis. It wanders in long S-curves, and at every life decision that was made it TURNS the way that was chosen.
  const turns = fromMain
    .filter((s) => isBig(s) && chosenIndex(s) >= 0)
    .map((s) => ({ D: siteOf.get(s.id) ?? 0, angle: bigAngles(viewsOf(s).length)[chosenIndex(s)] }))
  const wander = (D: number) => 0.34 * Math.sin(D * 0.16 + 0.9) + 0.12 * Math.sin(D * 0.07 + 2.0)
  const turned = (D: number) => turns.reduce((sum, t) => sum + t.angle * ease((D - t.D + 1.1) / 2.2), 0)
  const headingAt = (D: number) => wander(D) + turned(D) - (wander(0) + turned(0))
  const heave = (_D: number) => 0 // main is level: every circle on it meets it flush
  const firstEvent = mainEvents.length ? Math.min(...mainEvents.map((e) => yearOf(e.date))) : now - 4
  const nBack = Math.ceil(Math.max((now - (Math.min(firstEvent, now - 3) - 0.6)) * PAST_UNITS, -cursor + 3) / DS)
  const pastLen = nBack * DS
  const back: Sample[] = [{ x: 0, y: 0, z: 0 }]
  for (let i = 1; i <= nBack; i++) {
    const h = headingAt(-(i - 0.5) * DS)
    const p = back[i - 1]
    back.push({ x: p.x - Math.sin(h) * DS, y: heave(-i * DS), z: p.z + Math.cos(h) * DS })
  }
  const ahead: Sample[] = [{ x: 0, y: 0, z: 0 }]
  for (let i = 1; i <= AHEAD / DS; i++) {
    const h = headingAt((i - 0.5) * DS)
    const p = ahead[i - 1]
    ahead.push({ x: p.x + Math.sin(h) * DS, y: heave(i * DS), z: p.z - Math.cos(h) * DS })
  }
  const mainSamples = [...back].reverse()
  const mainAxis: Axis = (D) => {
    const p = D <= 0 ? along(mainSamples, pastLen + Math.max(-pastLen, D)) : along(ahead, Math.min(AHEAD, D))
    return { ...p, heading: headingAt(Math.max(-pastLen, Math.min(AHEAD, D))) }
  }
  const timeD = (t: number) => Math.max(-pastLen, Math.min(0, (t - now) * PAST_UNITS))

  const lanes: LaneSpec[] = []
  const plazas: Plaza[] = []

  // parents before the decisions made inside them
  const ordered: Scenario[] = []
  const pending = scenarios.filter((s) => viewsOf(s).length > 0)
  while (pending.length) {
    const i = pending.findIndex((s) => !s.assuming_branch_id || lanesWillExist(ordered, s.assuming_branch_id) || !byId.has(s.assuming_branch_id))
    ordered.push(...pending.splice(i < 0 ? 0 : i, 1))
  }

  let smallSide: 1 | -1 = 1
  const childCount = new Map<string, number>()

  for (const scenario of ordered) {
    const views = viewsOf(scenario)
    const big = isBig(scenario)
    const parent = scenario.assuming_branch_id ? (lanes.find((l) => l.id === scenario.assuming_branch_id) ?? null) : null
    if (scenario.assuming_branch_id && !parent) continue // made inside a life that is not drawn just now
    const collapsed = isCollapsed(scenario)
    const example = (scenario as { example?: boolean }).example === true

    // the axis this decision sits on: main, or the branch it is made inside
    let axis: Axis
    let site: number
    if (parent) {
      const k = childCount.get(parent.id) ?? 0
      childCount.set(parent.id, k + 1)
      axis = (D) => along(parent.samples, Math.max(0, D))
      site = Math.min(parent.fullLen * 0.7, (big ? 8 : 5.5) + k * (HANDLE + 1.6))
    } else {
      axis = mainAxis
      site = siteOf.get(scenario.id) ?? 0
    }
    const arriving = axis(site - (big && !parent ? 1.2 : 0))
    const centre = { ...axis(site), heading: arriving.heading }
    const scale = parent ? Math.min(1, parent.width / MAIN_WIDTH + 0.1) : 1
    const side: 1 | -1 = big ? 1 : smallSide
    if (!big) smallSide = smallSide === 1 ? -1 : 1
    plazas.push({ id: scenario.id, big, at: centre, r: (collapsed && big ? QUIET_BIG_R : big ? BIG_R : SMALL_R) * scale, label: clip(scenario.situation, 38), decided: !isOpen(scenario), onMain: !parent, collapsed, branchIds: views.map((v) => v.branch.id) })
    if (collapsed) continue

    const chosen = chosenIndex(scenario)
    const angles = parent && big ? views.map((_, i) => (parent.side || 1) * (48 + 46 * i) * DEG) : bigAngles(views.length)
    let rank = 0 // small options: the chosen handle sits nearest main, the rest stack outward

    views.forEach((view, i) => {
      const status = view.branch.status
      const closed = status === 'faded' || status === 'stale' || status === 'expired'
      const merged = status === 'merged'
      const steps = view.years.length
      const span = Math.max(1 / 365, yearOf(view.years[steps - 1].at) - Math.min(now, yearOf(view.branch.forked_at)))
      const fullLen = Math.round((big ? Math.max(12, Math.min(26, 10 + 22 * Math.sqrt(span / 40))) * (parent ? 0.75 : 1) : HANDLE + 1) / DS) * DS
      const stepLen = fullLen / steps
      // each step ends where its date falls, with time eased so the dense early weeks get room: the first
      // month of a three-year path takes about a fifth of it. Never less than a sliver per step.
      const t0 = Math.min(yearOf(view.branch.forked_at), yearOf(view.years[0].at))
      const tEnd = Math.max(t0 + 1 / 365, yearOf(view.years[steps - 1].at))
      const stepEnds: number[] = []
      view.years.forEach((y, k) => {
        const u = clamp01((yearOf(y.at) - t0) / (tEnd - t0))
        const d = fullLen * Math.pow(u, 0.45)
        stepEnds.push(Math.min(fullLen, Math.max(d, (stepEnds[k - 1] ?? 0) + Math.min(0.35, stepLen * 0.5))))
      })
      stepEnds[steps - 1] = fullLen
      // the first step is the choice itself: a clear stretch straight off the decision's circle
      const headD = big ? (parent ? 0 : BIG_R * scale) + 1.9 : 1.15
      if (steps > 1 && stepEnds[0] < headD) {
        const push = headD - stepEnds[0]
        for (let k = 0; k < steps - 1; k++) stepEnds[k] = Math.min(fullLen - (steps - 1 - k) * 0.2, stepEnds[k] + push * (1 - k / (steps - 1)))
      }
      const count = Math.round(fullLen / DS)
      const width = (big ? 1.0 : 0.4) * scale
      const phase = hash01(view.branch.id) * Math.PI * 2
      const samples: Sample[] = []
      let laneSide: 1 | -1 = side
      let fromD = -1
      let drawLen = fullLen
      let stoneLen = 0

      if (big && merged && !parent) {
        // the chosen way IS main from the plaza on: main turned here
        for (let k = 0; k <= count; k++) samples.push(mainAxis(site + k * DS))
        // A merge commits ONE step: main turns onto the chosen way and advances along it, and that is all
        // that becomes main's stone. Main's own band already covers what has been lived since. Everything
        // beyond stays a projected path, drawn by likelihood like any open one, and still walkable.
        const lived = Math.max(0, -site)
        fromD = lived - 0.2
        drawLen = primary ? lived : fullLen // unless a new junction already stands at now, where the way ahead divides again
        stoneLen = lived + 0.3
        laneSide = angles[i] >= 0 ? 1 : -1
      } else if (big) {
        // a full-width band leaving the plaza for its own part of the sky, in long graceful curves
        const a = angles[i]
        laneSide = a >= 0 ? 1 : -1
        let x = centre.x
        let z = centre.z
        for (let k = 0; k <= count; k++) {
          const d = k * DS
          samples.push({ x, y: centre.y + (-Math.sign(a) * 0.9 * (1 - Math.exp(-d / 9)) + 0.22 * Math.sin(d * 0.19 + phase)) * ease((d - BIG_R) / 5), z })
          const dm = d + DS / 2
          const h = centre.heading + a + 0.24 * Math.sin(dm * 0.2 + phase) * ease((dm - BIG_R) / 7) // straight out through its own place on the rim, then long curves
          x += Math.sin(h) * DS
          z -= Math.cos(h) * DS
        }
        if (merged) stoneLen = stepEnds[0] // chosen inside another life: only its first step is committed; the rest stays projected
        if (status === 'stale' || status === 'expired') drawLen = Math.min(fullLen, 3.4)
        else if (status === 'faded') drawLen = Math.min(fullLen, 8)
      } else {
        // a thin offshoot that keeps close to the band it left; chosen, it comes back in like a cup handle
        const order = merged ? 0 : ++rank - (chosen >= 0 ? 0 : 1)
        const amp = (0.9 + 0.7 * order) * scale + (chosen >= 0 && !merged ? 0.35 : 0)
        // each option has its own exit point on the rim of the circle, further round for each one out
        const R = SMALL_R * scale * 0.8
        const phi = (28 + 44 * order) * DEG // far enough round the rim from its neighbour that there is daylight between them
        const rimOff = R * Math.sin(phi)
        const rimAlong = R * Math.cos(phi)
        for (let k = 0; k <= count; k++) {
          const d = k * DS
          const a = axis(site + rimAlong + d)
          const reach = merged
            ? rimOff * (1 - clamp01(d / HANDLE)) + (amp - rimOff * 0.5) * Math.pow(Math.sin(Math.PI * clamp01(d / HANDLE)), 0.8)
            : rimOff + (amp * (1 + 0.12 * d) - rimOff) * Math.pow(Math.sin((Math.PI / 2) * clamp01(d / 2.2)), 0.9)
          const off = side * reach
          samples.push({ x: a.x + Math.cos(a.heading) * off, y: a.y + Math.abs(off) * 0.05 * ease((d - 0.3) / 1.5), z: a.z + Math.sin(a.heading) * off })
        }
        if (merged) {
          drawLen = HANDLE
          stoneLen = HANDLE + 1
        } else if (status === 'stale' || status === 'expired') drawLen = 1.5
        else if (status === 'faded') drawLen = 2.3
      }

      // how built it is along its length, from each step's agreement
      const built = new Float32Array(count + 1)
      for (let k = 0; k <= count; k++) {
        const f = sOfD(stepEnds, k * DS) - 0.5
        const a = Math.max(0, Math.min(steps - 1, Math.floor(f)))
        const b = Math.min(steps - 1, a + 1)
        const t = clamp01(f - a)
        let here = f < 0 ? 1 + (builtFrom(view.years[0].solidity) - 1) * clamp01(f + 0.5) * 2 : builtFrom(view.years[a].solidity) * (1 - t) + builtFrom(view.years[b].solidity) * t
        if (!big && status === 'open') here = Math.max(here, 0.74) * (1 - ease(((k * DS) / fullLen - 0.8) / 0.2)) // a small option is one clean thin band, tapering only at its very end
        // A path you could still take is never invisible: its first step (the choice itself) is plain stone, and the
        // rest is at least a thin pale band for the first half of its way, however unsure. Likelihood still shows above that.
        if (status === 'open') here = Math.max(here, k * DS <= stepEnds[0] ? 0.78 : 0.4 * (1 - ease(((k * DS) / fullLen - 0.5) / 0.45)))
        built[k] = closed ? Math.max(here, 0.78) : here
      }
      let giveOut = fullLen
      for (let k = Math.round(1.5 / DS); k <= count; k++)
        if (built[k] < 0.32) {
          giveOut = k * DS
          break
        }
      const fade = new Float32Array(count + 1)
      for (let k = 0; k <= count; k++) {
        const t = clamp01((k * DS - giveOut) / (big ? 9 : 1.5))
        fade[k] = status === 'open' ? 1 - t * t * (3 - 2 * t) : 1
      }
      const tagStagger = scenario === primary ? i * (big ? 1.1 : 0.45) : 0
      const tagD0 = big ? Math.max(1.2, Math.min(drawLen - 0.1, giveOut + 2, 12.5)) : Math.min(drawLen, fullLen * 0.86)

      const tagD = Math.min(fullLen - 0.2, tagD0 + tagStagger)

      const nodes: NodeSpec[] = []
      view.years.forEach((step, index) => {
        step.events.forEach((e, n) => {
          const from = index === 0 ? 0 : stepEnds[index - 1]
          // the choice itself (head) stands at the end of the first step: what a merge commits
          const d = isHead(e) ? stepEnds[0] : from + (0.35 + (0.5 * (n + 1)) / (step.events.length + 1)) * (stepEnds[index] - from)
          if ((d <= drawLen - 0.15 && d >= fromD) || isHead(e)) nodes.push({ id: e.id, kind: 'event', step: index, d, label: e.text, caption: step.label, basis: basisOf(e), domain: e.domain, event: e })
        })
      })
      for (const c of view.branch.commits ?? []) {
        const index = Math.max(0, view.years.findIndex((y) => y.at >= c.at || y.year >= c.year))
        const d = (index === 0 ? 0 : stepEnds[index - 1]) + 0.12 * (stepEnds[index] - (index === 0 ? 0 : stepEnds[index - 1]))
        if (d <= drawLen && d >= fromD) nodes.push({ id: c.id, kind: 'commit', step: index, d, label: c.message, caption: view.years[index].label, basis: 'background', domain: 'commit' })
      }

      const deadline = view.branch.precondition?.match(/(\d{4}-\d{2}-\d{2})/)?.[1] ?? null
      lanes.push({
        id: view.branch.id,
        view,
        status,
        big,
        accent: accents[i % accents.length],
        width,
        steps,
        stepLen,
        stepEnds,
        fullLen,
        fromD,
        drawLen,
        stoneLen,
        breaks: status === 'stale' || status === 'expired',
        side: laneSide,
        small: !big,
        atNow: scenario === primary,
        example,
        samples,
        built,
        fade,
        tagD,
        headD: stepEnds[0],
        nodes,
        note: status === 'open' && deadline ? `open until ${dayLabel(deadline)}` : (STATUS_NOTE[status] ?? ''),
      })
    })
  }

  // ---- main's own log, and what has been picked to keep
  // Main's marks. Things that share a date are ONE mark (they must never stretch main), and what has no real
  // date (facts about the person, breadcrumbs, glimpses, notes) is not a moment on main at all.
  const UNDATED = /^(state_fact|breadcrumb|profile_glimpse|note|goal)$/
  const byDay = new Map<string, LifeEvent[]>()
  for (const e of mainEvents) {
    if (UNDATED.test(e.event_type) || e.payload?.undated === true || yearOf(e.date) > now + 0.01) continue
    const day = e.date.slice(0, 10)
    byDay.set(day, [...(byDay.get(day) ?? []), e])
  }
  const nodes = [...byDay.entries()].map(([day, es]) => ({
    id: es[0].id,
    kind: 'event' as const,
    step: 0,
    d: 0,
    label: es.length === 1 ? es[0].text : `${es[0].text} · and ${es.length === 2 ? 'one more thing' : 'more'} that day`,
    caption: dayLabel(day),
    basis: (es[0].source === 'told' ? 'personal' : 'sourced') as Basis | 'personal',
    domain: es[0].domain,
    event: es[0],
    at: mainAxis(timeD(yearOf(day))),
  }))
  const seeds = mainEvents
    .filter((e) => e.event_type === 'goal')
    .map((e, i) => {
      const target = typeof e.payload?.target_date === 'string' ? yearOf(e.payload.target_date) : now + 2
      const a = mainAxis(Math.max(primary ? BIG_R + 1.6 : 2.2, Math.min(8, (target - now) * 0.9)) + i * 1.5)
      return { id: e.id, label: e.text, caption: typeof e.payload?.target_date === 'string' ? `picked · toward ${String(e.payload.target_date).slice(0, 4)}` : 'picked', at: { x: a.x, y: a.y + 0.1, z: a.z } }
    })

  // the overview keeps in sight: main's recent past, now, every junction near it, and every open way as far as it is visibly there
  // … composed around the one decision in focus: enough of main to reach it, now, and its paths
  const focusBack = Math.max(0, ...plazas.filter((p) => p.onMain && !p.collapsed).map((p) => Math.hypot(p.at.x, p.at.z)))
  const backLen = Math.min(pastLen, plazas.some((p) => p.collapsed) ? Math.max(6, focusBack + 2.5) : Math.max(9, -cursor))
  const frame: Sample[] = [mainAxis(-backLen), mainAxis(0), mainAxis(2), ...seeds.map((s) => s.at)]
  for (const p of plazas) if (p.onMain && (!p.collapsed || Math.hypot(p.at.x, p.at.z) < backLen)) frame.push(p.at)
  for (const l of lanes) {
    const reach = l.status === 'open' ? Math.min(l.tagD + 1, 13.5) : Math.min(l.drawLen, 7)
    for (let d = Math.max(0, l.fromD); d <= reach; d += 1.5) frame.push(along(l.samples, d))
  }

  return { now, main: { samples: mainSamples, nodes, seeds }, lanes, plazas, frame }
}

function lanesWillExist(ordered: Scenario[], branchId: string) {
  return ordered.some((o) => o.branch_ids.includes(branchId))
}

/** The rarest life on a branch: a hair-thin dotted strand, peeling off beside it. */
export function layoutRare(lane: LaneSpec, years: BranchYear[]): { samples: Sample[]; len: number } {
  const len = Math.min(dOfS(lane, years.length), lane.status === 'open' ? lane.fullLen : lane.drawLen)
  const samples: Sample[] = []
  const reach = lane.big ? 1.5 : 0.55
  for (let d = 0; d <= len + 1e-6; d += DS) {
    const p = along(lane.samples, d)
    const off = lane.side * (reach * ease((d - 0.3) / 3.2) + 0.18 * Math.sin(d * 0.8) * ease(d / 4))
    samples.push({ x: p.x + Math.cos(p.heading) * off, y: p.y + 0.12 * ease(d / 3), z: p.z + Math.sin(p.heading) * off })
  }
  return { samples, len }
}
