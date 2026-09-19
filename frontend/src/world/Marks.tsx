import { useRef, useState, type RefObject } from 'react'
import * as THREE from 'three'
import { useFrame } from '@react-three/fiber'
import { Html } from '@react-three/drei'
import type { NodeSpec, Sample } from './layout'
import type { StoneFamily } from './palette'
import { milestoneGeometry, smallGateGeometry, softMaterial, swell } from './soft'
import type { WalkerState } from './Walker'

interface Props {
  node: NodeSpec
  at: Sample & { heading: number }
  laneId: string
  family: StoneFamily
  side: 1 | -1
  walked: boolean // on the branch you are on, background marks appear once the figure has passed them
  speaking: boolean
  pale: number
  still: boolean
  walker: RefObject<WalkerState>
  onPick: () => void
  onArrive: () => void
}

/**
 * An event is a small rounded marker stone beside the trail; a commit is a small rounded gate over
 * one stone. What rests on a published figure is solid; an estimate is the same form as a pale
 * ghost; background stays out of sight until walked past. A waypoint too: when the figure reaches
 * it, it lifts a little and settles. It never bounces.
 */
export function Mark({ node, at, laneId, family, side, walked, speaking, pale, still, walker, onPick, onArrive }: Props) {
  const group = useRef<THREE.Group>(null)
  const [hovered, setHovered] = useState(false)
  const [passed, setPassed] = useState(false)
  const reached = useRef(false)
  const lift = useRef(0)
  const commit = node.kind === 'commit'
  const ghost = node.basis === 'estimated'
  const quiet = node.basis === 'background' && !commit
  const off = commit ? 0 : -side * 0.62
  const x = at.x + Math.cos(at.heading) * off
  const z = at.z + Math.sin(at.heading) * off

  useFrame((state, dt) => {
    const w = walker.current
    if (!w) return
    if (quiet && walked) {
      const now = w.laneId === laneId && w.d > node.d - 1.2
      if (now !== passed) setPassed(now)
    }
    const g = group.current
    if (!g) return
    const here = w.laneId === laneId && Math.abs(w.d - node.d) < 0.6
    if (here && !reached.current) onArrive()
    reached.current = here
    lift.current = still ? 0 : THREE.MathUtils.damp(lift.current, here ? 0.16 : hovered ? 0.07 : 0, here ? 3 : 5, dt)
    g.position.y = at.y - (commit ? 0.1 : 0.12) + lift.current + (still ? 0 : swell(x, z, state.clock.elapsedTime))
  })

  if (quiet && !(walked && passed)) return <group ref={group} />
  return (
    <group ref={group} position={[x, at.y, z]} rotation={[0, -at.heading, 0]}>
      <mesh
        geometry={commit ? smallGateGeometry() : milestoneGeometry(family)}
        material={softMaterial((ghost ? 0.45 : 1) * pale)}
        scale={quiet ? 0.7 : 1}
        onClick={(e) => {
          if (e.delta > 6) return
          e.stopPropagation()
          onPick()
        }}
        onPointerOver={(e) => (e.stopPropagation(), setHovered(true), (document.body.style.cursor = 'pointer'))}
        onPointerOut={() => (setHovered(false), (document.body.style.cursor = ''))}
      />
      {(hovered || speaking) && (
        <Html position={[0, 0.8, 0]} zIndexRange={[9, 5]} style={{ pointerEvents: 'none' }}>
          <div className={`hw-note ${side === 1 ? 'hw-note--left' : ''}`}>
            <span className="hw-note__caption">
              {commit ? `your commit · ${node.caption}` : ghost ? `${node.caption} · an estimate` : node.basis === 'sourced' ? `${node.caption} · from a published figure` : node.caption}
            </span>
            <span className="hw-note__text">{node.label}</span>
          </div>
        </Html>
      )}
    </group>
  )
}
