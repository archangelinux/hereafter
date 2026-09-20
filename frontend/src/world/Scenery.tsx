import { useEffect, useMemo, useRef } from 'react'
import * as THREE from 'three'
import { useFrame } from '@react-three/fiber'
import { ink, type StoneFamily } from './palette'
import { along, DS, MAIN_WIDTH, type LaneSpec, type Plaza, type WorldLayout } from './layout'
import { createRibbon, ribbonMaterial, writeRibbon } from './ribbon'
import { haloTexture, plazaGeometry, puffGeometry, seedGeometry, softMaterial, swell } from './soft'

function Bobbing({ at, still, children }: { at: [number, number, number]; still: boolean; children: React.ReactNode }) {
  const ref = useRef<THREE.Group>(null)
  useFrame((state) => {
    if (ref.current && !still) ref.current.position.y = at[1] + swell(at[0], at[2], state.clock.elapsedTime)
  })
  return (
    <group ref={ref} position={at}>
      {children}
    </group>
  )
}

/** Main: what actually happened. One strong band of warm stone, in long curves, ending under the figure's feet. */
export function Main({ layout, still }: { layout: WorldLayout; still: boolean }) {
  const { samples } = layout.main
  const geometry = useMemo(() => {
    const g = createRibbon(samples.length)
    writeRibbon(g, { samples, built: new Float32Array(samples.length).fill(1), firm: () => 1, width: MAIN_WIDTH, sink: 0, phase: 1.3, start: 0, end: (samples.length - 1) * DS + MAIN_WIDTH * 0.2 })
    return g
  }, [samples])
  const material = useMemo(() => ribbonMaterial(), [])
  useEffect(() => () => geometry.dispose(), [geometry])
  useFrame((state) => {
    material.uniforms.uTime.value = still ? 0 : state.clock.elapsedTime
    material.uniforms.uFarPast.value = 3 // the far past comes in out of the haze
  })
  return <mesh geometry={geometry} material={material} frustumCulled={false} renderOrder={3} />
}

/**
 * A circle, only where a decision is made: a calm plaza for a life decision, a small round for a
 * day-to-day one. A decision that is not in focus is only its circle; touching it asks for it to be opened.
 */
export function Plazas({ plazas, still, onHover, onPick }: { plazas: Plaza[]; still: boolean; onHover: (id: string | null) => void; onPick: (plaza: Plaza) => void }) {
  return (
    <group>
      {plazas.map((p) => (
        <Bobbing key={p.id} at={[p.at.x, p.at.y + 0.02, p.at.z]} still={still}>
          <mesh
            geometry={plazaGeometry('past')}
            material={softMaterial(1)}
            scale={[p.r, p.big ? 0.62 : 0.54, p.r]}
            renderOrder={4}
            onClick={(e) => {
              if (e.delta > 6 || !p.collapsed) return
              e.stopPropagation()
              onPick(p)
            }}
            onPointerOver={(e) => (e.stopPropagation(), onHover(p.id), p.collapsed && (document.body.style.cursor = 'pointer'))}
            onPointerOut={() => (onHover(null), (document.body.style.cursor = ''))}
          />
        </Bobbing>
      ))}
    </group>
  )
}

/**
 * The end of a path: a small platform, the same family of stone as the decision's circle it left, a
 * size down. The figure walks to it, the path's name stands on it, and it is where the way could
 * divide again. A road not taken ends in one too, in ruin stone, where it comes away.
 */
export function Ends({ lanes, still, onHover, onGo }: { lanes: LaneSpec[]; still: boolean; onHover: (id: string | null) => void; onGo: (laneId: string, step: number) => void }) {
  return (
    <group>
      {lanes.map((l) => {
        const p = along(l.samples, l.endD)
        const family: StoneFamily = l.status === 'merged' ? 'past' : l.status === 'open' ? 'open' : 'ruin'
        return (
          <Bobbing key={l.id} at={[p.x, p.y + 0.02, p.z]} still={still}>
            {/* a low landing, not a block: flat enough to stand on, a size down from a decision's circle */}
            <mesh
              geometry={plazaGeometry(family)}
              // opaque, like every other piece of stone: a translucent one draws in the late pass and
              // paints over the ghost whatever the depth says. Distance is told by colour, never by alpha.
              material={softMaterial(1)}
              scale={[l.endR, l.big ? 0.17 : 0.13, l.endR]}
              renderOrder={4}
              onClick={(e) => {
                if (e.delta > 6) return
                e.stopPropagation()
                onGo(l.id, l.steps - 1) // walk me to the end of this path
              }}
              onPointerOver={(e) => (e.stopPropagation(), onHover(l.id), (document.body.style.cursor = 'pointer'))}
              onPointerOut={() => (onHover(null), (document.body.style.cursor = ''))}
            />
          </Bobbing>
        )
      })}
    </group>
  )
}

// invisible, and wider than the dot it stands for: a dot this small is otherwise hard to hit
const pickable = new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false })

/**
 * The steps before the end: one dot for each place the figure comes to rest on its way out, lying ON
 * the band (never a peg through it). Coral behind the figure, dark ahead of it, so how far along the
 * path you are is plain at a glance. Touching one sends the figure to that step.
 */
export function Stops({ lanes, still, activeId, hereStep, onGo }: { lanes: LaneSpec[]; still: boolean; activeId: string | null; hereStep: number | null; onGo: (laneId: string, step: number) => void }) {
  return (
    <group>
      {lanes.map((l) => {
        const on = l.id === activeId && hereStep !== null
        const base = (l.big ? 0.22 : 0.12) * (l.width / (l.big ? 1 : 0.4))
        return l.rests.slice(0, -1).map((rest, k) => {
          const p = along(l.samples, rest.d)
          // steps that fall close together get smaller dots rather than touching ones
          const near = Math.min(k > 0 ? rest.d - l.rests[k - 1].d : 99, l.rests[k + 1].d - rest.d)
          const here = on && rest.step === hereStep
          const r = Math.max(0.06, Math.min(base, near * 0.4)) * (here ? 1.5 : 1)
          const family: StoneFamily = on && rest.step <= hereStep! ? 'coral' : l.status === 'open' || l.status === 'merged' ? 'bark' : 'ruin'
          return (
            <Bobbing key={`${l.id}:${rest.step}`} at={[p.x, p.y + 0.015, p.z]} still={still}>
              {/* depth in proportion to the dot, so it sits on the stone instead of hanging under it */}
              <mesh geometry={plazaGeometry(family)} material={softMaterial(1)} scale={[r, r * 0.5, r]} renderOrder={4} />
              <mesh
                geometry={plazaGeometry('past')}
                material={pickable}
                scale={[Math.max(r * 2.4, 0.3), 0.04, Math.max(r * 2.4, 0.3)]}
                onClick={(e) => {
                  if (e.delta > 6) return
                  e.stopPropagation()
                  onGo(l.id, rest.step)
                }}
                onPointerOver={(e) => (e.stopPropagation(), (document.body.style.cursor = 'pointer'))}
                onPointerOut={() => (document.body.style.cursor = '')}
              />
            </Bobbing>
          )
        })
      })}
    </group>
  )
}

/** What has been picked to keep: a soft-gold seed with a gentle halo, resting on the way ahead of now. */
export function Seeds({ layout, still }: { layout: WorldLayout; still: boolean }) {
  const halo = useMemo(() => new THREE.SpriteMaterial({ map: haloTexture(), transparent: true, depthWrite: false, toneMapped: false }), [])
  return (
    <group>
      {layout.main.seeds.map((s) => (
        <Bobbing key={s.id} at={[s.at.x, s.at.y + 0.2, s.at.z]} still={still}>
          <sprite material={halo} scale={[1.5, 1.5, 1]} />
          <mesh geometry={seedGeometry()} material={softMaterial(1)} scale={1.2} />
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
