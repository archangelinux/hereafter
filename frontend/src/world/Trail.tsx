import { useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { useFrame, type ThreeEvent } from '@react-three/fiber'
import { ink } from './palette'
import { hash01, type LaneSpec, type StoneSpec } from './layout'
import { isletGeometry, mossGeometry, puffGeometry, ringGeometry, softMaterial, stoneGeometry, swell, thinStoneGeometry } from './soft'

// ---------------------------------------------------------------- one stepping stone

type Look =
  | { kind: 'stone'; family: 'past' | 'open' | 'ruin'; tilt: number; lean: number; sink: number; adrift: number }
  | { kind: 'thin'; mist: 0 | 1; opacity: number }
  | { kind: 'ring'; opacity: number }
  | { kind: 'none' }

const lookKey = (l: Look) => JSON.stringify(l)
const easeInOut = (t: number) => {
  const v = Math.max(0, Math.min(1, t))
  return v < 0.5 ? 4 * v * v * v : 1 - Math.pow(-2 * v + 2, 3) / 2
}

const ringMaterials = new Map<string, THREE.MeshBasicMaterial>()
function ringMaterial(opacity: number) {
  const key = opacity.toFixed(2)
  let m = ringMaterials.get(key)
  if (!m) ringMaterials.set(key, (m = new THREE.MeshBasicMaterial({ color: ink.outline, toneMapped: false, transparent: true, opacity, depthWrite: false })))
  return m
}

interface StoneProps {
  stone: StoneSpec
  look: Look
  delayMs: number
  durationMs: number
  fresh: boolean // laid while you watch: it floats up into place rather than simply being there
  active: boolean
  pale: number // 1 = itself; less when it belongs to a branch you are not on, or to an example
  still: boolean
}

/**
 * A stone shows its look at once when first laid. When its look changes later (a path is chosen,
 * or left behind) it waits its turn, then settles into the new state: floaty, eased, never bouncing.
 */
function Stone({ stone, look, delayMs, durationMs, fresh, active, pale, still }: StoneProps) {
  const group = useRef<THREE.Group>(null)
  const [shown, setShown] = useState<Look>(fresh && !still ? { kind: 'none' } : look)
  const anim = useRef<number | null>(null)
  const rising = useRef(false)
  const lift = useRef(0)
  const at = useRef({ x: stone.x, y: stone.y, z: stone.z })
  const key = lookKey(look)

  useEffect(() => {
    if (lookKey(shown) === key) return
    if (still) {
      setShown(look)
      return
    }
    const id = setTimeout(() => {
      anim.current = performance.now()
      rising.current = shown.kind === 'none' || (look.kind === 'stone' && look.family === 'past')
      setShown(look)
    }, delayMs)
    return () => clearTimeout(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, still])

  useFrame((state, dt) => {
    const g = group.current
    if (!g) return
    const p = anim.current === null ? 1 : easeInOut((performance.now() - anim.current) / durationMs)
    if (anim.current !== null && p >= 1) anim.current = null
    lift.current = still ? (active ? 0.14 : 0) : THREE.MathUtils.damp(lift.current, active ? 0.14 : 0, 5, dt)
    // if the trail takes a new course, the stone drifts to its new place
    const a = at.current
    if (still) Object.assign(a, { x: stone.x, y: stone.y, z: stone.z })
    else {
      a.x = THREE.MathUtils.damp(a.x, stone.x, 1.6, dt)
      a.y = THREE.MathUtils.damp(a.y, stone.y, 1.6, dt)
      a.z = THREE.MathUtils.damp(a.z, stone.z, 1.6, dt)
    }

    let x = a.x
    let y = a.y + lift.current + (still ? 0 : swell(a.x, a.z, state.clock.elapsedTime))
    let z = a.z
    let rx = 0
    let rz = 0
    let scale = stone.r
    if (rising.current) {
      // the stone floats up out of the mist and settles
      y += (p - 1) * 1.4
      scale *= 0.55 + 0.45 * p
    }
    if (shown.kind === 'stone' && shown.family === 'ruin') {
      const q = rising.current ? 1 : p
      y -= shown.sink * q
      rx = shown.tilt * q
      rz = shown.lean * q
      x += Math.cos(stone.heading) * shown.adrift * q
      z += Math.sin(stone.heading) * shown.adrift * q
    }
    g.position.set(x, y, z)
    g.rotation.set(rx, 0, rz)
    g.scale.set(scale, Math.min(1, scale * 2), scale)
  })

  if (shown.kind === 'none') return <group ref={group} />
  return (
    <group ref={group} position={[stone.x, stone.y, stone.z]} scale={stone.r}>
      {shown.kind === 'stone' && <mesh geometry={stoneGeometry(shown.family)} material={softMaterial(pale)} />}
      {shown.kind === 'thin' && <mesh geometry={thinStoneGeometry(shown.mist)} material={softMaterial(shown.opacity * pale)} />}
      {shown.kind === 'ring' && <mesh geometry={ringGeometry()} material={ringMaterial(shown.opacity * pale)} />}
    </group>
  )
}

function lookFor(lane: LaneSpec, s: StoneSpec, leaving: boolean): Look {
  if (leaving) return { kind: 'none' }
  const closed = lane.status === 'faded' || lane.status === 'stale' || lane.status === 'expired'
  if (lane.status !== 'open' && s.d > lane.drawLen) return { kind: 'none' }
  if (lane.status === 'merged' && s.d <= lane.stoneLen) {
    // a chosen branch comes in out of the mist, then it is main's own stone
    if (s.d < 1.3) return { kind: 'thin', mist: 1, opacity: 0.55 }
    return { kind: 'stone', family: 'past', tilt: 0, lean: 0, sink: 0, adrift: 0 }
  }
  const b = s.built
  if (!closed) {
    if (b >= 0.6) return { kind: 'stone', family: 'open', tilt: 0, lean: 0, sink: 0, adrift: 0 }
    if (b >= 0.3) return b > 0.45 ? { kind: 'thin', mist: 0, opacity: 0.85 } : { kind: 'thin', mist: 1, opacity: 0.6 }
    if (b >= 0.07) return { kind: 'ring', opacity: b > 0.18 ? 0.9 : 0.5 }
    return { kind: 'none' }
  }
  // faded / stale: what was built stays, weathered; a few stones have sunk or drifted out of line
  const r = hash01(`${lane.id}:${s.index}`)
  if (b < 0.07) return { kind: 'none' }
  if (b < 0.3) return { kind: 'ring', opacity: 0.35 }
  const fromEnd = lane.drawLen - s.d
  if (lane.breaks) {
    // stale: the trail has broken off. A gap, then the last stones going down.
    if (fromEnd > 0.75 && fromEnd < 1.5) return { kind: 'none' }
    if (fromEnd <= 0.75) return { kind: 'stone', family: 'ruin', tilt: 0.5, lean: -0.35, sink: 0.75, adrift: 0.5 }
  }
  if (s.index > 4 && r < 0.1) return { kind: 'none' }
  const worn = r > 0.6
  return {
    kind: 'stone',
    family: 'ruin',
    tilt: worn ? (r - 0.8) * 0.5 : 0,
    lean: worn ? (hash01(`${lane.id}:lean:${s.index}`) - 0.5) * 0.25 : 0,
    sink: worn ? 0.08 + r * 0.14 : 0,
    adrift: worn ? (hash01(`${lane.id}:adrift:${s.index}`) - 0.5) * 0.7 : 0,
  }
}

// ---------------------------------------------------------------- things that ride the swell

export function Bobbing({ at, still, breathe = 0, children }: { at: [number, number, number]; still: boolean; breathe?: number; children: React.ReactNode }) {
  const ref = useRef<THREE.Group>(null)
  useFrame((state) => {
    if (!ref.current || still) return
    const t = state.clock.elapsedTime
    ref.current.position.y = at[1] + swell(at[0], at[2], t)
    if (breathe) ref.current.scale.setScalar(1 + breathe * Math.sin(t * 0.5 + at[0]))
  })
  return (
    <group ref={ref} position={at}>
      {children}
    </group>
  )
}

// ---------------------------------------------------------------- a whole branch of the delta

const hidden = new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false })
const hitGeometry = new THREE.SphereGeometry(0.8, 6, 5)

interface Props {
  spec: LaneSpec
  fresh: boolean
  leaving: boolean
  active: boolean
  activeStep: number | null
  dim: boolean // you are on another branch: this one recedes
  still: boolean
  onGone: () => void
  onHover: (over: boolean) => void
  onSwitch: () => void
  onSeek: (step: number) => void
}

export function Trail({ spec, fresh, leaving, active, activeStep, dim, still, onGone, onHover, onSwitch, onSeek }: Props) {
  const merged = spec.status === 'merged'
  const ruin = spec.status === 'faded' || spec.status === 'stale' || spec.status === 'expired'
  const family = merged ? 'past' : ruin ? 'ruin' : 'open'
  const stagger = leaving ? 22 : merged ? 60 : fresh ? 45 : 80
  const duration = merged ? 1300 : ruin ? 2400 : 1100
  const pale = (dim ? 0.38 : 1) * (spec.example ? 0.8 : 1)
  const last = spec.stones.length - 1

  // an undone branch draws back stone by stone from its far end, then is gone
  useEffect(() => {
    if (!leaving) return
    const id = setTimeout(onGone, still ? 0 : spec.stones.length * 22 + 1200)
    return () => clearTimeout(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [leaving])

  // soft islets under the well-built stretches; the trail rests on them, then drifts on alone
  const islets = useMemo(() => {
    const out: { key: string; at: [number, number, number]; scale: number; variant: 0 | 1 | 2 }[] = []
    if (merged || spec.small) return out // what runs beside main, or only a little way, needs no ground of its own
    const firm = ruin ? 0.45 : 0.6
    for (let i = ruin ? 9 : 4; i < spec.stones.length; i += ruin ? 9 : 7) {
      const s = spec.stones[i]
      if (s.d > spec.drawLen || (!merged && s.built < firm)) break
      if (merged && s.d > spec.stoneLen) break
      const r = hash01(`${spec.id}:islet:${i}`)
      out.push({ key: `i${i}`, at: [s.x, s.y - 0.36, s.z], scale: (ruin ? 0.8 : 1.0) + r * 0.5, variant: (i % 3) as 0 | 1 | 2 })
    }
    return out
  }, [spec, ruin, merged])

  // where the stones give out, a few soft banks of mist: punctuation, not a trail
  const puffs = useMemo(() => {
    if (spec.status !== 'open') return []
    const out: { key: string; at: [number, number, number]; scale: number }[] = []
    let beyond = 0
    spec.stones.forEach((s, i) => {
      if (s.built >= 0.45 || out.length >= 4) return
      if (s.built < 0.07 && ++beyond > 14) return
      if (i % 8 !== 0) return
      const r = hash01(`${spec.id}:puff:${i}`)
      out.push({ key: `p${i}`, at: [s.x + (r - 0.5) * 1.6, s.y - 0.5 - r * 0.4, s.z + (r - 0.5)], scale: 0.45 + (1 - s.built) * 0.6 * (0.7 + r * 0.6) })
    })
    return out
  }, [spec])

  const moss = useMemo(() => {
    if (!ruin) return []
    return spec.stones
      .filter((s) => s.d < spec.drawLen - 0.8 && s.built >= 0.3 && hash01(`${spec.id}:moss:${s.index}`) < 0.2)
      .map((s) => ({ key: `m${s.index}`, at: [s.x + 0.12, s.y - 0.02, s.z + 0.1] as [number, number, number], scale: 0.7 + hash01(`${spec.id}:mosssize:${s.index}`) }))
  }, [spec, ruin])

  const hits = useMemo(() => spec.stones.filter((s, i) => i % 2 === 0 && (spec.status === 'open' || s.d <= spec.drawLen)), [spec])
  const click = (s: StoneSpec) => (e: ThreeEvent<MouseEvent>) => {
    if (e.delta > 6) return // that was a drag
    e.stopPropagation()
    if (active) onSeek(Math.max(0, s.step))
    else onSwitch()
  }

  return (
    <group>
      {spec.stones.map((s) => (
        <Stone
          key={s.index}
          stone={s}
          look={lookFor(spec, s, leaving)}
          delayMs={(leaving ? last - s.index : s.index) * stagger}
          durationMs={duration}
          fresh={fresh}
          active={active && s.step === activeStep}
          pale={pale}
          still={still}
        />
      ))}

      {!leaving &&
        islets.map((i) => (
          <Bobbing key={i.key} at={i.at} still={still}>
            <mesh geometry={isletGeometry(family, i.variant)} material={softMaterial(pale)} scale={[i.scale, i.scale * 0.9, i.scale]} />
          </Bobbing>
        ))}

      {!leaving &&
        !dim &&
        puffs.map((p) => (
          <Bobbing key={p.key} at={p.at} still={still} breathe={0.06}>
            <group scale={p.scale}>
              <mesh geometry={puffGeometry('mist')} material={softMaterial(1)} scale={[1, 0.6, 1]} />
              <mesh geometry={puffGeometry('mist')} material={softMaterial(1)} position={[0.85, -0.1, 0.2]} scale={[0.65, 0.42, 0.65]} />
              <mesh geometry={puffGeometry('mist')} material={softMaterial(1)} position={[-0.8, -0.12, -0.1]} scale={[0.55, 0.36, 0.55]} />
            </group>
          </Bobbing>
        ))}

      {!leaving && moss.map((m) => <mesh key={m.key} geometry={mossGeometry()} material={softMaterial(pale)} position={m.at} scale={m.scale} />)}

      {/* a generous invisible band along the trail, so rings and mist are as easy to pick as stone */}
      {!leaving &&
        hits.map((s) => (
          <mesh
            key={s.index}
            geometry={hitGeometry}
            material={hidden}
            position={[s.x, s.y - 0.1, s.z]}
            onClick={click(s)}
            onPointerOver={(e) => (e.stopPropagation(), onHover(true), (document.body.style.cursor = 'pointer'))}
            onPointerOut={() => (onHover(false), (document.body.style.cursor = ''))}
          />
        ))}
    </group>
  )
}

/** The rarest life on a branch: a faint trail of tiny ring-stones peeling off beside it. */
export function RareTrail({ points, still }: { points: { x: number; y: number; z: number }[]; still: boolean }) {
  const [count, setCount] = useState(still ? points.length : 0)
  useEffect(() => {
    if (still) return setCount(points.length)
    setCount(0)
    const id = setInterval(() => setCount((c) => (c >= points.length ? (clearInterval(id), c) : c + 1)), 70)
    return () => clearInterval(id)
  }, [points, still])
  return (
    <group>
      {points.slice(0, count).map((p, i) => (
        <Bobbing key={i} at={[p.x, p.y + 0.02, p.z]} still={still}>
          <mesh geometry={ringGeometry()} material={ringMaterial(0.95)} scale={i % 2 ? 0.22 : 0.3} />
        </Bobbing>
      ))}
    </group>
  )
}
