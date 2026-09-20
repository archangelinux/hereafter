import { useEffect, useMemo, useRef } from 'react'
import * as THREE from 'three'
import { useFrame, type ThreeEvent } from '@react-three/fiber'
import { DS, hash01, stepAtD, type LaneSpec, type Sample } from './layout'
import { createRibbon, ribbonMaterial, writeRibbon } from './ribbon'

const easeInOut = (t: number) => {
  const v = Math.max(0, Math.min(1, t))
  return v < 0.5 ? 4 * v * v * v : 1 - Math.pow(-2 * v + 2, 3) / 2
}
const smooth = (a: number, b: number, v: number) => {
  const t = Math.max(0, Math.min(1, (v - a) / (b - a)))
  return t * t * (3 - 2 * t)
}

const MORPH_S = 3.2 // a band swinging to a new course
const FIRM_S = 3.0 // turning to main's stone, from the fork outward
const WEATHER_S = 3.6
const hidden = new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false })
const ones = new Map<number, Float32Array>()
const ONES = (n: number) => ones.get(n) ?? (ones.set(n, new Float32Array(n).fill(1)), ones.get(n)!)

interface Props {
  spec: LaneSpec
  fresh: boolean // first seen after the first paint: it grows outward along its course
  leaving: boolean // undone: it draws back into its fork, then is gone
  active: boolean
  dim: boolean
  still: boolean
  onGone: () => void
  onHover: (over: boolean) => void
  onSwitch: () => void
  onSeek: (step: number) => void
}

/**
 * One branch: one continuous band. Everything that can happen to it (growing, swinging to a new
 * course, firming into main's stone, weathering, breaking off, drawing back) happens to the same
 * band, continuously.
 */
export function Band({ spec, fresh, leaving, active, dim, still, onGone, onHover, onSwitch, onSeek }: Props) {
  const count = spec.samples.length
  const geometry = useMemo(() => createRibbon(count), [count])
  const hitGeometry = useMemo(() => createRibbon(count), [count])
  const material = useMemo(() => ribbonMaterial(), [])
  useEffect(() => () => (geometry.dispose(), hitGeometry.dispose()), [geometry, hitGeometry])
  useEffect(() => () => material.dispose(), [material])
  const hovered = useRef(false)

  const merged = spec.status === 'merged'
  const closed = spec.status === 'faded' || spec.status === 'stale' || spec.status === 'expired'
  const endTarget = spec.status === 'open' ? spec.fullLen + 1 : spec.drawLen
  const pale = spec.example ? 0.8 : 1

  const a = useRef({
    shown: spec.samples as Sample[],
    from: null as Sample[] | null,
    morph: 1,
    firm: merged ? 1 : 0,
    weather: closed ? 1 : 0,
    grow: fresh && !still ? 0 : spec.fullLen + 2,
    end: endTarget,
    lift: 0,
    lit: 0,
    litDrawn: 0,
    slim: 0,
    dimmed: pale,
    dirty: true,
    gone: false,
  })

  // a new course for the same branch: swing to it rather than jump
  const lastSpec = useRef(spec)
  useEffect(() => {
    const s = a.current
    if (lastSpec.current !== spec) {
      const moved = lastSpec.current.samples.length === spec.samples.length && spec.samples.some((p, i) => i % 8 === 0 && Math.hypot(p.x - s.shown[i].x, p.z - s.shown[i].z) > 0.05)
      if (moved && !still) {
        s.from = s.shown
        s.morph = 0
      } else s.shown = spec.samples
      lastSpec.current = spec
      s.dirty = true
    }
  }, [spec, still])

  const phase = useMemo(() => hash01(spec.id) * 6.28, [spec.id])

  useFrame((state, dt) => {
    const s = a.current
    const step = (value: number, target: number, seconds: number) => (still ? target : value < target ? Math.min(target, value + dt / seconds) : Math.max(target, value - dt / seconds))

    if (s.morph < 1) {
      s.morph = still ? 1 : Math.min(1, s.morph + dt / MORPH_S)
      const k = easeInOut(s.morph)
      const from = s.from!
      s.shown = spec.samples.map((p, i) => ({ x: from[i].x + (p.x - from[i].x) * k, y: from[i].y + (p.y - from[i].y) * k, z: from[i].z + (p.z - from[i].z) * k }))
      if (s.morph >= 1) {
        s.shown = spec.samples
        s.from = null
      }
      s.dirty = true
    }
    s.lit = still ? (active ? 1 : 0) : THREE.MathUtils.damp(s.lit, active ? 1 : 0, 2.5, dt)
    if (Math.abs(s.lit - (active ? 1 : 0)) < 0.01) s.lit = active ? 1 : 0
    const slim = still ? (dim ? 1 : 0) : THREE.MathUtils.damp(s.slim, dim ? 1 : 0, 3, dt)
    if (Math.abs(slim - s.slim) > 0.002) s.dirty = true
    s.slim = Math.abs(slim - (dim ? 1 : 0)) < 0.004 ? (dim ? 1 : 0) : slim
    const firm = step(s.firm, merged ? 1 : 0, FIRM_S)
    const weather = step(s.weather, closed ? 1 : 0, WEATHER_S)
    if (firm !== s.firm || weather !== s.weather) s.dirty = true
    s.firm = firm
    s.weather = weather

    if (Math.abs(s.lit - s.litDrawn) > 0.02 || (s.lit !== s.litDrawn && (s.lit < 0.01 || s.lit > 0.99))) s.dirty = true
    // its end is part of its shape: while the end is still settling, the nose moves with it
    const endNow = still ? endTarget : THREE.MathUtils.damp(s.end, endTarget, 1.1, dt)
    if (Math.abs(endNow - s.end) > 0.003) s.dirty = true
    s.end = Math.abs(endNow - endTarget) < 0.004 ? endTarget : endNow
    if (s.dirty) {
      s.litDrawn = s.lit
      const floor = s.lit
      const front = easeInOut(s.firm) * (spec.stoneLen + 3)
      writeRibbon(geometry, {
        samples: s.shown,
        built: floor > 0 ? spec.built.map((b, i) => Math.max(b, floor * (0.5 + 0.22 * b) * (1 - smooth(0.9, 1, (i * DS) / spec.fullLen)))) : spec.built,
        fade: spec.fade,
        firm: (d) => (s.firm <= 0 ? 0 : (1 - smooth(front - 3, front, d)) * (1 - smooth(spec.stoneLen - 0.7, spec.stoneLen + 0.7, d))),
        width: spec.width,
        sink: 0.42 * easeInOut(s.weather),
        phase,
        slim: s.slim,
        start: spec.fromD > 0 ? spec.fromD : -1,
        end: Math.min(s.end, spec.fullLen),
        land: true, // every path ends on its platform (see LaneSpec.endD)
      })
      writeRibbon(hitGeometry, { samples: s.shown, built: ONES(count), firm: () => 0, width: Math.max(1.5, spec.width * 2.2), sink: 0, phase: 0 })
      s.dirty = false
    }

    // growing out, drawing back, settling to its end
    const growTarget = leaving ? -0.5 : spec.fullLen + 2
    const rate = Math.max(4, spec.fullLen / 2.6)
    s.grow = still ? growTarget : s.grow < growTarget ? Math.min(growTarget, s.grow + rate * dt) : Math.max(growTarget, s.grow - rate * 1.4 * dt)
    if (leaving && s.grow <= 0 && !s.gone) {
      s.gone = true
      onGone()
    }
    s.lift = 0 // a branch never moves under the pointer: hovering only warms its colour
    const dimTarget = pale
    s.dimmed = still ? dimTarget : THREE.MathUtils.damp(s.dimmed, dimTarget, 3, dt)

    const u = material.uniforms
    u.uTime.value = still ? 0 : state.clock.elapsedTime
    u.uWeather.value = easeInOut(s.weather)
    u.uGrow.value = s.grow
    u.uFrom.value = spec.fromD
    u.uEnd.value = s.end + 0.01
    u.uLift.value = s.lift
    u.uPale.value = s.dimmed
    u.uBreak.value = spec.breaks ? 1 : 0
    u.uRecede.value = s.slim
    u.uActive.value = s.lit
    u.uReveal.value = s.lit
    u.uHead.value = spec.status === 'open' ? spec.headD : 1e6
  })

  // where a click on the band falls along it
  const stepAt = (point: THREE.Vector3) => {
    const s = a.current.shown
    let best = 0
    let bestD = Infinity
    for (let i = 0; i < s.length; i += 2) {
      const d = (s[i].x - point.x) ** 2 + (s[i].z - point.z) ** 2
      if (d < bestD) {
        bestD = d
        best = i
      }
    }
    return { d: best * DS, step: stepAtD(spec, best * DS) }
  }
  const within = (d: number) => d <= endTarget + 0.5 && d >= spec.fromD
  const onClick = (e: ThreeEvent<MouseEvent>) => {
    if (e.delta > 6) return // that was a drag
    const hit = stepAt(e.point)
    if (!within(hit.d)) return
    e.stopPropagation()
    if (active) onSeek(hit.step)
    else onSwitch()
  }

  return (
    <group>
      <mesh geometry={geometry} material={material} frustumCulled={false} renderOrder={closed ? 1 : 2} />
      <mesh
        geometry={hitGeometry}
        material={hidden}
        frustumCulled={false}
        onClick={onClick}
        onPointerOver={(e) => {
          if (!within(stepAt(e.point).d)) return
          e.stopPropagation()
          hovered.current = true
          onHover(true)
          document.body.style.cursor = 'pointer'
        }}
        onPointerOut={() => {
          hovered.current = false
          onHover(false)
          document.body.style.cursor = ''
        }}
      />
    </group>
  )
}
