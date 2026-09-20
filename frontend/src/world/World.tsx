// The world: the branch timeline as a place. Main is one smooth flowing band of stone through the sky.
// Circles appear only where a decision is made: a large plaza for a life decision, whose options leave in
// entirely different directions; a small round for a day-to-day one, whose options are thin handles and stubs.
//
// DROP-IN for `Line` (src/line/Line.tsx): it takes exactly the same props. Mount it full-bleed;
// the sky is transparent, so the page's own gradient shows through behind it.
//
// Additions, all OPTIONAL, for a HUD to use:
//   safeInsets?: {top,right,bottom,left} in px — the regions the HUD covers. The world composes itself
//       inside what is left: the overview frames the whole delta in the clear middle, the walked figure
//       stands left-of-centre in it, and no in-scene label is ever placed under the HUD.
//       e.g. <World {...viewProps} safeInsets={{ top: 24, right: 24, bottom: 210, left: 370 }} />
//   onFocusScenario?(scenarioId)  — a COLLAPSED decision's circle was clicked: open that decision. (A scenario
//       with `collapsed: true` is drawn as its circle only, with its name on hover. If this prop is not
//       given, the click falls back to onSwitch(first branch of that scenario).)
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
import { Band } from './Band'
import { createRibbon, ribbonMaterial, writeRibbon } from './ribbon'
import { Ends, Main, Plazas, Seeds, Sky, Stops } from './Scenery'
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
  /** the choice has been made: the ghost walks back out of the future and into the figure at now */
  homing?: boolean
  onFocusScenario?: (scenarioId: string) => void
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

export function World({ now, events, views, scenarios, activeId, hereStep, rare, onSwitch, onSeek, onOpenLog, safeInsets, homing = false, onFocusScenario, onArrive, onWalking }: WorldProps) {
  const still = useReducedMotion()
  const insets = useMemo<Insets>(() => ({ top: 24, right: 24, bottom: 24, left: 24, ...safeInsets }), [safeInsets?.top, safeInsets?.right, safeInsets?.bottom, safeInsets?.left]) // eslint-disable-line react-hooks/exhaustive-deps
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const [hoveredPlaza, setHoveredPlaza] = useState<string | null>(null)
  const [arrivedId, setArrivedId] = useState<string | null>(null) // the one landmark the figure is standing by: only it speaks
  const labelEls = useRef(new Map<string, HTMLElement>())
  const layout = useMemo(() => layoutWorld({ now, events, views, scenarios }), [now, events, views, scenarios])
  const view = useRef<View>({ x: 0, y: 0, k: 1 })
  const [moved, setMoved] = useState(false)
  const drag = useRef<{ x: number; y: number; px: number; py: number } | null>(null)
  const walker = useRef<WalkerState>(newWalkerState())
  const real = useRef<WalkerState>(newWalkerState())

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
  // how many steps the cursor just moved: one press is one step; a click far ahead walks through the ones between
  const prevStep = useRef<{ lane: string | null; step: number }>({ lane: null, step: 0 })
  const stepNow = hereStep ?? 0
  const jumped = prevStep.current.lane === activeId ? Math.max(1, Math.abs(stepNow - prevStep.current.step)) : 1
  useEffect(() => {
    prevStep.current = { lane: activeId, step: stepNow }
  }, [activeId, stepNow])
  // Where the figure stands for the step being read. Anything within reach of the platform IS the
  // platform — so the last step always finishes on the stone, whatever the step bookkeeping says —
  // and nothing ever walks past it.
  // The figure stands on one of the path's own circles — the same places the reading stops at — and
  // the last of them is the end platform. The rarest life is read on the same circles.
  // ONE circle is the answer to "where is the reader?" — the ghost stands on it and it is the one that
  // lights up. Both come from here, so they can never point at different places: a step with nothing on
  // it has no circle of its own, and resolves to the next circle ahead.
  const restOn = (lane: typeof active, step: number) => {
    if (!lane || lane.rests.length === 0) return null
    const last = rare ? Math.min(lane.rests.length, rare.length) : lane.rests.length
    return lane.rests.find((r) => r.step >= step) ?? lane.rests[last - 1] ?? lane.rests[lane.rests.length - 1]
  }
  const here = restOn(active, hereStep ?? 0)
  const target = active
    ? { lane: active, d: here?.d ?? 0, steps: hereStep === null ? 1 : jumped }
    : null
  // a branch that runs down the screen (a side-stream) wants the figure high in the frame, not low
  const downhill = useMemo(() => {
    if (!active) return false
    const a = along(active.samples, 0.5)
    const b = along(active.samples, Math.min(active.drawLen, 5))
    return -(b.x - a.x) - (b.z - a.z) < 0
  }, [active])
  const rareTagAt = useMemo(() => {
    if (!active || !rare) return null
    const r = layoutRare(active, rare)
    return along(r.samples, Math.min(r.len, active.big ? 3.4 : 2.2))
  }, [active, rare])
  const hereLabel = active && hereStep !== null ? (active.view.years[hereStep]?.label ?? null) : null

  useEffect(() => {
    view.current = { x: 0, y: 0, k: 1 }
    setMoved(false)
  }, [activeId])

  // When the choice is made the ghost has nowhere left to explore: it turns round, walks back down the
  // branch to now, and steps into the figure standing there. Only once it has arrived does it stop being.
  const [arrivedHome, setArrivedHome] = useState(false)
  useEffect(() => {
    setArrivedHome(false)
  }, [activeId, homing])

  // names and captions live in one layer over the canvas, where they can be kept apart from each other and from the HUD
  const labels = useMemo<LabelSpec[]>(() => {
    const out: LabelSpec[] = [
      ...(active && (arrivedId || !hereLabel) ? [] : [{ id: 'here', priority: 100, align: 'above' as const, className: 'hw-here', node: hereLabel ?? 'now', at: () => ({ x: walker.current.x, y: walker.current.y + 1.2, z: walker.current.z }) }]),
    ]
    // Every path carries its name, always — the island should read without pointing at anything. When
    // two names would overlap the projector hides the lesser one, so priority is the whole ordering:
    // what you are pointing at, then the path you are on, then what is still open, then the ruins.
    for (const lane of layout.lanes) {
      const hovered = hoveredId === lane.id
      const p = along(lane.samples, lane.endD) // the name stands on the platform at the path's end
      out.push({
        id: `lane:${lane.id}`,
        priority: hovered ? 95 : lane.id === activeId ? 90 : lane.status === 'open' ? (lane.big ? 70 : 40) : lane.status === 'merged' ? 55 : 20,
        always: lane.atNow && lane.status === 'open' && !activeId,
        align: lane.side === -1 && lane.status !== 'merged' ? 'left' : 'right',
        className: `hw-tag hw-tag--${lane.status} ${lane.big ? '' : 'hw-tag--small'}`,
        at: () => ({ x: p.x, y: p.y + 0.3, z: p.z }),
        onClick: () => onSwitch(lane.id),
        node: (
          <>
            <span className="hw-tag__name">
              {lane.example ? 'an example · ' : ''}
              {lane.view.branch.label}
            </span>
            {lane.note && <span className="hw-tag__note">{lane.note}</span>}
          </>
        ),
      })
    }
    // and so does every decision, the ones that are only a circle included
    for (const plaza of layout.plazas) {
      const hovered = hoveredPlaza === plaza.id
      out.push({ id: `plaza:${plaza.id}`, priority: hovered ? 96 : plaza.collapsed ? 25 : plaza.big ? 60 : 35, align: 'left', className: `hw-tag hw-tag--plaza ${plaza.collapsed ? 'hw-tag--quiet' : ''}`, at: () => ({ x: plaza.at.x - Math.cos(plaza.at.heading) * (plaza.r + 0.3), y: plaza.at.y, z: plaza.at.z - Math.sin(plaza.at.heading) * (plaza.r + 0.3) }), node: <span className="hw-tag__note">{plaza.label}</span> })
    }
    if (rareTagAt) {
      const p = rareTagAt
      out.push({ id: 'rare', priority: 80, align: active?.side === -1 ? 'left' : 'right', className: 'hw-tag hw-tag--rare', at: () => ({ x: p.x, y: p.y + 0.3, z: p.z }), node: <span className="hw-tag__note">the rarest life here</span> })
    }
    if (!activeId)
      for (const seed of layout.main.seeds)
        out.push({ id: `seed:${seed.id}`, priority: 30, align: 'left', className: 'hw-tag hw-tag--seed', at: () => ({ x: seed.at.x, y: seed.at.y + 0.7, z: seed.at.z }), node: (<><span className="hw-tag__note">{seed.caption}</span><span className="hw-tag__aside">{seed.label}</span></>) })
    return out
  }, [layout, activeId, hoveredId, hereLabel, onSwitch, rareTagAt, active, hoveredPlaza, arrivedId])

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
        <Rig layout={layout} walker={walker} following={!!active} close={!!active && !active.big} downhill={downhill} view={view} insets={insets} still={still} onWalking={onWalking} />
        <LabelProjector specs={labels} els={labelEls} insets={insets} />
        <Sky still={still} />
        <Main layout={layout} still={still} />
        <Seeds layout={layout} still={still} />

        {layout.main.nodes.map((n) => (
          <Mark key={n.id} node={n} at={n.at} laneId={null} width={1.15} walked={false} pale={1} still={still} walker={walker} onPick={onOpenLog} />
        ))}

        {[...layout.lanes, ...leaving.filter((l) => !layout.lanes.some((x) => x.id === l.id))].map((lane) => {
          const isLeaving = !layout.lanes.includes(lane)
          const isActive = lane.id === activeId
          const pale = (active && !isActive ? 0.5 : 1) * (lane.example ? 0.8 : 1)
          return (
            <group key={lane.id}>
              <Band
                spec={lane}
                fresh={freshEver.current.has(lane.id)}
                leaving={isLeaving}
                active={isActive}
                dim={!!active && !isActive}
                still={still}
                onGone={() => setLeaving((prev) => prev.filter((p) => p.id !== lane.id))}
                onHover={(over) => setHoveredId((h) => (over ? lane.id : h === lane.id ? null : h))}
                onSwitch={() => onSwitch(lane.id)}
                onSeek={(step) => onSeek(lane.id, step)}
              />
              {!isLeaving &&
                (isActive ? lane.nodes : active ? [] : hintsOf(lane)).map((n) => (
                  <Mark
                    key={n.id}
                    node={n}
                    at={along(lane.samples, n.d)}
                    laneId={lane.id}
                    width={lane.width}
                    sink={lane.status === 'faded' || lane.status === 'stale' || lane.status === 'expired' ? 0.42 * Math.min(1, n.d / 2.6) : 0}
                    walked={isActive}
                   
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

        {/* circles only where a decision is made; drawn over the bands that meet there */}
        <Plazas plazas={layout.plazas} still={still} onHover={setHoveredPlaza} onPick={(p) => (onFocusScenario ? onFocusScenario(p.id) : p.branchIds[0] && onSwitch(p.branchIds[0]))} />
        <Ends lanes={layout.lanes} still={still} onHover={setHoveredId} onGo={onSeek} />
        <Stops lanes={layout.lanes} still={still} activeId={activeId} hereStep={here ? here.step : null} onGo={onSeek} />
        {active && rare && <RareStrand lane={active} years={rare} still={still} />}
        {/* the real you: always at now, never in a future */}
        <Walker layout={layout} target={null} state={real} still />
        {/* the ghost: the one that walks the futures, until the choice is made and it comes home */}
        {active && !arrivedHome && (
          <Walker
            layout={layout}
            target={homing ? null : target}
            state={walker}
            still={still}
            pale
            onRest={(laneId) => homing && laneId === null && setArrivedHome(true)}
          />
        )}
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

/** On a branch you are not on: at most two quiet marks of what happens there, where it is still stone. */
function hintsOf(lane: LaneSpec) {
  if (!lane.big) return []
  const onStone = lane.nodes.filter((n) => n.kind === 'event' && n.basis !== 'background' && n.d > 2.8 && n.d < lane.drawLen - 0.5 && lane.built[Math.round(n.d / DS)] >= 0.5)
  const sourced = onStone.filter((n) => n.basis === 'sourced')
  return (sourced.length ? sourced : onStone).slice(0, 2)
}

/** The rarest life on the active branch: a hair-thin dotted strand peeling off beside it. */
function RareStrand({ lane, years, still }: { lane: LaneSpec; years: BranchYear[]; still: boolean }) {
  const rare = useMemo(() => layoutRare(lane, years), [lane, years])
  const geometry = useMemo(() => {
    const g = createRibbon(rare.samples.length)
    writeRibbon(g, { samples: rare.samples, built: new Float32Array(rare.samples.length).fill(1), firm: () => 0, width: 0.09, sink: 0, phase: 0, thick: 0.05, start: 0, end: rare.len })
    return g
  }, [rare])
  const material = useMemo(() => {
    const m = ribbonMaterial()
    for (const k of ['uOpenTop', 'uOpenX', 'uOpenZ']) m.uniforms[k].value = new THREE.Color('#C4705A')
    m.uniforms.uDash.value = 3.4
    return m
  }, [])
  const grow = useRef(still ? 1e6 : 0)
  useEffect(() => () => (geometry.dispose(), material.dispose()), [geometry, material])
  useFrame((state, dt) => {
    grow.current = Math.min(rare.len + 1, grow.current + dt * Math.max(3, rare.len / 2.5))
    material.uniforms.uGrow.value = grow.current
    material.uniforms.uTime.value = still ? 0 : state.clock.elapsedTime
  })
  return <mesh geometry={geometry} material={material} frustumCulled={false} renderOrder={5} />
}

// ---------------------------------------------------------------- the camera

// A fixed, gentle, near-isometric gaze. Only the point it rests on and how closely it looks change.
const gazeParam = typeof location !== 'undefined' ? new URLSearchParams(location.search).get('gaze') : null
const GAZE = (gazeParam === '1' ? new THREE.Vector3(1, 0.35, 0.3) : gazeParam === '2' ? new THREE.Vector3(-0.4, 1.6, 1) : new THREE.Vector3(1, 0.92, 1)).normalize() // ?gaze=1|2: only for inspecting joins and ends
const RIGHT = new THREE.Vector3(GAZE.z, 0, -GAZE.x).normalize()
const UP = new THREE.Vector3(0, 1, 0).addScaledVector(GAZE, -GAZE.y).normalize()

function Rig({ layout, walker, following, close, downhill, view, insets, still, onWalking }: { downhill: boolean; close: boolean; layout: WorldLayout; walker: React.RefObject<WalkerState>; following: boolean; view: React.RefObject<View>; insets: Insets; still: boolean; onWalking?: (moving: boolean) => void }) {
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
      // a small decision is a short thing: come in close, so its offshoot fills the view rather than hiding under the figure
      wantZoom = close ? Math.max(30, Math.min(84, Math.min(safeW / 13, safeH / 8))) : Math.max(20, Math.min(58, Math.min(safeW / 22, safeH / 12)))
      fx = insets.left + safeW * 0.36
      fy = insets.top + safeH * (downhill ? 0.3 : 0.64)
    } else {
      want.copy(fit.centre)
      wantZoom = Math.max(7, Math.min(46, Math.min(safeW / fit.w, safeH / fit.h)))
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
