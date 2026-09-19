// Round forms, flat pastel shading. Nothing is lit at run time: each shape's smooth normals are
// read once and the palette's three values (top, warm side, shadow side) are blended across them,
// so the colours are exactly the palette's and the look is soft rather than faceted.
// The camera sits toward (+x, +y, +z): +x is the warm side, +z the shadow side.

import * as THREE from 'three'
import { stone, type Faces, type StoneFamily } from './palette'

export const smooth = (a: number, b: number, v: number) => {
  const t = Math.max(0, Math.min(1, (v - a) / (b - a)))
  return t * t * (3 - 2 * t)
}

export function paintSoft(g: THREE.BufferGeometry, faces: Faces): THREE.BufferGeometry {
  if (!g.getAttribute('normal')) g.computeVertexNormals()
  const normal = g.getAttribute('normal')
  const colors = new Float32Array(normal.count * 3)
  const top = new THREE.Color(faces.top)
  const sx = new THREE.Color(faces.sideX)
  const sz = new THREE.Color(faces.sideZ)
  const c = new THREE.Color()
  for (let i = 0; i < normal.count; i++) {
    const nx = normal.getX(i)
    const ny = normal.getY(i)
    const nz = normal.getZ(i)
    c.copy(sz).lerp(sx, smooth(-0.35, 0.35, nx - nz))
    if (ny < 0) c.lerp(sz, smooth(0, 0.8, -ny))
    c.lerp(top, smooth(0.3, 0.7, ny))
    colors.set([c.r, c.g, c.b], i * 3)
  }
  g.setAttribute('color', new THREE.BufferAttribute(colors, 3))
  return g
}

const cache = new Map<string, THREE.BufferGeometry>()
function cached(key: string, make: () => THREE.BufferGeometry): THREE.BufferGeometry {
  let g = cache.get(key)
  if (!g) cache.set(key, (g = make()))
  return g
}

/** join painted parts (position + colour only) into one geometry */
function join(parts: THREE.BufferGeometry[]): THREE.BufferGeometry {
  const flat = parts.map((p) => (p.index ? p.toNonIndexed() : p))
  let total = 0
  for (const p of flat) total += p.getAttribute('position').count
  const position = new Float32Array(total * 3)
  const color = new Float32Array(total * 3)
  let at = 0
  for (const p of flat) {
    position.set(p.getAttribute('position').array as Float32Array, at)
    color.set(p.getAttribute('color').array as Float32Array, at)
    at += p.getAttribute('position').count * 3
  }
  const g = new THREE.BufferGeometry()
  g.setAttribute('position', new THREE.BufferAttribute(position, 3))
  g.setAttribute('color', new THREE.BufferAttribute(color, 3))
  return g
}

/** A pebble: a squashed cylinder with soft shoulders. Unit radius, top at y = 0. */
function pebble(height: number, bevel: number, segments = 28) {
  const pts: THREE.Vector2[] = [new THREE.Vector2(0.0001, 0)]
  const steps = 6
  pts.push(new THREE.Vector2(1 - bevel, 0))
  for (let i = 1; i <= steps; i++) {
    const a = (i / steps) * (Math.PI / 2)
    pts.push(new THREE.Vector2(1 - bevel + Math.sin(a) * bevel, -bevel + Math.cos(a) * bevel))
  }
  for (let i = 1; i <= steps; i++) {
    const a = (i / steps) * (Math.PI / 2)
    pts.push(new THREE.Vector2(1 - bevel + Math.cos(a) * bevel, -height + bevel - Math.sin(a) * bevel))
  }
  pts.push(new THREE.Vector2(0.0001, -height))
  const g = new THREE.LatheGeometry(pts.reverse(), segments)
  // whichever way the profile was wound, make the normals face outward: the top must look up
  const pos = g.getAttribute('position')
  const n = g.getAttribute('normal')
  let topmost = 0
  for (let i = 1; i < pos.count; i++) if (pos.getY(i) > pos.getY(topmost)) topmost = i
  if (n.getY(topmost) < 0) for (let i = 0; i < n.count; i++) n.setXYZ(i, -n.getX(i), -n.getY(i), -n.getZ(i))
  return g
}

export function mixFaces(a: Faces, b: Faces, t: number): Faces {
  const mix = (p: string, q: string) => '#' + new THREE.Color(p).lerp(new THREE.Color(q), t).getHexString()
  return { top: mix(a.top, b.top), sideX: mix(a.sideX, b.sideX), sideZ: mix(a.sideZ, b.sideZ) }
}

/** the stepping stone */
export const stoneGeometry = (family: StoneFamily) => cached(`stone:${family}`, () => paintSoft(pebble(0.42, 0.16), stone[family]))

/** thinner, on its way to mist; `mist` picks how far the colour has gone toward lavender */
export const thinStoneGeometry = (mist: 0 | 1) => cached(`thin:${mist}`, () => paintSoft(pebble(0.16, 0.07), mixFaces(stone.open, stone.mist, mist ? 0.75 : 0.3)))

/** only a soft lavender ring where a stone would be */
export const ringGeometry = () => cached('ring', () => new THREE.TorusGeometry(0.9, 0.035, 8, 40).rotateX(Math.PI / 2).translate(0, -0.05, 0))

/** A floating islet: a smooth blob, gently domed on top, hanging to a soft rounded root. Top at y = 0. */
export function isletGeometry(family: StoneFamily, variant: 0 | 1 | 2 = 0) {
  return cached(`islet:${family}:${variant}`, () => {
    const g = new THREE.SphereGeometry(1, 28, 20)
    const pos = g.getAttribute('position')
    const a = variant * 2.1
    for (let i = 0; i < pos.count; i++) {
      let x = pos.getX(i)
      let y = pos.getY(i)
      let z = pos.getZ(i)
      const wobble = 1 + 0.13 * Math.sin(x * 2.3 + a) * Math.sin(z * 1.9 + a * 0.7) + 0.08 * Math.sin(y * 3.1 + a)
      if (y > 0) {
        y *= 0.2
      } else {
        const taper = 1 - 0.55 * Math.pow(-y, 1.6)
        x *= taper
        z *= taper
        y *= 1.35
      }
      pos.setXYZ(i, x * wobble, y - 0.2, z * wobble)
    }
    g.computeVertexNormals()
    return paintSoft(g, stone[family])
  })
}

export const puffGeometry = (family: 'cloud' | 'mist' = 'cloud') => cached(`puff:${family}`, () => paintSoft(new THREE.SphereGeometry(1, 20, 14), stone[family]))

export const mossGeometry = () => cached('moss', () => paintSoft(new THREE.SphereGeometry(0.2, 12, 8).scale(1, 0.55, 1), stone.sage))

/** an event beside the trail: a small rounded marker stone */
export const milestoneGeometry = (family: StoneFamily) =>
  cached(`milestone:${family}`, () => paintSoft(new THREE.SphereGeometry(0.15, 14, 10).scale(1, 0.85, 1).translate(0, 0.1, 0), stone[family]))

// ---- the few landmarks of the past: a dome with its pennant, a little round hut, a rounded gate

export function domeGeometry() {
  return cached('dome', () =>
    join([
      paintSoft(new THREE.CylinderGeometry(0.62, 0.68, 0.7, 28, 1, true).translate(0, 0.35, 0), stone.past),
      paintSoft(new THREE.SphereGeometry(0.66, 28, 14, 0, Math.PI * 2, 0, Math.PI / 2).translate(0, 0.7, 0), stone.roof),
    ]),
  )
}

export function hutGeometry() {
  return cached('hut', () =>
    join([
      paintSoft(new THREE.CylinderGeometry(0.42, 0.46, 0.5, 24, 1, true).translate(0, 0.25, 0), stone.open),
      paintSoft(new THREE.SphereGeometry(0.56, 24, 12, 0, Math.PI * 2, 0, Math.PI / 2).scale(1, 0.8, 1).translate(0, 0.46, 0), stone.past),
    ]),
  )
}

/** an arch the trail passes under; it stands across the x axis, feet at y = 0 */
export const gateGeometry = () => cached('gate', () => paintSoft(new THREE.TorusGeometry(0.85, 0.11, 12, 28, Math.PI), stone.past))
/** a commit: the same rounded gate, small, over one stone */
export const smallGateGeometry = () => cached('gate:small', () => paintSoft(new THREE.TorusGeometry(0.52, 0.07, 10, 24, Math.PI), stone.roof))

export const treeGeometry = () =>
  cached('tree', () =>
    join([
      paintSoft(new THREE.CylinderGeometry(0.045, 0.06, 0.7, 10).translate(0, 0.35, 0), stone.bark),
      paintSoft(new THREE.SphereGeometry(0.42, 20, 14).translate(0, 0.98, 0), stone.sage),
    ]),
  )

export function pennantGeometry() {
  return cached('pennant', () => {
    const pole = paintSoft(new THREE.CylinderGeometry(0.018, 0.018, 0.8, 8).translate(0, 0.4, 0), stone.bark)
    const s = new THREE.Shape()
    s.moveTo(0, 0.78)
    s.bezierCurveTo(0.2, 0.84, 0.36, 0.72, 0.56, 0.76)
    s.bezierCurveTo(0.5, 0.7, 0.5, 0.66, 0.56, 0.6)
    s.bezierCurveTo(0.36, 0.56, 0.2, 0.66, 0, 0.58)
    s.closePath()
    const cloth = new THREE.ShapeGeometry(s, 10).rotateY(Math.PI / 2)
    const n = cloth.getAttribute('position').count
    const colors = new Float32Array(n * 3)
    const c = new THREE.Color(stone.sage.sideX)
    for (let i = 0; i < n; i++) colors.set([c.r, c.g, c.b], i * 3)
    cloth.setAttribute('color', new THREE.BufferAttribute(colors, 3))
    return join([pole, cloth])
  })
}

// ---- the figure: a rounded coral body, two small arms, a cream head, small feet. A normal, simple little person.
export const figureBody = () =>
  cached('figure:body', () => {
    const g = new THREE.CapsuleGeometry(0.13, 0.2, 10, 28)
    const pos = g.getAttribute('position')
    for (let i = 0; i < pos.count; i++) {
      const y = pos.getY(i)
      const k = 1 - 0.28 * smooth(-0.1, 0.23, y) // narrower at the shoulders, like a little cloak
      pos.setXYZ(i, pos.getX(i) * k, y, pos.getZ(i) * k)
    }
    g.computeVertexNormals()
    return paintSoft(g.translate(0, 0.27, 0), stone.coral)
  })
export const figureHead = () => cached('figure:head', () => paintSoft(new THREE.SphereGeometry(0.105, 24, 18), stone.open))
export const figureFoot = () => cached('figure:foot', () => paintSoft(new THREE.SphereGeometry(0.05, 12, 10).scale(1, 0.7, 1.4), stone.roof))
/** a short soft arm, hanging from its shoulder: the pivot is the top of the capsule */
export const figureArm = () => cached('figure:arm', () => paintSoft(new THREE.CapsuleGeometry(0.021, 0.078, 8, 16).translate(0, -0.052, 0), stone.open)) // small, and the same cream as the head
/** where you are: a thin ring around the figure's feet. It lives in the figure's own group, so the two can never come apart. */
export const figureRing = () => cached('figure:ring', () => new THREE.TorusGeometry(0.27, 0.014, 8, 48).rotateX(Math.PI / 2))

/** a decision's circle: a simple, perfect, low cylinder with a crisp rim. Unit radius, top at y = 0, unit depth. */
export const plazaGeometry = (family: StoneFamily) =>
  cached(`plaza:${family}`, () => {
    const g = new THREE.CylinderGeometry(1, 1, 1, 96, 1, false).translate(0, -0.5, 0)
    return paintSoft(g, stone[family])
  })

export const seedGeometry = () => cached('seed', () => paintSoft(new THREE.SphereGeometry(0.15, 16, 12).scale(0.85, 1.2, 0.85), stone.gold))

let halo: THREE.Texture | null = null
/** a soft lighter disc behind a picked seed; there is no bloom pass anywhere */
export function haloTexture(): THREE.Texture {
  if (halo) return halo
  const size = 128
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = size
  const ctx = canvas.getContext('2d')!
  const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2)
  g.addColorStop(0, 'rgba(255, 244, 214, 0.95)')
  g.addColorStop(0.35, 'rgba(250, 226, 170, 0.5)')
  g.addColorStop(1, 'rgba(250, 226, 170, 0)')
  ctx.fillStyle = g
  ctx.fillRect(0, 0, size, size)
  halo = new THREE.CanvasTexture(canvas)
  halo.colorSpace = THREE.SRGBColorSpace
  return halo
}

const shared = new Map<string, THREE.MeshBasicMaterial>()
/** One unlit vertex-coloured material per opacity: exact palette colours out. */
export function softMaterial(opacity = 1): THREE.MeshBasicMaterial {
  const key = opacity.toFixed(2)
  let m = shared.get(key)
  if (!m) {
    m = new THREE.MeshBasicMaterial({ vertexColors: true, toneMapped: false, transparent: opacity < 1, opacity, depthWrite: opacity >= 1, side: THREE.DoubleSide })
    shared.set(key, m)
  }
  return m
}

/** the slow swell everything rides on; the ribbon shader uses the same wave */
export const swell = (_x: number, _z: number, time: number) => 0.05 * Math.sin(time * 0.45) // one swell for the whole world, so everything that touches stays flush
