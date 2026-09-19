import { useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent, type WheelEvent as ReactWheelEvent } from 'react'
import { belongsOnLine, dayLabel, deadlineOf, isByYear, preciseDate, stepDate, yearOf } from '../format'
import { theme } from '../theme'
import type { BranchView, BranchYear, Insets, LifeEvent, Scenario, Zone } from '../types'
import { placeLabels, type Candidate } from './labels'
import { inkFor, layoutLine, layoutRare, type Lane, type LaneNode } from './layout'

interface Props {
  now: string
  events: LifeEvent[]
  views: BranchView[]
  scenarios: Scenario[]
  activeId: string | null
  hereStep: number | null
  rare: BranchYear[] | null // the rarest life on the active branch, when the reader has jumped to it
  onSwitch: (branchId: string) => void
  onSeek: (branchId: string, step: number) => void
  onOpenLog: () => void
  /** the corner map: no labels, no legend, the whole shape at a glance */
  compact?: boolean
  /** where the HUD is, in viewport pixels: labels stay out, and now sits clear of it */
  zones?: Zone[]
  free?: Insets
  /** the borrowed life is stepping aside: its lanes fade out */
  leavingExamples?: boolean
  onFocusDecision?: (scenarioId: string | null) => void
}

const NO_ZONES: Zone[] = []
const NO_INSETS: Insets = { top: 0, right: 0, bottom: 0, left: 0 }

/** A restrained ink per branch, by its place among its scenario's options. */
export function accentOf(view: BranchView, scenarios: Scenario[]): string {
  const scenario = scenarios.find((s) => s.id === view.branch.scenario_id)
  const i = Math.max(0, scenario?.branch_ids.indexOf(view.branch.id) ?? 0)
  return theme.branch[i % theme.branch.length]
}


export function Line({ now, events, views, scenarios, activeId, hereStep, rare, onSwitch, onSeek, onOpenLog, compact = false, zones = NO_ZONES, free = NO_INSETS, leavingExamples = false, onFocusDecision }: Props) {
  const frame = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ w: 560, h: 800 })
  const home = useMemo(() => ({ x: 0, y: 0, k: compact ? 0.4 : 1 }), [compact])
  const [pan, setPan] = useState(home)
  const drag = useRef<{ x: number; y: number; px: number; py: number; moved: boolean } | null>(null)
  const seen = useRef<Set<string> | null>(null)
  const wasForming = useRef(new Set<string>())
  const [legend, setLegend] = useState(false)

  useEffect(() => {
    const el = frame.current
    if (!el) return
    const ro = new ResizeObserver(([entry]) => setSize({ w: entry.contentRect.width, h: entry.contentRect.height }))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const focusId = views.find((v) => v.branch.id === activeId)?.branch.scenario_id ?? null
  const freeW = Math.max(360, size.w - free.left - free.right)
  const freeH = Math.max(300, size.h - free.top - free.bottom)
  const layout = useMemo(() => layoutLine({ now, events, views, scenarios, focusId, width: freeW }), [now, events, views, scenarios, focusId, freeW])

  // branches first seen after the first paint draw themselves outward
  const fresh = useMemo(() => {
    const ids = new Set(layout.lanes.map((l) => l.view.branch.id))
    if (seen.current === null) {
      if (ids.size) seen.current = ids
      return new Set<string>()
    }
    const added = new Set([...ids].filter((id) => !seen.current!.has(id)))
    ids.forEach((id) => seen.current!.add(id))
    // a guide line that has just filled in grows outward like a new branch
    for (const l of layout.lanes) {
      const id = l.view.branch.id
      if (l.view.branch.forming) wasForming.current.add(id)
      else if (wasForming.current.delete(id)) added.add(id)
    }
    return added
  }, [layout])

  const origin = compact ? { x: size.w * 0.42, y: size.h * 0.8 } : { x: free.left + freeW * 0.3, y: free.top + freeH * 0.58 }
  const mainEvents = events.filter((e) => e.branch_id === 'main' && e.event_type !== 'goal' && belongsOnLine(e))
  const goals = events.filter((e) => e.event_type === 'goal')
  const active = layout.lanes.find((l) => l.view.branch.id === activeId) ?? null
  const rareLane = useMemo(() => (active && rare ? layoutRare(active, rare) : null), [active, rare])

  // every label is a candidate; placement is by priority: where you are, the branch you are on,
  // its rare offshoot, branch names, picked moments, and last main's log
  const labels = useMemo(() => {
    if (compact) return []
    const c: Candidate[] = []
    if (active) {
      const colour = accentOf(active.view, scenarios)
      for (const n of active.nodes) {
        const here = n.step === hereStep
        const estimate = n.basis === 'estimated' ? ' · an estimate' : ''
        c.push({
          id: n.id, kind: here ? 'card' : n.kind === 'commit' ? 'commit' : 'node', priority: here ? 0 : 1, anchor: n.at, prefer: active.side, colour, reach: 120, upOnly: true,
          top: n.head ? `The choice · ${n.caption}` : n.kind === 'commit' ? `Your commit · ${n.caption}` : `${n.caption}${estimate}${here && n.event && active.view.years[n.step]?.outlook[n.event.event_type]?.probability !== undefined ? ` · ${Math.round(active.view.years[n.step].outlook[n.event.event_type].probability! * 100)}%` : ''}`,
          text: n.label,
          onClick: () => onSeek(active.view.branch.id, n.step),
        })
      }
      if (rareLane) c.push({ id: 'rare', kind: 'rare', priority: 1.5, anchor: rareLane.labelAt, prefer: active.side, colour, top: '', text: 'the rarest life here' })
    }
    for (const lane of layout.lanes) {
      const { branch } = lane.view
      if (lane === active || !lane.focus) continue
      const closed = branch.status === 'faded' || branch.status === 'stale'
      const deadline = deadlineOf(branch.precondition)
      const base = branch.forming ? 'being drawn' : branch.status === 'stale' && deadline ? `stale · closed ${dayLabel(deadline)}` : branch.status === 'open' && deadline ? `until ${dayLabel(deadline)}` : STATUS_WORDS[branch.status]
      const note = branch.example ? ['an example', base].filter(Boolean).join(' · ') : base
      if (branch.example && leavingExamples) continue
      c.push({
        id: `name:${branch.id}`, kind: 'name', priority: 2, anchor: lane.labelAt, prefer: lane.side, reach: 96, top: note, text: branch.label,
        colour: closed ? theme.color.textDim : branch.status === 'merged' ? theme.color.text : accentOf(lane.view, scenarios),
        onClick: () => onSwitch(branch.id),
      })
    }
    goals.forEach((g, i) => {
      const target = typeof g.payload.target_date === 'string' ? g.payload.target_date : null
      c.push({ id: g.id, kind: 'pick', priority: 3, anchor: { x: 0, y: pickY(i) }, prefer: -1, top: `picked${target ? ` · toward ${target.slice(0, 4)}` : ''}`, text: g.text })
    })
    ;[...mainEvents].reverse().forEach((e, i) => c.push({ id: e.id, kind: 'log', priority: 4 + i * 0.01, anchor: { x: 0, y: layout.yAt(yearOf(e.date)) }, prefer: 1, reach: 132, top: preciseDate(e), text: e.text, onClick: onOpenLog }))

    const toGraph = (z: Zone): Zone => ({ x: (z.x - origin.x - pan.x) / pan.k, y: (z.y - origin.y - pan.y) / pan.k, w: z.w / pan.k, h: z.h / pan.k })
    const pennant = active && hereStep !== null ? active.pos(hereStep + 0.6) : null
    const blocked = [...zones.map(toGraph), ...(pennant ? [{ x: pennant.x - 128, y: pennant.y - 12, w: 128, h: 24 }] : []), { x: -9, y: layout.top - 200, w: 18, h: layout.yAt(layout.pastFrom) - layout.top + 200 }, { x: -96, y: -24, w: 92, h: 62 }]
    return placeLabels(c, blocked, toGraph({ x: 8, y: 8, w: size.w - 16, h: size.h - 16 }))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [compact, layout, active, rareLane, hereStep, leavingExamples, goals.length, mainEvents.length, zones, origin.x, origin.y, pan, size.w, size.h, scenarios])

  const onWheel = (e: ReactWheelEvent) => {
    if (e.ctrlKey || e.metaKey) setPan((p) => ({ ...p, k: Math.max(0.45, Math.min(2.2, p.k * Math.exp(-e.deltaY * 0.002))) }))
    else setPan((p) => ({ ...p, y: p.y - e.deltaY, x: p.x - e.deltaX }))
  }
  const onDown = (e: ReactPointerEvent) => {
    drag.current = { x: e.clientX, y: e.clientY, px: pan.x, py: pan.y, moved: false }
  }
  const onMove = (e: ReactPointerEvent) => {
    const d = drag.current
    if (!d) return
    const dx = e.clientX - d.x
    const dy = e.clientY - d.y
    if (Math.abs(dx) + Math.abs(dy) > 4) d.moved = true
    if (d.moved) setPan((p) => ({ ...p, x: d.px + dx, y: d.py + dy }))
  }
  const onUp = () => setTimeout(() => (drag.current = null), 0)
  const unlessDragged = (fn: () => void) => () => {
    if (!drag.current?.moved) fn()
  }

  // keep the reader's place in view as the page scrolls
  useEffect(() => {
    if (hereStep === null || !active || compact) return
    const y = origin.y + pan.y + active.pos(hereStep + 0.6).y * pan.k
    if (y < free.top + freeH * 0.14 || y > free.top + freeH * 0.8) setPan((p) => ({ ...p, y: p.y + (free.top + freeH * 0.5 - y) }))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hereStep, activeId])

  // when the scenario in focus changes, the future is redrawn at another scale: come back to now
  useEffect(() => setPan(home), [focusId, home])

  const pastYears: number[] = []
  for (let y = Math.ceil(layout.pastFrom); y <= Math.floor(layout.now); y++) pastYears.push(y)
  const left = (-origin.x - pan.x) / pan.k
  const right = (size.w - origin.x - pan.x) / pan.k

  return (
    <div className={`line ${compact ? 'line--compact' : ''}`} ref={frame} onWheel={onWheel} onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerLeave={onUp}>
      <svg width={size.w} height={size.h} role="img" aria-label="Your life as a line: main below now, branches above">
        <defs>
          <filter id="ink" x="-5%" y="-5%" width="110%" height="110%">
            <feTurbulence type="fractalNoise" baseFrequency="0.035" numOctaves="2" seed="7" result="n" />
            <feDisplacementMap in="SourceGraphic" in2="n" scale="2.6" />
          </filter>
          <filter id="wash" x="-20%" y="-5%" width="140%" height="110%">
            <feGaussianBlur stdDeviation="5" />
          </filter>
        </defs>

        <g transform={`translate(${origin.x + pan.x} ${origin.y + pan.y}) scale(${pan.k})`}>
          {/* the past's years, faint, at the far left: dates are the one place digits belong */}
          {pastYears.map((y) => (
            <g key={y} className="line__year">
              <line x1={left} x2={right} y1={layout.yAt(y)} y2={layout.yAt(y)} />
            </g>
          ))}

          <g filter="url(#ink)">
            {/* what has not happened yet: main goes on, unknown */}
            <line className="line__unknown" x1={0} x2={0} y1={0} y2={layout.top - 80} />
            {/* main: what actually happened. One thick line, never redrawn. */}
            {mainSpans(layout.yAt(layout.pastFrom), 0, layout.turns).map(([a, b, turned], i) => (
              <line key={i} className={turned ? 'line__main-left' : 'line__main'} x1={0} x2={0} y1={a} y2={b} />
            ))}
            <path className="line__main-root" d={`M-7 ${layout.yAt(layout.pastFrom)} h14`} />

            {layout.lanes.map((lane) => (
              <LaneInk key={`${lane.view.branch.id}:${lane.view.branch.forming}`} lane={lane} accent={accentOf(lane.view, scenarios)} active={lane === active} dim={!!active && lane !== active} fresh={fresh.has(lane.view.branch.id)} leaving={leavingExamples} />
            ))}

            {rareLane && active && (
              <g className="rare">
                <path className="rare__ink" d={rareLane.d} stroke={accentOf(active.view, scenarios)} />
                {rareLane.nodes.map((n) => (
                  <Tick key={n.id} node={n} colour={accentOf(active.view, scenarios)} />
                ))}
              </g>
            )}

            {layout.forks.filter((f) => !f.collapsed).map((f) =>
              f.scale === 'big' ? <path key={f.id} className="line__fork line__fork--big" d={`M${f.x - 10} ${f.y} L${f.x} ${f.y - 10} L${f.x + 10} ${f.y} L${f.x} ${f.y + 10} Z`} /> : <circle key={f.id} className="line__fork line__fork--small" cx={f.x} cy={f.y} r={3.5} />,
            )}

            {/* main's log entries: strokes across the line, a heavier one where something was chosen */}
            {mainEvents.map((e) => {
              const y = layout.yAt(yearOf(e.date))
              return <path key={e.id} className={`line__tick ${e.event_type === 'decision' ? 'line__tick--decision' : ''}`} d={`M-7 ${y} h14`} />
            })}
          </g>

          {/* now */}
          <g className="line__now">
            <line x1={left} x2={right} y1={0} y2={0} />
            <path d="M-9 0 L0 -9 L9 0 L0 9 Z" />
            <text x={-18} y={-10} textAnchor="end">now</text>
            {!compact && <text className="line__now-date" x={-18} y={16} textAnchor="end">{dayLabel(now)}</text>}
          </g>

          {/* picked moments: a small gold mark on main ahead of now, tied to where it came from */}
          {goals.map((g, i) => {
            const y = pickY(i)
            const from = layout.lanes.find((l) => l.view.branch.id === g.payload.from_branch)
            const node = from?.nodes.find((n) => n.id === g.payload.carried_event_id)
            return (
              <g key={g.id} className="line__pick">
                {node && <path className="line__pick-tie" d={`M${node.at.x} ${node.at.y} C ${node.at.x * 0.6} ${node.at.y - 40}, ${node.at.x * 0.4} ${y + 10}, 0 ${y}`} />}
                <path className="line__pick-mark" d={`M0 ${y - 8} C 6 ${y - 4}, 6 ${y + 4}, 0 ${y + 8} C -6 ${y + 4}, -6 ${y - 4}, 0 ${y - 8} Z`} />
              </g>
            )
          })}

          {/* the other decisions: one circle each on main. Its name on hover; a click brings it into focus. */}
          {layout.forks.filter((f) => f.collapsed).map((f) => (
            <g key={f.id} className="line__fork--collapsed">
              <circle cx={f.x} cy={f.y} r={f.scale === 'big' ? 8 : 5} className={f.scale === 'big' ? 'line__fork line__fork--big' : 'line__fork line__fork--big line__fork--minor'} />
              <circle cx={f.x} cy={f.y} r={14} className="line__fork-hit" tabIndex={0} onClick={unlessDragged(() => onFocusDecision?.(f.id))} onKeyDown={(e) => e.key === 'Enter' && onFocusDecision?.(f.id)}><title>{f.label}</title></circle>
              {!compact && <text className="line__fork-name" x={f.x - 16} y={f.y + 4} textAnchor="end">{f.label}</text>}
            </g>
          ))}

          {/* hit areas sit above the ink, unfiltered */}
          {layout.lanes.map((lane) => (
            <path key={lane.view.branch.id} className="lane__hit" d={lane.hit} onClick={unlessDragged(() => onSwitch(lane.view.branch.id))}>
              <title>{`switch to: ${lane.view.branch.label}`}</title>
            </path>
          ))}

          {/* every label, laid out together so none overlaps another, the main line or the HUD */}
          {labels.map((l) => (
            <g key={l.id} className={`label label--${l.kind}`} style={{ color: l.colour }} onClick={l.onClick && unlessDragged(l.onClick)}>
              <path className="line__leader" d={l.leader} />
              {l.kind === 'card' && <rect className="label__paper" x={l.x} y={l.y} width={l.w} height={l.h} rx={9} />}
              {l.top && <text x={(l.side === 1 ? l.x : l.x + l.w) + (l.kind === 'card' ? l.side * 8 : 0)} y={l.y + (l.kind === 'card' ? 20 : 12)} textAnchor={l.side === 1 ? 'start' : 'end'} className="line__date">{l.top}</text>}
              <text x={(l.side === 1 ? l.x : l.x + l.w) + (l.kind === 'card' ? l.side * 8 : 0)} y={l.y + l.h - (l.kind === 'card' ? 13 : 5)} textAnchor={l.side === 1 ? 'start' : 'end'} className={l.kind === 'name' ? 'lane__title' : `line__message ${l.kind === 'commit' ? 'line__message--commit' : ''}`}>{l.text}</text>
            </g>
          ))}

          {active && hereStep !== null && hereStep + 0.6 <= active.endS && <Here lane={active} step={hereStep} accent={accentOf(active.view, scenarios)} />}
        </g>
      </svg>

      {!compact && <button type="button" className="h-link line__legend-toggle" style={{ left: free.left + 8, top: free.top + 12 }} onClick={() => setLegend((v) => !v)} aria-expanded={legend}>{legend ? 'Hide the key' : 'How to read the line'}</button>}
      {!compact && legend && <div className="line__legend" style={{ left: free.left + 8, top: free.top + 44 }}>
        <span><i className="ink ink--sure" />almost always</span>
        <span><i className="ink ink--usual" />usually</span>
        <span><i className="ink ink--even" />as often as not</span>
        <span><i className="ink ink--rare" />rarely</span>
        <span><i className="mark mark--sourced" />from a published figure</span>
        <span><i className="mark mark--estimated" />an estimate</span>
        <span><i className="mark mark--commit" />your commit</span>
      </div>}
      {!compact && (pan.x !== 0 || pan.y !== 0 || pan.k !== 1) && (
        <button type="button" className="quiet line__recentre" onClick={() => setPan(home)}>
            Back to now
        </button>
      )}
    </div>
  )
}

/** Main, cut where a merged life decision turned it aside: [y from, y to, turned aside]. */
function mainSpans(bottom: number, top: number, turns: [number, number][]): [number, number, boolean][] {
  const out: [number, number, boolean][] = []
  let from = bottom
  for (const [a, b] of [...turns].sort((x, y) => y[0] - x[0])) {
    if (a >= from || a <= top) continue
    out.push([from, a, false], [a, Math.max(b, top), true])
    from = Math.max(b, top)
  }
  out.push([from, top, false])
  return out
}

/** An event is a short stroke across the line: solid when it rests on a published figure, open when it is an estimate. */
function Tick({ node, colour }: { node: LaneNode; colour: string }) {
  const { at, normal, basis } = node
  if (node.head) return <circle className="lane__head" cx={at.x} cy={at.y} r={6} stroke={colour} />
  if (node.kind === 'commit') return <path className="lane__knot" stroke={colour} d={`M${at.x} ${at.y - 8} L${at.x + 7} ${at.y} L${at.x} ${at.y + 8} L${at.x - 7} ${at.y} Z`} />
  const a = { x: at.x - normal.x * 8, y: at.y - normal.y * 8 }
  const b = { x: at.x + normal.x * 8, y: at.y + normal.y * 8 }
  if (basis === 'estimated') {
    // two short strokes with a gap over the line: open, unfilled
    return <path className="lane__tick lane__tick--estimated" stroke={colour} d={`M${a.x} ${a.y} L${at.x - normal.x * 3} ${at.y - normal.y * 3} M${at.x + normal.x * 3} ${at.y + normal.y * 3} L${b.x} ${b.y}`} />
  }
  return <path className={`lane__tick lane__tick--${basis}`} stroke={colour} d={`M${a.x} ${a.y} L${b.x} ${b.y}`} />
}

function LaneInk({ lane, accent, active, dim, fresh, leaving }: { lane: Lane; accent: string; active: boolean; dim: boolean; fresh: boolean; leaving: boolean }) {
  const status = lane.view.branch.status
  const closed = status === 'faded' || status === 'stale'
  const colour = closed ? theme.color.ruin : accent
  return (
    <g className={`lane lane--${status} ${active ? 'lane--active' : ''} ${dim ? 'lane--dim' : ''} ${fresh ? 'lane--fresh' : ''} ${lane.view.branch.forming ? 'lane--forming' : ''} ${lane.view.branch.example ? 'lane--example' : ''} ${lane.view.branch.example && leaving ? 'lane--leaving' : ''}`}>
      {active && <path className="lane__halo" d={lane.hit} stroke={colour} />}
      {lane.segments.map((s) => {
        const certain = status === 'merged' && s.index === 0
        const base = inkFor(s.solidity)
        const small = lane.scale === 'small'
        const weighed = { ...base, width: base.width * (small ? 0.7 : 1.15) }
        const ink = certain ? { ...base, width: small ? 2 : 6, dash: undefined, wash: false } : status === 'merged' ? { ...weighed, width: weighed.width + 0.8 } : weighed
        const delay = `${Math.min(s.index, 30) * (fresh ? 80 : 45)}ms`
        return (
          <g key={s.index} style={{ opacity: s.hidden ? 0 : 1, transitionDelay: delay }} className="lane__seg">
            {ink.wash && <path d={s.d} stroke={colour} strokeWidth={13} opacity={0.16} filter="url(#wash)" fill="none" />}
            <path
              d={s.d}
              fill="none"
              stroke={certain ? theme.color.text : colour}
              strokeWidth={ink.width + (active ? 0.8 : 0)}
              strokeDasharray={ink.dash}
              strokeLinecap="round"
              strokeLinejoin="round"
              opacity={ink.opacity}
              style={{ transitionDelay: delay, animationDelay: delay }}
              className="lane__ink"
            />
          </g>
        )
      })}
      {lane.nodes.map((n) => (
        <Tick key={n.id} node={n} colour={colour} />
      ))}
      {status === 'faded' && <path className="lane__cap" stroke={colour} d={`M${lane.endAt.x - lane.endNormal.x * 9} ${lane.endAt.y - lane.endNormal.y * 9} L${lane.endAt.x + lane.endNormal.x * 9} ${lane.endAt.y + lane.endNormal.y * 9}`} />}
      {status === 'stale' && (
        <g className="lane__cut" stroke={colour}>
          <path d={`M${lane.endAt.x - 9} ${lane.endAt.y + 3} l18 -8`} />
          <path d={`M${lane.endAt.x - 9} ${lane.endAt.y - 4} l18 -8`} />
        </g>
      )}
    </g>
  )
}

const STATUS_WORDS: Record<string, string> = { open: '', merged: 'chosen · what follows is a projection', faded: 'not taken', stale: 'closed', expired: 'closed' }
const pickY = (i: number) => -110 - i * 44

/** Where the reader is on the page: a small pennant on the lane. */
function Here({ lane, step, accent }: { lane: Lane; step: number; accent: string }) {
  const p = lane.pos(step + 0.6)
  return (
    <g className="line__here" style={{ transform: `translate(${p.x}px, ${p.y}px)` }}>
      <path d="M-3 0 L-24 -7 L-24 7 Z" fill={accent} />
      <text x={-29} y={4} textAnchor="end">{lane.view.years[step] ? stepDate(lane.view.years[step].at, isByYear(lane.view.years)) : ''}</text>
    </g>
  )
}
