// Where everything in the world lies. Pure functions; the scene only draws what this returns.
//
// The world IS the branch timeline. Time has one direction across it: main flows in from the past
// (lower left on screen) to now, and everything undecided carries on the same way (upper right),
// fanning apart like a river delta. A chosen branch bows out and curves back into main. Roads not
// taken peel away to the sides and end. A decision made inside another life leaves from that
// life's ribbon, not from main. Small decisions are short side-streams near now; big ones run far.
//
// Every lane is a centreline sampled every DS of arc length from its fork (d = 0). A lane's steps
// are spread evenly along it, so `s` (0 = the fork, i + 1 = the end of step i) maps to d = s * stepLen.

import { yearOf } from '../format'
import type { Basis, BranchStatus, BranchView, BranchYear, LifeEvent, Scenario } from '../types'
import { accents } from './palette'

export const DS = 0.25
const PAST_UNITS = 1.35 // world units per year of past
const AHEAD = 40
const DEG = Math.PI / 180

export interface Sample {
  x: number
  y: number
  z: number
}

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

export interface StoneSpec {
  index: number // order outward from the fork
  step: number // which step of the branch it belongs to (-1 on main)
  lead: boolean // the step's own stone; the others only carry the trail between steps
  d: number
  x: number
  y: number
  z: number
  heading: number
  r: number
  built: number
}

/** Stepping stones along a centreline: one for each step, with smaller ones between where steps lie far apart. */
export function stonesAlong(samples: Sample[], from: number, to: number, stepLen: number, builtAt: (d: number) => number, seed: string): StoneSpec[] {
  const out: StoneSpec[] = []
  const per = Math.max(1, Math.round(stepLen / 0.72))
  const steps = Math.ceil((to - 1e-6) / stepLen)
  for (let step = 0; step < steps; step++) {
    for (let j = 0; j < per; j++) {
      const d = (step + (j + 0.5) / per) * stepLen
      if (d < from || d > to) continue
      const p = along(samples, d)
      const r1 = hash01(`${seed}:${step}:${j}`)
      const r2 = hash01(`${seed}:${step}:${j}:b`)
      const side = (r1 - 0.5) * 0.3
      const big = per === 1 ? out.length % 2 === 0 : j === 0
      out.push({ index: out.length, step, lead: j === 0, d, x: p.x + Math.cos(p.heading) * side, y: p.y, z: p.z + Math.sin(p.heading) * side, heading: p.heading, r: (big ? 0.47 : 0.35) * (0.9 + r2 * 0.22), built: builtAt(d) })
    }
  }
  return out
}

export interface LaneSpec {
  id: string
  view: BranchView
  status: BranchStatus
  accent: string
  width: number
  steps: number
  stepLen: number
  fullLen: number
  /** how much of it is drawn once settled: all of an open lane, the loop of a merged one, a stub of a stale one */
  drawLen: number
  /** merged only: how far from the fork it has become main's own stone (the loop, or what has been lived) */
  stoneLen: number
  breaks: boolean // stale: the end has visibly broken off
  side: 1 | -1
  small: boolean
  samples: Sample[]
  built: Float32Array // per sample, 0..1: how BUILT the ribbon is there
  /** per sample, 1..0: past where the stone gives out, the drawn ghost of the ribbon soon fades into mist */
  fade: Float32Array
  tagD: number // where its name sits: at its far end, as far as it is still visibly there
  nodes: NodeSpec[]
  stones: StoneSpec[]
  example: boolean // a sample path shown to a first-time visitor: drawn the same, a touch paler
  note: string
}

export interface MainSpec {
  samples: Sample[] // from the earliest past to now; the last sample is now
  stones: StoneSpec[]
  ahead: Sample[] // what has not happened yet, straight on from now
  nodes: (NodeSpec & { at: Sample & { heading: number } })[]
  seeds: { id: string; at: Sample; label: string; caption: string }[]
}

export interface WorldLayout {
  now: number
  main: MainSpec
  lanes: LaneSpec[]
  frame: Sample[] // what the overview must keep in view
  /** half the width of the platform at now, wide enough for every branch that leaves from it */
  platformHalf: number
}

const clamp01 = (v: number) => Math.max(0, Math.min(1, v))
const ease = (v: number) => {
  const c = clamp01(v)
  return c * c * c * (c * (c * 6 - 15) + 10)
}

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
export function along(samples: Sample[], d: number): Sample & { heading: number } {
  const f = Math.max(0, Math.min(samples.length - 1, d / DS))
  const i = Math.min(samples.length - 2, Math.floor(f))
  const k = f - i
  const a = samples[Math.max(0, i)]
  const b = samples[Math.min(samples.length - 1, i + 1)]
  const p = samples[Math.max(0, i - 1)]
  const n = samples[Math.min(samples.length - 1, i + 2)]
  return { x: a.x + (b.x - a.x) * k, y: a.y + (b.y - a.y) * k, z: a.z + (b.z - a.z) * k, heading: Math.atan2(n.x - p.x, -(n.z - p.z)) }
}

function fanAngles(n: number): number[] {
  if (n <= 1) return [-30 * DEG]
  const spread = n === 2 ? 34 : n === 3 ? 42 : n === 4 ? 54 : 60
  return Array.from({ length: n }, (_, i) => (-spread + (2 * spread * i) / (n - 1)) * DEG)
}

const STATUS_NOTE: Record<string, string> = { open: '', merged: 'merged into main', faded: 'a road not taken', stale: 'stale', expired: 'stale' }

export function layoutWorld(opts: { now: string; events: LifeEvent[]; views: BranchView[]; scenarios: Scenario[] }): WorldLayout {
  const now = yearOf(opts.now)
  const byId = new Map(opts.views.map((v) => [v.branch.id, v]))

  // ---- main's axis: the past behind now, and the same line carried on ahead of it
  const wander = (D: number) => 0.3 * Math.sin(D * 0.21 + 1.1) + 0.14 * Math.sin(D * 0.09 + 0.4)
  const heave = (D: number) => 0.28 * Math.sin(D * 0.27) * clamp01(Math.abs(D) / 4)
  const mainEvents = opts.events.filter((e) => e.branch_id === 'main')
  const firstEvent = mainEvents.length ? Math.min(...mainEvents.map((e) => yearOf(e.date))) : now - 4
  const nBack = Math.ceil(((now - (Math.min(firstEvent, now - 3) - 0.6)) * PAST_UNITS) / DS)
  const pastLen = nBack * DS
  const back: Sample[] = [{ x: 0, y: 0, z: 0 }]
  for (let i = 1; i <= nBack; i++) {
    const D = -(i - 0.5) * DS
    const h = (wander(D) - wander(0)) * (0.3 + 0.7 * ease(-D / 9)) // the last stretch into now is one clear sweep
    const p = back[i - 1]
    back.push({ x: p.x - Math.sin(h) * DS, y: heave(-i * DS), z: p.z + Math.cos(h) * DS })
  }
  const ahead: Sample[] = [{ x: 0, y: 0, z: 0 }]
  for (let i = 1; i <= AHEAD / DS; i++) {
    const D = (i - 0.5) * DS
    const h = (wander(D) - wander(0)) * (0.3 + 0.7 * ease(D / 9))
    const p = ahead[i - 1]
    ahead.push({ x: p.x + Math.sin(h) * DS, y: heave(i * DS), z: p.z - Math.cos(h) * DS })
  }
  const mainSamples = [...back].reverse()
  /** a point on main's axis at signed arc length D from now (negative is the past) */
  const axisAt = (D: number) => (D <= 0 ? along(mainSamples, pastLen + Math.max(-pastLen, D)) : along(ahead, Math.min(AHEAD, D)))
  const axisD = (t: number) => Math.max(-pastLen, Math.min(0, (t - now) * PAST_UNITS))

  // ---- which scenario owns the way straight ahead: the open one that reaches furthest
  const spanOf = (view: BranchView) => Math.max(1 / 365, yearOf(view.years[view.years.length - 1]?.at ?? view.branch.forked_at) - Math.min(now, yearOf(view.branch.forked_at)))
  const scenarioSpan = (s: Scenario) => Math.max(0, ...s.branch_ids.map((id) => (byId.has(id) ? spanOf(byId.get(id)!) : 0)))
  const scenarios = [...opts.scenarios].sort((a, b) => a.created_at.localeCompare(b.created_at))
  const fromMainOpen = scenarios.filter((s) => !s.assuming_branch_id && s.branch_ids.some((id) => byId.get(id)?.branch.status === 'open'))
  const primary = [...fromMainOpen].sort((a, b) => scenarioSpan(b) - scenarioSpan(a))[0] ?? null
  const lastDecided = [...scenarios].reverse().find((s) => !s.assuming_branch_id && s.branch_ids.some((id) => byId.get(id)?.branch.status === 'merged')) ?? null

  // ---- where each decision leaves main: at its real date, but never crowding another fork
  const SITE_GAP = 2.8
  const JOIN_LEN = 5.6 // a chosen branch flows back into main over this much of it
  const siteOf = new Map<string, number>()
  {
    const fromMain = scenarios.filter((sc) => !sc.assuming_branch_id)
    const isOpen = (sc: Scenario) => fromMainOpen.includes(sc)
    const real = (sc: Scenario) => (sc === primary ? 0 : isOpen(sc) ? -0.01 : axisD(Math.min(...sc.branch_ids.map((id) => (byId.has(id) ? yearOf(byId.get(id)!.branch.forked_at) : now)))))
    let lastD = Infinity
    for (const sc of [...fromMain].sort((a, b) => real(b) - real(a))) {
      if (sc === primary) {
        siteOf.set(sc.id, 0)
        lastD = 0
        continue
      }
      // an open side-stream needs a fork's width of main to itself; a decided one needs room for its rejoining too
      const room = isOpen(sc) ? SITE_GAP : JOIN_LEN + 2
      const D = Math.max(-pastLen + 1, Math.min(real(sc), (lastD === Infinity ? 0 : lastD) - room))
      siteOf.set(sc.id, D)
      lastD = D
    }
  }

  const lanes: LaneSpec[] = []
  let sideStream = 0

  // parents before the decisions made inside them
  const ordered: Scenario[] = []
  const pending = [...scenarios]
  while (pending.length) {
    const i = pending.findIndex((s) => !s.assuming_branch_id || ordered.some((o) => o.branch_ids.includes(s.assuming_branch_id!)) || !byId.has(s.assuming_branch_id))
    ordered.push(...pending.splice(i < 0 ? 0 : i, 1))
  }

  for (const scenario of ordered) {
    const views = scenario.branch_ids.map((id) => byId.get(id)).filter((v): v is BranchView => !!v && v.years.length > 0)
    if (!views.length) continue
    const parent = scenario.assuming_branch_id ? (lanes.find((l) => l.id === scenario.assuming_branch_id) ?? null) : null
    const anyOpen = views.some((v) => v.branch.status === 'open')
    const isPrimary = scenario === primary
    const stemSide: 1 | -1 = sideStream % 2 === 0 ? 1 : -1
    const isSideStream = !parent && anyOpen && !isPrimary
    if (isSideStream) sideStream++
    const openFan = fanAngles(views.length)
    let closedCount = 0

    views.forEach((view, i) => {
      const status = view.branch.status
      const closed = status === 'faded' || status === 'stale' || status === 'expired'
      const merged = status === 'merged'
      const steps = view.years.length
      const span = spanOf(view)
      const fullLen = Math.round(Math.max(5, Math.min(34, 5 + 29 * Math.sqrt(span / 40))) / DS) * DS
      const stepLen = fullLen / steps
      const small = span < 1.5
      const width = parent ? 0.62 : small ? 0.5 : 0.62 + 0.36 * clamp01(span / 25)
      const count = Math.round(fullLen / DS)
      const phase = hash01(view.branch.id) * Math.PI * 2
      const samples: Sample[] = []
      let side: 1 | -1 = 1
      let drawLen = fullLen
      let stoneLen = 0

      if (merged) {
        // The chosen branch flows back into main BEHIND now: two ribbons becoming one, a clean wide Y.
        // It comes in from the side its siblings did not take, meets main at a shallow angle, and from
        // there on it IS main.
        const site = siteOf.get(scenario.id) ?? axisD(yearOf(view.branch.forked_at))
        const joinD = Math.min(-1.6, site + JOIN_LEN)
        side = 1
        for (let k = 0; k <= count; k++) {
          const d = k * DS
          const a = axisAt(joinD - JOIN_LEN + d)
          const off = 4.2 * Math.pow(1 - clamp01(d / JOIN_LEN), 1.7) // in from well aside, meeting main at a shallow angle
          samples.push({ x: a.x + Math.cos(a.heading) * off, y: a.y + off * 0.2, z: a.z + Math.sin(a.heading) * off })
        }
        const continues = scenario === lastDecided && fromMainOpen.length === 0
        drawLen = continues ? fullLen : Math.min(fullLen, JOIN_LEN + 0.4)
        stoneLen = continues ? Math.max(JOIN_LEN, -(joinD - JOIN_LEN) + 0.4) : drawLen + 1
      } else {
        // where it leaves from, and which way that was already heading
        let start: Sample & { heading: number }
        let stem = 0
        let stemLen = 0
        let fan = openFan[i]
        const hasChosen = views.some((v) => v.branch.status === 'merged')
        if (parent) {
          start = along(parent.samples, Math.min(parent.fullLen * 0.5, Math.max(parent.stepLen * 0.9, 4.5)) + i * 0.9)
          fan = parent.side * (16 + 12 * i) * DEG
        } else if (isSideStream) {
          // a small decision: short side-streams, each leaving main from its own point
          start = axisAt((siteOf.get(scenario.id) ?? 0) - i * 0.95)
          stem = stemSide * 84 * DEG
          stemLen = 0.6
          fan = stemSide * (views.length > 1 ? 16 - (34 * i) / (views.length - 1) : 0) * DEG
        } else if (closed) {
          start = axisAt((siteOf.get(scenario.id) ?? 0) - closedCount * 1.3)
        } else {
          // the way ahead divides at the edge of the now platform: each branch from its own place on it
          const a = axisAt(0)
          const off = 0 * i // every way ahead leaves from the stone the figure stands on
          start = { ...a, x: a.x + Math.cos(a.heading) * off, z: a.z + Math.sin(a.heading) * off }
        }
        if (closed) {
          // roads not taken peel away early and well aside: all to the far side from the chosen one, or alternating
          const s: 1 | -1 = hasChosen ? -1 : closedCount % 2 === 0 ? -1 : 1
          const n = hasChosen ? closedCount : Math.floor(closedCount / 2)
          closedCount++
          stem = 0
          fan = s * (78 + 24 * n) * DEG
        }
        const total = stem + fan
        side = total >= 0 ? 1 : -1
        const lean = closed ? -1.4 : Math.abs(total) < 0.05 ? 0.2 : -Math.sign(total) * 0.8
        let x = start.x
        let z = start.z
        for (let k = 0; k <= count; k++) {
          const d = k * DS
          samples.push({ x, y: start.y + lean * 1.0 * (1 - Math.exp(-d / (closed ? 3 : 9))) + 0.16 * Math.sin(d * 0.3 + phase) * ease(d / 5), z })
          const dm = d + DS / 2
          const h = start.heading + stem * ease(dm / 1.6) + fan * ease((dm - stemLen) / (small ? 2.0 : 3.2)) + 0.15 * Math.sin(dm * 0.33 + phase) * ease(dm / 7)
          x += Math.sin(h) * DS
          z -= Math.cos(h) * DS
        }
        if (status === 'stale' || status === 'expired') drawLen = Math.min(fullLen, 3.6)
        else if (status === 'faded') drawLen = Math.min(fullLen, 10)
      }

      // how built it is along its length, from each step's agreement
      const built = new Float32Array(count + 1)
      for (let k = 0; k <= count; k++) {
        const f = (k * DS) / stepLen - 0.5
        const a = Math.max(0, Math.min(steps - 1, Math.floor(f)))
        const b = Math.min(steps - 1, a + 1)
        const t = clamp01(f - a)
        const here = f < 0 ? 1 + (builtFrom(view.years[0].solidity) - 1) * clamp01(f + 0.5) * 2 : builtFrom(view.years[a].solidity) * (1 - t) + builtFrom(view.years[b].solidity) * t
        built[k] = closed ? Math.max(here, 0.78) : here
      }

      // once the stone has given out, its drawn ghost carries on a little way and is gone
      let giveOut = fullLen
      for (let k = Math.round(1.5 / DS); k <= count; k++)
        if (built[k] < 0.32) {
          giveOut = k * DS
          break
        }
      const fade = new Float32Array(count + 1)
      for (let k = 0; k <= count; k++) {
        const t = clamp01((k * DS - giveOut) / 6)
        fade[k] = status === 'open' ? 1 - t * t * (3 - 2 * t) : 1
      }
      const tagD = merged ? Math.min(drawLen, stoneLen) / 2 : Math.max(1.4, Math.min(drawLen - 0.2, giveOut + 2.5, small ? 99 : 12.5))

      const nodes: NodeSpec[] = []
      view.years.forEach((step, index) => {
        step.events.forEach((e, n) => {
          const d = (index + 0.35 + (0.5 * (n + 1)) / (step.events.length + 1)) * stepLen
          if (d <= drawLen - 0.2) nodes.push({ id: e.id, kind: 'event', step: index, d, label: e.text, caption: step.label, basis: basisOf(e), domain: e.domain, event: e })
        })
      })
      for (const c of view.branch.commits ?? []) {
        const index = Math.max(0, view.years.findIndex((y) => y.at >= c.at || y.year >= c.year))
        const d = (index + 0.12) * stepLen
        if (d <= drawLen) nodes.push({ id: c.id, kind: 'commit', step: index, d, label: c.message, caption: view.years[index].label, basis: 'background', domain: 'commit' })
      }

      const stones = stonesAlong(samples, 0.62, fullLen, stepLen, (d) => built[Math.min(count, Math.round(d / DS))], view.branch.id)

      const deadline = view.branch.precondition?.match(/(\d{4}-\d{2}-\d{2})/)?.[1] ?? null
      lanes.push({
        id: view.branch.id,
        view,
        status,
        accent: accents[i % accents.length],
        width,
        steps,
        stepLen,
        fullLen,
        drawLen,
        stoneLen,
        breaks: status === 'stale' || status === 'expired',
        side,
        small,
        samples,
        built,
        fade,
        tagD,
        nodes,
        stones,
        example: (scenario as { example?: boolean }).example === true,
        note: status === 'open' && deadline ? `open until ${deadline}` : (STATUS_NOTE[status] ?? ''),
      })
    })
  }

  // ---- main's own log, and what has been picked to keep
  const nodes = mainEvents
    .filter((e) => e.event_type !== 'goal' && yearOf(e.date) <= now + 0.01)
    .map((e) => ({ id: e.id, kind: 'event' as const, step: 0, d: 0, label: e.text, caption: e.date, basis: (e.source === 'told' ? 'personal' : 'sourced') as Basis | 'personal', domain: e.domain, event: e, at: axisAt(axisD(yearOf(e.date))) }))
  const seeds = mainEvents
    .filter((e) => e.event_type === 'goal')
    .map((e, i) => {
      const target = typeof e.payload?.target_date === 'string' ? yearOf(e.payload.target_date) : now + 2
      const a = axisAt(Math.max(4.6, Math.min(9, (target - now) * 0.9)) + i * 1.6)
      return { id: e.id, label: e.text, caption: typeof e.payload?.target_date === 'string' ? `picked · toward ${String(e.payload.target_date).slice(0, 4)}` : 'picked', at: { x: a.x - Math.cos(a.heading) * 2.1, y: a.y + 0.3, z: a.z - Math.sin(a.heading) * 2.1 } }
    })

  // the overview keeps in sight: some past, now, what was picked, and every lane as far as it is visibly there
  const frame: Sample[] = [axisAt(-Math.min(pastLen, 10)), axisAt(0), ...seeds.map((s) => s.at)]
  for (const l of lanes) {
    const reach = l.status === 'open' ? Math.min(l.tagD + 1, 13.5) : Math.min(l.drawLen, 8)
    for (let d = 0; d <= reach; d += 1.5) frame.push(along(l.samples, d))
  }

  const onPlatform = primary ? primary.branch_ids.filter((id) => byId.get(id)?.branch.status === 'open').length : 0
  const widest = Math.max(0.7, ...lanes.filter((l) => primary?.branch_ids.includes(l.id)).map((l) => l.width))
  const platformHalf = Math.max(1.05, ((Math.max(1, primary ? primary.branch_ids.length : 1) - 1) / 2) * (widest + 0.55) + widest / 2 + 0.3) * (onPlatform ? 1 : 0.8)

  const mainStones = stonesAlong(mainSamples, 0.3, pastLen - 0.5, 0.68, () => 1, 'main').map((st) => ({ ...st, step: -1 }))

  return { now, main: { samples: mainSamples, stones: mainStones, ahead, nodes, seeds }, lanes, frame, platformHalf }
}

/** The rarest life on a branch: the faintest thread, peeling off beside it. */
export function layoutRare(lane: LaneSpec, years: BranchYear[]): { samples: Sample[]; nodes: NodeSpec[]; len: number } {
  const len = Math.min(years.length * lane.stepLen, lane.drawLen)
  const samples: Sample[] = []
  for (let d = 0; d <= len + 1e-6; d += DS) {
    const p = along(lane.samples, d)
    const off = lane.side * (1.35 * ease((d - 0.3) / 3.2) + 0.2 * Math.sin(d * 0.8) * ease(d / 4))
    samples.push({ x: p.x + Math.cos(p.heading) * off, y: p.y + 0.12 * ease(d / 3), z: p.z + Math.sin(p.heading) * off })
  }
  const nodes: NodeSpec[] = []
  years.forEach((step, index) =>
    step.events.forEach((e, n) => {
      const d = (index + 0.35 + (0.5 * (n + 1)) / (step.events.length + 1)) * lane.stepLen
      if (d <= len) nodes.push({ id: e.id, kind: 'event', step: index, d, label: e.text, caption: step.label, basis: basisOf(e), domain: e.domain, event: e })
    }),
  )
  return { samples, nodes, len }
}
