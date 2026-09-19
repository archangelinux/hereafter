// The world: the branch timeline as a place. A winding trail of rounded stepping stones resting on
// soft floating islets; at a decision the trail opens like a river delta.
//
// DROP-IN for `Line` (src/line/Line.tsx): it takes exactly the same props. Mount it full-bleed;
// the sky is transparent, so the page's own gradient shows through behind it.
//
// Additions, all OPTIONAL, for a HUD to use:
//   safeInsets?: {top,right,bottom,left} in px — the regions the HUD covers. The world composes itself
//       inside what is left: the overview frames the whole delta in the clear middle, the walked figure
//       stands left-of-centre in it, and no in-scene label is ever placed under the HUD.
//       e.g. <World {...viewProps} safeInsets={{ top: 24, right: 24, bottom: 210, left: 370 }} />
//   onArrive?(eventId, branchId)  — the figure has walked up to an event's landmark (a waypoint)
//   onWalking?(moving)            — the figure set off / came to rest (for footstep sound, HUD state)
// The walk itself is driven by the existing cursor props: set `activeId` + `hereStep` and the figure
// walks there along the ribbon (back to the fork first if it has to change branch); set `activeId`
// to null and it walks home to now. There is no separate walkTo: the cursor IS the destination.
//
// Interaction: click a ribbon or its name → onSwitch; click along the active ribbon, or a landmark
// on it → onSeek; click one of main's landmarks → onOpenLog. Drag pans, the wheel zooms.

import { useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent, type WheelEvent as ReactWheelEvent } from 'react'
import * as THREE from 'three'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import type { BranchView, BranchYear, LifeEvent, Scenario } from '../types'
import { LabelLayer, LabelProjector, type Insets, type LabelSpec } from './Labels'
import { Mark } from './Marks'
import { along, DS, layoutRare, layoutWorld, type LaneSpec, type WorldLayout } from './layout'
import { Past, Seeds, Sky } from './Scenery'
import { RareTrail, Trail } from './Trail'
import { newWalkerState, Walker, type WalkerState } from './Walker'
import './world.css'

export interface WorldProps {
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
  safeInsets?: Partial<Insets>
  onArrive?: (eventId: string, branchId: string) => void
  onWalking?: (moving: boolean) => void
}

function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() => typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches)
  useEffect(() => {
    const mq = matchMedia('(prefers-reduced-motion: reduce)')
    const on = () => setReduced(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])
  return reduced
}

interface View {
  x: number // pan, in screen pixels
  y: number
  k: number // zoom on top of the framing
}

export function World({ now, events, views, scenarios, activeId, hereStep, rare, onSwitch, onSeek, onOpenLog, safeInsets, onArrive, onWalking }: WorldProps) {
  const still = useReducedMotion()
  const insets = useMemo<Insets>(() => ({ top: 24, right: 24, bottom: 24, left: 24, ...safeInsets }), [safeInsets?.top, safeInsets?.right, safeInsets?.bottom, safeInsets?.left]) // eslint-disable-line react-hooks/exhaustive-deps
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const [arrivedId, setArrivedId] = useState<string | null>(null) // the one landmark the figure is standing by: only it speaks
  const labelEls = useRef(new Map<string, HTMLElement>())
  const layout = useMemo(() => layoutWorld({ now, events, views, scenarios }), [now, events, views, scenarios])
  const view = useRef<View>({ x: 0, y: 0, k: 1 })
  const [moved, setMoved] = useState(false)
  const drag = useRef<{ x: number; y: number; px: number; py: number } | null>(null)
  const walker = useRef<WalkerState>(newWalkerState())

  // branches first seen after the first paint grow outward; branches that vanish (an undo) draw back first
  const seen = useRef<Set<string> | null>(null)
  const last = useRef(new Map<string, LaneSpec>())
  const [leaving, setLeaving] = useState<LaneSpec[]>([])
  const fresh = useMemo(() => {
    const ids = new Set(layout.lanes.map((l) => l.id))
    if (seen.current === null) {
      if (ids.size) seen.current = ids
      return new Set<string>()
    }
    const added = new Set([...ids].filter((id) => !seen.current!.has(id)))
    ids.forEach((id) => seen.current!.add(id))
    return added
  }, [layout])
  const freshEver = useRef(new Set<string>())
  fresh.forEach((id) => freshEver.current.add(id))
  useEffect(() => {
    const ids = new Set(layout.lanes.map((l) => l.id))
    const gone = [...last.current.values()].filter((l) => !ids.has(l.id))
    if (gone.length) {
      gone.forEach((l) => seen.current?.delete(l.id))
      setLeaving((prev) => [...prev.filter((p) => !ids.has(p.id)), ...gone])
    }
    last.current = new Map(layout.lanes.map((l) => [l.id, l]))
  }, [layout])

  const active = layout.lanes.find((l) => l.id === activeId) ?? null
  const target = active && hereStep !== null ? { lane: active, d: Math.min(active.drawLen, (hereStep + 0.6) * active.stepLen) } : active ? { lane: active, d: Math.min(active.drawLen, 0.6 * active.stepLen) } : null
  // a branch that runs down the screen (a side-stream) wants the figure high in the frame, not low
  const downhill = useMemo(() => {
    if (!active) return false
    const a = along(active.samples, 0.5)
    const b = along(active.samples, Math.min(active.drawLen, 5))
    return -(b.x - a.x) - (b.z - a.z) < 0
  }, [active])
  const rarePoints = useMemo(() => {
    if (!active || !rare) return []
    const r = layoutRare(active, rare)
    const out: { x: number; y: number; z: number }[] = []
    for (let d = 0.9; d <= r.len; d += 0.55) out.push(along(r.samples, d))
    return out
  }, [active, rare])
  const hereLabel = active && hereStep !== null ? (active.view.years[hereStep]?.label ?? null) : null

  useEffect(() => {
    view.current = { x: 0, y: 0, k: 1 }
    setMoved(false)
  }, [activeId])

  // names and captions live in one layer over the canvas, where they can be kept apart from each other and from the HUD
  const labels = useMemo<LabelSpec[]>(() => {
    const out: LabelSpec[] = [
      { id: 'here', priority: 100, align: 'above', className: 'hw-here', node: hereLabel ?? 'now', at: () => ({ x: walker.current.x, y: walker.current.y + 1.2, z: walker.current.z }) },
    ]
    for (const lane of layout.lanes) {
      const settled = lane.status !== 'open' && lane.status !== 'faded'
      const hovered = hoveredId === lane.id
      // far names belong to the overview; what is settled keeps its name to itself until you go near it
      if (!hovered && (activeId || settled)) continue
      const p = along(lane.samples, lane.tagD)
      out.push({
        id: `lane:${lane.id}`,
        priority: hovered ? 95 : lane.status === 'open' ? 50 + lane.fullLen : 20,
        align: lane.side === -1 && lane.status !== 'merged' ? 'left' : 'right',
        className: `hw-tag hw-tag--${lane.status}`,
        at: () => ({ x: p.x, y: p.y + 0.3, z: p.z }),
        onClick: () => onSwitch(lane.id),
        node: (
          <>
            <span className="hw-tag__name" style={lane.status === 'open' ? { color: lane.accent } : undefined}>
              {lane.example ? 'an example · ' : ''}
              {lane.view.branch.label}
            </span>
            {lane.note && <span className="hw-tag__note">{lane.note}</span>}
          </>
        ),
      })
    }
    if (rarePoints.length > 6) {
      const p = rarePoints[6]
      out.push({ id: 'rare', priority: 80, align: active?.side === -1 ? 'left' : 'right', className: 'hw-tag hw-tag--rare', at: () => ({ x: p.x, y: p.y + 0.3, z: p.z }), node: <span className="hw-tag__note">the rarest life here</span> })
    }
    if (!activeId)
      for (const seed of layout.main.seeds)
        out.push({ id: `seed:${seed.id}`, priority: 30, align: 'left', className: 'hw-tag hw-tag--seed', at: () => ({ x: seed.at.x, y: seed.at.y + 0.7, z: seed.at.z }), node: (<><span className="hw-tag__note">{seed.caption}</span><span className="hw-tag__aside">{seed.label}</span></>) })
    return out
  }, [layout, activeId, hoveredId, hereLabel, onSwitch, rarePoints, active])

  const onWheel = (e: ReactWheelEvent) => {
    view.current.k = Math.max(0.55, Math.min(3, view.current.k * Math.exp(-e.deltaY * 0.0016)))
    setMoved(true)
  }
  const onDown = (e: ReactPointerEvent) => {
    drag.current = { x: e.clientX, y: e.clientY, px: view.current.x, py: view.current.y }
  }
  const onMove = (e: ReactPointerEvent) => {
    const d = drag.current
    if (!d) return
    const dx = e.clientX - d.x
    const dy = e.clientY - d.y
    if (Math.abs(dx) + Math.abs(dy) < 5) return
    view.current.x = d.px + dx
    view.current.y = d.py + dy
    if (!moved) setMoved(true)
  }
  const onUp = () => (drag.current = null)

  return (
    <div className="hw-world" onWheel={onWheel} onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerLeave={onUp}>
      <Canvas orthographic flat camera={{ position: [60, 55, 60], zoom: 24, near: 0.1, far: 500 }} dpr={[1, 2]} gl={{ antialias: true, alpha: true }}>
        <Rig layout={layout} walker={walker} following={!!active} downhill={downhill} view={view} insets={insets} still={still} onWalking={onWalking} />
        <LabelProjector specs={labels} els={labelEls} insets={insets} />
        <Sky still={still} />
        <Past layout={layout} still={still} onOpenLog={onOpenLog} />
        <Seeds layout={layout} still={still} />

        {[...layout.lanes, ...leaving.filter((l) => !layout.lanes.some((x) => x.id === l.id))].map((lane) => {
          const isLeaving = !layout.lanes.includes(lane)
          const isActive = lane.id === activeId
          const closed = lane.status === 'faded' || lane.status === 'stale' || lane.status === 'expired'
          const pale = (active && !isActive ? 0.38 : 1) * (lane.example ? 0.8 : 1)
          return (
            <group key={lane.id}>
              <Trail
                spec={lane}
                fresh={freshEver.current.has(lane.id)}
                leaving={isLeaving}
                active={isActive}
                activeStep={isActive ? hereStep : null}
                dim={!!active && !isActive}
                still={still}
                onGone={() => setLeaving((prev) => prev.filter((p) => p.id !== lane.id))}
                onHover={(over) => setHoveredId((h) => (over ? lane.id : h === lane.id ? null : h))}
                onSwitch={() => onSwitch(lane.id)}
                onSeek={(step) => onSeek(lane.id, step)}
              />
              {!isLeaving &&
                (isActive ? lane.nodes : active ? [] : hintsOf(lane)).map((n, i) => (
                  <Mark
                    key={n.id}
                    node={n}
                    at={along(lane.samples, n.d)}
                    laneId={lane.id}
                    family={lane.status === 'merged' && n.d <= lane.stoneLen ? 'past' : closed ? 'ruin' : 'open'}
                    side={(i % 2 === 0 ? lane.side : -lane.side) as 1 | -1}
                    walked={isActive}
                    speaking={isActive && arrivedId === n.id}
                    pale={pale}
                    still={still}
                    walker={walker}
                    onPick={() => (isActive ? onSeek(lane.id, n.step) : onSwitch(lane.id))}
                    onArrive={() => (setArrivedId(n.id), onArrive?.(n.id, lane.id))}
                  />
                ))}
            </group>
          )
        })}

        {active && rare && <RareTrail points={rarePoints} still={still} />}
        <Walker layout={layout} target={target} state={walker} still={still} />
      </Canvas>
      <LabelLayer specs={labels} els={labelEls} />

      {(moved || active) && (
        <button
          type="button"
          className="hw-recentre"
          onClick={() => {
            view.current = { x: 0, y: 0, k: 1 }
            setMoved(false)
          }}
        >
          {moved ? 'recentre' : ''}
        </button>
      )}
    </div>
  )
}

export default World

/** On a branch you are not on: at most two quiet hints of what happens there, where it is still stone. */
function hintsOf(lane: LaneSpec) {
  const onStone = lane.nodes.filter((n) => n.kind === 'event' && n.basis !== 'background' && n.d > 1.5 && n.d < lane.drawLen - 0.5 && lane.built[Math.round(n.d / DS)] >= 0.5)
  const sourced = onStone.filter((n) => n.basis === 'sourced')
  return (sourced.length ? sourced : onStone).slice(0, lane.small ? 1 : 2)
}

// ---------------------------------------------------------------- the camera

// A fixed, gentle, near-isometric gaze. Only the point it rests on and how closely it looks change.
const GAZE = new THREE.Vector3(1, 0.92, 1).normalize()
const RIGHT = new THREE.Vector3(1, 0, -1).normalize()
const UP = new THREE.Vector3(0, 1, 0).addScaledVector(GAZE, -GAZE.y).normalize()

function Rig({ layout, walker, following, downhill, view, insets, still, onWalking }: { downhill: boolean; layout: WorldLayout; walker: React.RefObject<WalkerState>; following: boolean; view: React.RefObject<View>; insets: Insets; still: boolean; onWalking?: (moving: boolean) => void }) {
  const size = useThree((s) => s.size)
  const at = useRef<THREE.Vector3 | null>(null)
  const zoom = useRef<number | null>(null)
  const wasMoving = useRef(false)

  // the overview frames main and every open fork
  const fit = useMemo(() => {
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
    const v = new THREE.Vector3()
    for (const p of layout.frame) {
      v.set(p.x, p.y, p.z)
      const sx = v.dot(RIGHT)
      const sy = v.dot(UP)
      minX = Math.min(minX, sx); maxX = Math.max(maxX, sx); minY = Math.min(minY, sy); maxY = Math.max(maxY, sy)
    }
    const centre = new THREE.Vector3().addScaledVector(RIGHT, (minX + maxX) / 2).addScaledVector(UP, (minY + maxY) / 2)
    return { centre, w: maxX - minX + 7, h: maxY - minY + 6 } // air around it, like a postcard
  }, [layout])

  const want = useMemo(() => new THREE.Vector3(), [])
  useFrame(({ camera }, dt) => {
    const w = walker.current
    const v = view.current
    if (!w || !v) return
    if (w.moving !== wasMoving.current) {
      wasMoving.current = w.moving
      onWalking?.(w.moving)
    }
    // compose inside what the HUD leaves clear
    const safeW = Math.max(200, size.width - insets.left - insets.right)
    const safeH = Math.max(160, size.height - insets.top - insets.bottom)
    let wantZoom: number
    let fx: number // where on screen the point of interest should sit
    let fy: number
    if (following || w.laneId) {
      // walking: the figure left of centre and low in the clear area, its branch running up and to the right
      want.set(w.x, w.y, w.z)
      wantZoom = Math.max(30, Math.min(58, Math.min(safeW / 22, safeH / 12)))
      fx = insets.left + safeW * 0.36
      fy = insets.top + safeH * (downhill ? 0.3 : 0.64)
    } else {
      want.copy(fit.centre)
      wantZoom = Math.max(10, Math.min(46, Math.min(safeW / fit.w, safeH / fit.h)))
      fx = insets.left + safeW / 2
      fy = insets.top + safeH / 2
    }
    wantZoom *= v.k
    want.addScaledVector(RIGHT, -(fx - size.width / 2 + v.x) / wantZoom).addScaledVector(UP, (fy - size.height / 2 + v.y) / wantZoom)
    if (!at.current || zoom.current === null || still) {
      at.current = want.clone()
      zoom.current = wantZoom
    } else {
      at.current.x = THREE.MathUtils.damp(at.current.x, want.x, 1.7, dt)
      at.current.y = THREE.MathUtils.damp(at.current.y, want.y, 1.7, dt)
      at.current.z = THREE.MathUtils.damp(at.current.z, want.z, 1.7, dt)
      zoom.current = THREE.MathUtils.damp(zoom.current, wantZoom, 1.4, dt)
    }
    camera.position.copy(at.current).addScaledVector(GAZE, 80)
    camera.lookAt(at.current)
    if (camera.zoom !== zoom.current) {
      camera.zoom = zoom.current
      camera.updateProjectionMatrix()
    }
  })
  return null
}
