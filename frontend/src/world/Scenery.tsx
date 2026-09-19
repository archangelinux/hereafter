import { useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { useFrame } from '@react-three/fiber'
import { Html } from '@react-three/drei'
import { ink } from './palette'
import { along, hash01, type WorldLayout } from './layout'
import { domeGeometry, gateGeometry, haloTexture, hutGeometry, isletGeometry, milestoneGeometry, pennantGeometry, puffGeometry, seedGeometry, softMaterial, stoneGeometry, treeGeometry } from './soft'
import { Bobbing } from './Trail'

/**
 * The past: the same stones in warm sand and terracotta, fully laid, resting on soft islets, with a
 * few small rounded landmarks: one dome where learning began, one gate at a move, one hut at first
 * work, and the one tree where it all starts. You can look back; it is finished.
 */
export function Past({ layout, still, onOpenLog }: { layout: WorldLayout; still: boolean; onOpenLog: () => void }) {
  const { stones, samples, nodes } = layout.main
  const islets = useMemo(() => stones.filter((_, i) => i % 7 === 3), [stones])
  const pick = (type: RegExp, not: number[]) => nodes.find((n) => type.test(n.event?.event_type ?? '') && not.every((z) => Math.hypot(z - n.at.z) > 1.2))
  const learning = pick(/education/, [])
  const moving = pick(/city_move/, learning ? [learning.at.z] : [])
  const working = pick(/job_start/, [learning?.at.z ?? 999, moving?.at.z ?? 999])
  const beside = (p: { x: number; y: number; z: number; heading: number }, off: number, drop = 0): [number, number, number] => [p.x + Math.cos(p.heading) * off, p.y + drop, p.z + Math.sin(p.heading) * off]
  const start = along(samples, 0.5)
  const [hovered, setHovered] = useState<string | null>(null)

  return (
    <group>
      {stones.map((s) => (
        <Bobbing key={s.index} at={[s.x, s.y, s.z]} still={still}>
          <mesh geometry={stoneGeometry('past')} material={softMaterial(1)} scale={[s.r, Math.min(1, s.r * 2), s.r]} />
        </Bobbing>
      ))}
      {/* the stone under the figure's feet: where the trail opens */}
      <Bobbing at={[0, 0.04, 0]} still={still}>
        <mesh geometry={stoneGeometry('past')} material={softMaterial(1)} scale={[0.85, 1, 0.85]} />
      </Bobbing>
      <Bobbing at={[0, -0.34, 0]} still={still}>
        <mesh geometry={isletGeometry('past', 1)} material={softMaterial(1)} scale={1.5} />
      </Bobbing>
      {islets.map((s) => (
        <Bobbing key={s.index} at={[s.x, s.y - 0.36, s.z]} still={still}>
          <mesh geometry={isletGeometry('past', (s.index % 3) as 0 | 1 | 2)} material={softMaterial(1)} scale={1.0 + hash01(`trunk:islet:${s.index}`) * 0.6} />
        </Bobbing>
      ))}

      {nodes.map((n) => (
        <mesh
          key={n.id}
          geometry={milestoneGeometry('past')}
          material={softMaterial(1)}
          position={beside(n.at, -0.62, -0.12)}
          onClick={(e) => (e.delta > 6 ? undefined : (e.stopPropagation(), onOpenLog()))}
          onPointerOver={(e) => (e.stopPropagation(), setHovered(n.id), (document.body.style.cursor = 'pointer'))}
          onPointerOut={() => (setHovered(null), (document.body.style.cursor = ''))}
        >
          {hovered === n.id && (
            <Html position={[0, 0.7, 0]} zIndexRange={[9, 5]} style={{ pointerEvents: 'none' }}>
              <div className="hw-note hw-note--left">
                <span className="hw-note__caption">{n.caption}</span>
                <span className="hw-note__text">{n.label}</span>
              </div>
            </Html>
          )}
        </mesh>
      ))}

      {learning && (
        <group position={beside(learning.at, -2.0, -0.2)}>
          <mesh geometry={isletGeometry('past', 1)} material={softMaterial(1)} scale={1.5} />
          <mesh geometry={domeGeometry()} material={softMaterial(1)} />
          <mesh geometry={pennantGeometry()} material={softMaterial(1)} position={[0, 1.3, 0]} />
        </group>
      )}
      {moving && <mesh geometry={gateGeometry()} material={softMaterial(1)} position={beside(moving.at, 0, -0.1)} rotation={[0, -moving.at.heading, 0]} />}
      {working && (
        <group position={beside(working.at, 1.8, -0.3)}>
          <mesh geometry={isletGeometry('past', 2)} material={softMaterial(1)} scale={1.1} />
          <mesh geometry={hutGeometry()} material={softMaterial(1)} />
        </group>
      )}

      {/* where it all starts: a little ground, and the one tree */}
      <group position={[start.x + 1.5, start.y - 0.25, start.z + 0.9]}>
        <mesh geometry={isletGeometry('past', 0)} material={softMaterial(1)} scale={1.3} />
        <mesh geometry={treeGeometry()} material={softMaterial(1)} />
      </group>
    </group>
  )
}

/** What has been picked to keep: a soft-gold seed with a gentle halo, resting on its own small islet ahead of now. */
export function Seeds({ layout, still }: { layout: WorldLayout; still: boolean }) {
  const halo = useMemo(() => new THREE.SpriteMaterial({ map: haloTexture(), transparent: true, depthWrite: false, toneMapped: false }), [])
  return (
    <group>
      {layout.main.seeds.map((s) => (
        <Bobbing key={s.id} at={[s.at.x, s.at.y, s.at.z]} still={still}>
          <mesh geometry={isletGeometry('past', 2)} material={softMaterial(1)} scale={0.7} />
          <sprite material={halo} scale={[1.5, 1.5, 1]} position={[0, 0.5, 0]} />
          <mesh geometry={seedGeometry()} material={softMaterial(1)} position={[0, 0.5, 0]} scale={1.2} />
        </Bobbing>
      ))}
    </group>
  )
}

// Round, puffy clouds, drifting slowly. The sky itself is the page behind the canvas.
const CLOUDS: { at: [number, number, number]; scale: number; speed: number }[] = [
  { at: [-16, -8, -4], scale: 2.4, speed: 0.1 },
  { at: [9, -10, 10], scale: 3.0, speed: 0.07 },
  { at: [-2, -9, -30], scale: 3.2, speed: 0.09 },
  { at: [-24, -7, -38], scale: 2.6, speed: 0.06 },
  { at: [14, -8, -44], scale: 3.4, speed: 0.08 },
]
const LOBES: [number, number, number, number][] = [
  [0, 0, 0, 1],
  [1.2, -0.18, 0.25, 0.74],
  [-1.15, -0.22, -0.1, 0.66],
  [0.4, 0.3, -0.5, 0.6],
  [-0.35, 0.18, 0.55, 0.52],
]
const DRIFT = 34

export function Sky({ still }: { still: boolean }) {
  const refs = useRef<(THREE.Group | null)[]>([])
  const bird = useRef<THREE.Group>(null)
  const wings = useMemo(() => {
    const s = new THREE.Shape()
    s.moveTo(-0.6, 0.12)
    s.quadraticCurveTo(-0.3, 0.34, 0, 0)
    s.quadraticCurveTo(0.3, 0.34, 0.6, 0.12)
    s.quadraticCurveTo(0.3, 0.24, 0, -0.08)
    s.quadraticCurveTo(-0.3, 0.24, -0.6, 0.12)
    return new THREE.ShapeGeometry(s, 8)
  }, [])
  const feather = useMemo(() => new THREE.MeshBasicMaterial({ color: ink.text, side: THREE.DoubleSide, toneMapped: false, transparent: true, opacity: 0.5 }), [])

  useFrame((state) => {
    if (still) return
    const t = state.clock.elapsedTime
    CLOUDS.forEach((c, i) => {
      const g = refs.current[i]
      if (!g) return
      g.position.x = c.at[0] + ((t * c.speed + i * 9) % DRIFT) - DRIFT / 2
      g.position.y = c.at[1] + 0.25 * Math.sin(t * 0.2 + i)
    })
    if (bird.current) bird.current.position.set(-12 + ((t * 0.3) % 36), 10 + Math.sin(t * 0.25) * 0.4, -20 - ((t * 0.18) % 36))
  })

  return (
    <group>
      {CLOUDS.map((c, i) => (
        <group key={i} ref={(g) => void (refs.current[i] = g)} position={c.at} scale={c.scale}>
          {LOBES.map(([x, y, z, s], k) => (
            <mesh key={k} geometry={puffGeometry('cloud')} material={softMaterial(1)} position={[x, y, z]} scale={[s, s * 0.72, s]} />
          ))}
        </group>
      ))}
      <group ref={bird} position={[-8, 10, -24]} rotation={[0, Math.PI / 4, 0]} scale={0.9}>
        <mesh geometry={wings} material={feather} />
      </group>
    </group>
  )
}
