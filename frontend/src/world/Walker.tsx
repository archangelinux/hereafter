import { useRef, type RefObject } from 'react'
import * as THREE from 'three'
import { useFrame } from '@react-three/fiber'
import { along, type LaneSpec, type Sample, type WorldLayout } from './layout'
import { figureArm, figureBody, figureFoot, figureHead, figureRing, softMaterial, swell } from './soft'

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

// a soft, slightly darker ellipse directly under the figure: small, and soft at its edge
function shadowTexture() {
  const size = 64
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = size
  const ctx = canvas.getContext('2d')!
  const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2)
  g.addColorStop(0, 'rgba(150, 120, 100, 0.34)')
  g.addColorStop(0.55, 'rgba(150, 120, 100, 0.18)')
  g.addColorStop(1, 'rgba(150, 120, 100, 0)')
  ctx.fillStyle = g
  ctx.fillRect(0, 0, size, size)
  const t = new THREE.CanvasTexture(canvas)
  t.colorSpace = THREE.SRGBColorSpace
  return t
}
let contact: THREE.MeshBasicMaterial | null = null
const contactMaterial = () => (contact ??= new THREE.MeshBasicMaterial({ map: shadowTexture(), transparent: true, toneMapped: false, depthWrite: false }))
const disc = new THREE.PlaneGeometry(0.46, 0.36).rotateX(-Math.PI / 2)
const ringMaterial = new THREE.MeshBasicMaterial({ color: '#E2917A', toneMapped: false })

interface Props {
  /** the ghost is drawn pale: the real figure never leaves now */
  pale?: boolean
  layout: WorldLayout
  target: { lane: LaneSpec; d: number; steps: number } | null // where the reader is (and how many steps away that was); null means now
  onRest?: (laneId: string | null, d: number) => void // it has come to rest exactly on its target
  state: RefObject<WalkerState>
  still: boolean
}

/**
 * The only figure in the world. It idles at now, and when the reader moves through a branch it
 * WALKS there along the ribbon: back to the fork if it has to change branch, then out along the
 * new one. A procedural walk: a small bob, feet that step, a lean into the way it is going.
 */
export function Walker({ layout, target, state, still, onRest, pale = false }: Props) {
  const skin = softMaterial(pale ? 0.42 : 1)
  const root = useRef<THREE.Group>(null)
  const body = useRef<THREE.Group>(null)
  const head = useRef<THREE.Mesh>(null)
  const footL = useRef<THREE.Mesh>(null)
  const footR = useRef<THREE.Mesh>(null)
  const ring = useRef<THREE.Mesh>(null)
  const armL = useRef<THREE.Mesh>(null)
  const armR = useRef<THREE.Mesh>(null)
  const stride = useRef(0)
  const vel = useRef(0) // along the path, signed
  const gaitAmp = useRef(0)
  const rested = useRef<string>('')
  const cruise = useRef(1.5)
  const lastTarget = useRef('')
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
      // ONE PRESS, ONE STEP. It moves only because the cursor moved: at a calm pace, easing out of rest and
      // into rest, through every step between in order, and it STOPS exactly on the target. A new target
      // mid-walk simply bends the same motion toward it; an earlier one turns it round to walk back.
      const goal = s.laneId === wantLane ? wantD : 0
      const gap = goal - s.d
      const key = `${wantLane}:${wantD.toFixed(3)}`
      if (key !== lastTarget.current) {
        lastTarget.current = key
        const hops = Math.max(1, s.laneId === wantLane ? (target?.steps ?? 1) : 3)
        // about a second and a half for one step whatever its length; several steps go quicker each, never rushed
        cruise.current = Math.max(0.5, Math.abs(gap) / (0.95 + 0.42 * (hops - 1)))
      }
      if (Math.abs(gap) > 0.004 || Math.abs(vel.current) > 0.02) {
        const accel = cruise.current / 0.45
        const braking = Math.sqrt(2 * accel * Math.abs(gap)) // the most it may be doing and still stop ON the mark
        const want = Math.sign(gap) * Math.min(cruise.current, braking)
        const dv = want - vel.current
        vel.current += Math.sign(dv) * Math.min(Math.abs(dv), accel * 1.6 * dt)
        let move = vel.current * dt
        if (Math.sign(gap) === Math.sign(move) && Math.abs(move) >= Math.abs(gap)) {
          move = gap // never past the target
          vel.current = 0
        }
        s.d += move
        speed = Math.abs(vel.current)
        if (Math.abs(goal - s.d) < 0.004 && Math.abs(vel.current) < 0.06) {
          s.d = goal
          vel.current = 0
          speed = 0
        }
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
      // on the band's top surface, at its centreline (a weathered band has settled a little)
      const settled = lane && lane.status !== 'open' && lane.status !== 'merged' ? 0.42 * Math.min(1, s.d / 2.6) : 0
      s.x = p.x
      s.y = p.y - settled
      s.z = p.z
      if (speed > 0.05) heading = p.heading + (vel.current < 0 ? Math.PI : 0) // it faces the way it walks: along the path, or back along it
      // at rest it keeps facing the way it last walked; it never snaps round on its own
    }
    s.moving = speed > 0.03 || !!hop.current
    // come to rest exactly on the target: say so, once
    const restKey = `${s.laneId}:${s.d.toFixed(3)}`
    if (!s.moving && s.laneId === wantLane && Math.abs(s.d - wantD) < 0.005 && rested.current !== restKey) {
      rested.current = restKey
      onRest?.(s.laneId, s.d)
    }
    if (s.moving) rested.current = ''

    // turn toward where it is going, the short way round
    let turn = heading - facing.current
    while (turn > Math.PI) turn -= 2 * Math.PI
    while (turn < -Math.PI) turn += 2 * Math.PI
    facing.current += still ? turn : turn * Math.min(1, dt * 6)

    const t = clock.clock.elapsedTime
    // A proper little walk. The cycle is driven by distance covered, so the feet do not skate; each foot slides
    // forward and back ALONG the way it walks, in opposite phase, lifting a touch only as it swings forward.
    // At rest the amplitude eases to nothing: feet side by side under the body, arms down, quite still.
    stride.current += (speed * dt * (2 * Math.PI)) / 0.34
    gaitAmp.current = still ? 0 : THREE.MathUtils.damp(gaitAmp.current, speed > 0.05 ? Math.min(1, speed / 0.8) : 0, 7, dt)
    const gait = gaitAmp.current
    const ph = stride.current
    g.position.set(s.x, s.y + (s.laneId ? 0 : 0.02) + (still ? 0 : swell(s.x, s.z, t)), s.z)
    g.rotation.y = -facing.current
    if (body.current) {
      body.current.position.y = gait * (0.5 - 0.5 * Math.cos(ph * 2)) * 0.012 // one small bob to each step
      body.current.rotation.x = THREE.MathUtils.damp(body.current.rotation.x, -gait * 0.1, 6, dt) // leaning a touch into it
      body.current.rotation.z = 0
    }
    // forward is -z in the figure's own frame. Feet stay flat and pointed forward: they slide
    // forward and back in opposite phase and lift a little only while swinging through. Nothing rotates.
    const lift = 0.028
    const reach = 0.06
    if (pale) {
      // the ghost floats: it hovers a little off the path and its hem drifts
      g.position.y += 0.22 + Math.sin(t * 0.9) * 0.05
    }
    if (footL.current) {
      footL.current.position.set(-0.06, 0.04 + gait * Math.max(0, Math.sin(ph)) * lift, -gait * Math.cos(ph) * reach)
      footL.current.rotation.set(0, 0, 0)
    }
    if (footR.current) {
      footR.current.position.set(0.06, 0.04 + gait * Math.max(0, -Math.sin(ph)) * lift, gait * Math.cos(ph) * reach)
      footR.current.rotation.set(0, 0, 0)
    }
    // arms swing opposite to their foot, small, and hang still at rest
    if (armL.current) armL.current.rotation.set(-gait * Math.cos(ph) * 0.35, 0, -0.32)
    if (armR.current) armR.current.rotation.set(gait * Math.cos(ph) * 0.35, 0, 0.32)
    if (head.current) head.current.rotation.y = 0
    if (ring.current) {
      // on a path: the ring marks exactly where you stand on it, no wider than the path itself
      const on = s.laneId ? lanes.current.get(s.laneId) : null
      ring.current.visible = !!on && !hop.current
      if (on) ring.current.scale.setScalar(Math.max(0.6, Math.min(1.25, (on.width * 0.56) / (0.27 * 1.45))))
    }
  })

  return (
    <group ref={root} scale={2.05}>
      {/* the shadow and the ring share the figure's own anchor: its feet are the origin of this group */}
      <mesh geometry={disc} material={contactMaterial()} position={[0, 0.012, 0]} renderOrder={5} />
      <mesh ref={ring} geometry={figureRing()} material={ringMaterial} position={[0, 0.02, 0]} renderOrder={6} visible={false} />
      <mesh ref={footL} geometry={figureFoot()} material={skin} />
      <mesh ref={footR} geometry={figureFoot()} material={skin} />
      <group ref={body}>
        <mesh geometry={figureBody()} material={skin} />
        <mesh ref={armL} geometry={figureArm()} material={skin} position={[-0.105, 0.4, 0]} rotation={[0, 0, -0.32]} />
        <mesh ref={armR} geometry={figureArm()} material={skin} position={[0.105, 0.4, 0]} rotation={[0, 0, 0.32]} />
        <mesh ref={head} geometry={figureHead()} material={skin} position={[0, 0.585, 0]} />
      </group>
    </group>
  )
}
