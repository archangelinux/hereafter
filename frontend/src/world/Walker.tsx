import { useRef, type RefObject } from 'react'
import * as THREE from 'three'
import { useFrame } from '@react-three/fiber'
import { ink } from './palette'
import { along, type LaneSpec, type Sample, type WorldLayout } from './layout'
import { figureBody, figureFoot, figureHead, figureSatchel, figureScarf, figureScarfTail, softMaterial, swell } from './soft'

/** Where the figure is, shared with the camera and the landmarks. */
export interface WalkerState {
  laneId: string | null // null: standing on main, at now
  d: number
  x: number
  y: number
  z: number
  moving: boolean
}

export const newWalkerState = (): WalkerState => ({ laneId: null, d: 0, x: 0, y: 0, z: 0, moving: false })

const contact = new THREE.MeshBasicMaterial({ color: ink.contact, transparent: true, opacity: 0.45, toneMapped: false, depthWrite: false })
const disc = new THREE.CircleGeometry(0.22, 20).rotateX(-Math.PI / 2)

interface Props {
  layout: WorldLayout
  target: { lane: LaneSpec; d: number } | null // where the reader is; null means now
  state: RefObject<WalkerState>
  still: boolean
}

/**
 * The only figure in the world. It idles at now, and when the reader moves through a branch it
 * WALKS there along the ribbon: back to the fork if it has to change branch, then out along the
 * new one. A procedural walk: a small bob, feet that step, a lean into the way it is going.
 */
export function Walker({ layout, target, state, still }: Props) {
  const root = useRef<THREE.Group>(null)
  const body = useRef<THREE.Group>(null)
  const head = useRef<THREE.Mesh>(null)
  const footL = useRef<THREE.Mesh>(null)
  const footR = useRef<THREE.Mesh>(null)
  const tail = useRef<THREE.Mesh>(null)
  const stride = useRef(0)
  const facing = useRef(0)
  const hop = useRef<{ from: Sample; to: Sample; t: number; len: number } | null>(null)
  const lanes = useRef(new Map<string, LaneSpec>())
  lanes.current = new Map(layout.lanes.map((l) => [l.id, l]))

  useFrame((clock, dt) => {
    const s = state.current
    const g = root.current
    if (!s || !g) return
    const current = s.laneId ? (lanes.current.get(s.laneId) ?? null) : null
    if (s.laneId && !current) {
      s.laneId = null
      s.d = 0
    }
    const wantLane = target?.lane.id ?? null
    const wantD = target?.d ?? 0
    let heading = facing.current
    let speed = 0

    if (still) {
      s.laneId = wantLane
      s.d = wantD
      hop.current = null
    } else if (hop.current) {
      // between two forks that are not the same place: a short, slow glide across
      const h = hop.current
      h.t = Math.min(1, h.t + (dt * 5) / Math.max(1, h.len))
      const k = h.t * h.t * (3 - 2 * h.t)
      s.x = h.from.x + (h.to.x - h.from.x) * k
      s.z = h.from.z + (h.to.z - h.from.z) * k
      s.y = h.from.y + (h.to.y - h.from.y) * k + Math.sin(k * Math.PI) * 0.5
      heading = Math.atan2(h.to.x - h.from.x, -(h.to.z - h.from.z))
      speed = 2
      if (h.t >= 1) hop.current = null
    } else {
      const goal = s.laneId === wantLane ? wantD : 0
      const gap = goal - s.d
      if (Math.abs(gap) > 0.02) {
        // unhurried, but it does not dawdle over a long way
        speed = Math.min(9, Math.max(1.3, Math.abs(gap) * 0.85))
        const move = Math.sign(gap) * Math.min(Math.abs(gap), speed * dt)
        s.d += move
      } else if (s.laneId !== wantLane) {
        // at a fork: step across to where the other branch leaves from
        const from = current ? along(current.samples, 0) : { x: 0, y: 0, z: 0 }
        const next = wantLane ? lanes.current.get(wantLane) : null
        const to = next ? along(next.samples, 0) : { x: 0, y: 0, z: 0 }
        const len = Math.hypot(to.x - from.x, to.z - from.z)
        s.laneId = wantLane
        s.d = 0
        if (len > 0.6) hop.current = { from, to, t: 0, len }
      }
    }

    if (!hop.current) {
      const lane = s.laneId ? lanes.current.get(s.laneId) : null
      const p = lane ? along(lane.samples, s.d) : { x: 0, y: 0, z: 0, heading: 0 }
      s.x = p.x
      s.y = p.y
      s.z = p.z
      if (speed > 0) heading = p.heading + ((s.laneId === wantLane ? wantD : 0) < s.d ? Math.PI : 0)
      else if (!lane) heading = 0
    }
    s.moving = speed > 0

    // turn toward where it is going, the short way round
    let turn = heading - facing.current
    while (turn > Math.PI) turn -= 2 * Math.PI
    while (turn < -Math.PI) turn += 2 * Math.PI
    facing.current += still ? turn : turn * Math.min(1, dt * 6)

    const t = clock.clock.elapsedTime
    stride.current += dt * (speed > 0 ? 5 + Math.min(4, speed) : 0)
    const gait = speed > 0 ? 1 : 0
    const ph = stride.current
    g.position.set(s.x, s.y + 0.04 + (still ? 0 : swell(s.x, s.z, t)), s.z)
    g.rotation.y = -facing.current
    if (body.current) {
      body.current.position.y = gait * Math.abs(Math.sin(ph)) * 0.045 + (1 - gait) * Math.sin(t * 1.1) * 0.008
      body.current.rotation.x = THREE.MathUtils.damp(body.current.rotation.x, -gait * 0.2, 5, dt) // leaning into the way it goes
      body.current.rotation.z = gait * Math.sin(ph) * 0.05
    }
    if (tail.current) tail.current.rotation.x = THREE.MathUtils.damp(tail.current.rotation.x, gait * (0.9 + Math.sin(ph * 0.5) * 0.25) + (1 - gait) * (0.15 + Math.sin(t * 0.8) * 0.08), 4, dt) // the scarf streams out behind
    if (head.current) head.current.rotation.y = (1 - gait) * Math.sin(t * 0.35) * 0.5 // looking about, at rest
    if (footL.current) footL.current.position.set(-0.06, 0.04 + gait * Math.max(0, Math.sin(ph)) * 0.07, -gait * Math.cos(ph) * 0.09)
    if (footR.current) footR.current.position.set(0.06, 0.04 + gait * Math.max(0, -Math.sin(ph)) * 0.07, gait * Math.cos(ph) * 0.09)
  })

  return (
    <group ref={root} scale={1.45}>
      <mesh geometry={disc} material={contact} position={[0.03, 0.012, 0.03]} />
      <mesh ref={footL} geometry={figureFoot()} material={softMaterial(1)} />
      <mesh ref={footR} geometry={figureFoot()} material={softMaterial(1)} />
      <group ref={body}>
        <mesh geometry={figureBody()} material={softMaterial(1)} />
        <mesh geometry={figureSatchel()} material={softMaterial(1)} position={[0.13, 0.2, 0.02]} />
        <mesh geometry={figureScarf()} material={softMaterial(1)} position={[0, 0.47, 0]} />
        <mesh ref={tail} geometry={figureScarfTail()} material={softMaterial(1)} position={[0, 0.47, 0.085]} />
        <mesh ref={head} geometry={figureHead()} material={softMaterial(1)} position={[0, 0.6, 0]} />
      </group>
    </group>
  )
}
