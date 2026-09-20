import { useRef, useState, type RefObject } from 'react'
import * as THREE from 'three'
import { useFrame } from '@react-three/fiber'
import { Html } from '@react-three/drei'
import type { NodeSpec, Sample } from './layout'
import { stone } from './palette'
import { paintSoft, softMaterial, swell } from './soft'
import type { WalkerState } from './Walker'

// an event is a small inlay in the band: a low dot of warmer stone. A commit is a slim arch over it.
const inlay = paintSoft(new THREE.SphereGeometry(1, 16, 10).scale(1, 0.28, 1), { top: stone.roof.top, sideX: stone.roof.sideX, sideZ: stone.roof.sideZ })
const arch = paintSoft(new THREE.TorusGeometry(1, 0.085, 10, 28, Math.PI), stone.roof)

interface Props {
  node: NodeSpec
  at: Sample & { heading: number }
  laneId: string | null // null: on main
  width: number // of the band it is set into
  sink?: number // a weathered band has settled; its marks with it
  walked: boolean // on the branch you are on, background marks appear once the figure has passed them
  pale: number
  still: boolean
  walker: RefObject<WalkerState>
  onPick: () => void
  onArrive?: () => void
}

/**
 * What rests on a published figure is a solid little inlay; an estimate is the same, paler and
 * translucent; background stays out of sight until walked past. A waypoint too: when the figure
 * reaches it, it rises a little and settles. It never bounces. Its words are an HTML note.
 */
export function Mark({ node, at, laneId, width, sink = 0, walked, pale, still, walker, onPick, onArrive }: Props) {
  const group = useRef<THREE.Group>(null)
  const [hovered, setHovered] = useState(false)
  const [passed, setPassed] = useState(false)
  const reached = useRef(false)
  const lift = useRef(0)
  const commit = node.kind === 'commit'
  const quiet = node.basis === 'background' && !commit
  // set exactly into the top surface, on the centreline, all of one size for their band
  const r = commit ? width * 0.42 : 0.0001 // a dot is a commit; nothing else is a dot

  useFrame((state, dt) => {
    const w = walker.current
    if (!w) return
    if (quiet && walked) {
      const now = w.laneId === laneId && w.d > node.d - 1.2
      if (now !== passed) setPassed(now)
    }
    const g = group.current
    if (!g) return
    const here = laneId !== null && w.laneId === laneId && Math.abs(w.d - node.d) < 0.6
    if (here && !reached.current) onArrive?.()
    reached.current = here
    lift.current = still ? 0 : THREE.MathUtils.damp(lift.current, here ? 0.05 : hovered ? 0.03 : 0, here ? 3 : 5, dt)
    g.position.y = at.y - sink + lift.current + (still ? 0 : swell(at.x, at.z, state.clock.elapsedTime))
  })

  if (quiet && !(walked && passed)) return <group ref={group} />
  return (
    <group ref={group} position={[at.x, at.y, at.z]} rotation={[0, -at.heading, 0]}>
      <mesh
        geometry={commit ? arch : inlay}
        material={softMaterial(pale)}
        scale={r}
        position={[0, commit ? -0.04 : 0, 0]}
        onClick={(e) => {
          if (e.delta > 6) return
          e.stopPropagation()
          onPick()
        }}
        onPointerOver={(e) => (e.stopPropagation(), setHovered(true), (document.body.style.cursor = 'pointer'))}
        onPointerOut={() => (setHovered(false), (document.body.style.cursor = ''))}
      />
      {hovered && commit && (
        <Html position={[0, 0.7, 0]} zIndexRange={[9, 5]} style={{ pointerEvents: 'none' }}>
          <div className="hw-note"><span className="hw-note__text">{node.label}</span></div>
        </Html>
      )}
    </group>
  )
}
