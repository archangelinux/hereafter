// One smooth, continuous band: a soft stream of pale stone winding through the sky. Its cross-section
// is rounded and CLOSED (a low crown, soft shoulders, an underside), its width breathes a little.
// The top of the band is exactly at the centreline's height, so bands, circles, marks and the figure
// all share one plane. Every end is finished in the geometry itself: a rounded nose where a band
// genuinely ends, a taper to nothing where it dissolves. Nothing is translucent: likelihood is drawn
// as stone → thinner and paler → just its two drawn edges → gone, and what recedes grows paler, not
// see-through, so no layer ever shows through another.

import * as THREE from 'three'
import { ink, stone } from './palette'
import { DS, type Sample } from './layout'

// across the band: under-left, left edge, left shoulder, crown, right shoulder, right edge, under-right
// a soft ROUNDED section, finely divided so it shades smoothly: under, edge, shoulders, crown
const U = [-0.74, -0.93, -1, -0.95, -0.8, -0.45, 0, 0.45, 0.8, 0.95, 1, 0.93, 0.74]
const UP = [0, 0.1, 0.3, 0.5, 0.72, 0.92, 1, 0.92, 0.72, 0.5, 0.3, 0.1, 0] // how much each looks at the sky
const YK = [-1, -0.8, -0.52, -0.3, -0.13, -0.035, 0, -0.035, -0.13, -0.3, -0.52, -0.8, -1] // depth below the crown, as a share of the thickness // how much each looks at the sky
const VERTS = U.length

export interface RibbonState {
  samples: Sample[]
  built: ArrayLike<number> // per sample 0..1
  fade?: ArrayLike<number> // per sample 1..0: the drawn edges of an unbuilt stretch thinning away
  firm: (d: number) => number // 0..1: how far it has turned to main's own stone
  width: number
  sink: number
  phase: number
  start?: number // where the band begins (a rounded nose there, unless it is hidden inside a circle)
  end?: number // where it ends: a rounded nose
  slim?: number // 0..1: a branch you are not on draws in, thinner
  thick?: number
}

export function createRibbon(count: number): THREE.BufferGeometry {
  const g = new THREE.BufferGeometry()
  const n = count * VERTS
  g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(n * 3), 3))
  for (const name of ['aAcross', 'aUp', 'aWarm', 'aAlong', 'aBuilt', 'aFirm', 'aFade']) g.setAttribute(name, new THREE.BufferAttribute(new Float32Array(n), 1))
  const index: number[] = []
  for (let i = 0; i < count - 1; i++)
    for (let k = 0; k < VERTS; k++) {
      // the last strip joins under-right back to under-left: the underside. The section is closed.
      const a = i * VERTS + k
      const a1 = i * VERTS + ((k + 1) % VERTS)
      index.push(a, a1, a + VERTS, a1, a1 + VERTS, a + VERTS)
    }
  g.setIndex(index)
  return g
}

const smooth = (a: number, b: number, v: number) => {
  const t = Math.max(0, Math.min(1, (v - a) / (b - a)))
  return t * t * (3 - 2 * t)
}

/** Write the band's vertices for a centreline. Cheap enough to run every frame while something is changing. */
export function writeRibbon(g: THREE.BufferGeometry, s: RibbonState) {
  const attr = (name: string) => g.getAttribute(name) as THREE.BufferAttribute
  const pos = attr('position')
  const across = attr('aAcross')
  const up = attr('aUp')
  const warm = attr('aWarm')
  const alongA = attr('aAlong')
  const builtA = attr('aBuilt')
  const firmA = attr('aFirm')
  const fadeA = attr('aFade')
  const n = s.samples.length
  const T = s.thick ?? 0.34
  const start = s.start ?? -1
  const end = s.end ?? 1e6
  const nose = Math.max(0.3, s.width * 0.75) // how long a rounded end takes
  let prevH = 0
  for (let i = 0; i < n; i++) {
    const p = s.samples[i]
    const a = s.samples[Math.max(0, i - 2)]
    const b = s.samples[Math.min(n - 1, i + 2)]
    const h = Math.atan2(b.x - a.x, -(b.z - a.z)) // heading over a wider stencil: no kinks, no ribs
    const d = i * DS
    const firm = s.firm(d)
    const b0 = s.built[Math.min(s.built.length - 1, i)]
    const built = b0 + (1 - b0) * firm
    const fade = s.fade ? s.fade[Math.min(s.fade.length - 1, i)] : 1
    let turn = i === 0 ? 0 : h - prevH
    if (turn > Math.PI) turn -= 2 * Math.PI
    if (turn < -Math.PI) turn += 2 * Math.PI
    prevH = h
    const roll = Math.max(-0.12, Math.min(0.12, (turn / DS) * 0.4)) * smooth(0.5, 3.5, d) // banked a little, never where it meets a circle
    const breathe = 1 + 0.08 * Math.sin(d * 0.41 + s.phase) * smooth(1, 4, d)
    // finished ends: a rounded nose at a true end, a taper to nothing where the stone gives out
    const toEnd = end - d
    const fromStart = d - start
    const capE = toEnd <= 0 ? 0 : toEnd < nose ? Math.sqrt(1 - Math.pow(1 - toEnd / nose, 2)) : 1
    const capS = start < 0 ? 1 : fromStart <= 0 ? 0 : fromStart < nose ? Math.sqrt(1 - Math.pow(1 - fromStart / nose, 2)) : 1
    const cap = Math.min(capE, capS)
    const body = (0.22 + 0.78 * smooth(0.06, 0.6, built)) * (0.35 + 0.65 * fade)
    const half = (s.width / 2) * (1 - 0.4 * (s.slim ?? 0)) * breathe * body * cap
    const thick = T * Math.min(1, 0.45 + s.width * 0.55) * (0.1 + 0.9 * smooth(0.2, 0.6, built)) * cap
    const rx = Math.cos(h) * Math.cos(roll)
    const rz = Math.sin(h) * Math.cos(roll)
    const ry = -Math.sin(roll)
    const y0 = p.y - s.sink * smooth(0, 2.6, d) // the crown of the band is exactly here
    const lightL = smooth(-0.4, 0.4, -Math.cos(h) + Math.sin(h)) // does this side look toward the warm +x, or the shadow +z
    const lightR = smooth(-0.4, 0.4, Math.cos(h) - Math.sin(h))
    for (let k = 0; k < VERTS; k++) {
      const v = i * VERTS + k
      const o = U[k] * half
      pos.setXYZ(v, p.x + rx * o, y0 + ry * o + YK[k] * thick, p.z + rz * o)
      across.setX(v, U[k])
      up.setX(v, UP[k])
      warm.setX(v, k < 6 ? lightL : k > 6 ? lightR : 0.5)
      alongA.setX(v, d)
      builtA.setX(v, built)
      firmA.setX(v, firm)
      fadeA.setX(v, fade)
    }
  }
  for (const a of [pos, across, up, warm, alongA, builtA, firmA, fadeA]) a.needsUpdate = true
  g.computeBoundingSphere()
}

const vertex = /* glsl */ `
  attribute float aAcross;
  attribute float aUp;
  attribute float aWarm;
  attribute float aAlong;
  attribute float aBuilt;
  attribute float aFirm;
  attribute float aFade;
  uniform float uTime;
  uniform float uLift;
  uniform float uEnd;
  uniform float uBreak;
  varying float vAcross;
  varying float vUp;
  varying float vWarm;
  varying float vAlong;
  varying float vBuilt;
  varying float vFirm;
  varying float vFade;
  void main() {
    vAcross = aAcross; vUp = aUp; vWarm = aWarm; vAlong = aAlong; vBuilt = aBuilt; vFirm = aFirm; vFade = aFade;
    vec3 p = position;
    p.y += 0.05 * sin(uTime * 0.45) + uLift; // the slow swell everything rides on
    float gone = smoothstep(uEnd - 1.1, uEnd, aAlong) * uBreak;       // a stale end has come away and is going down
    p.y -= gone * gone * 0.8;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
  }
`

const fragment = /* glsl */ `
  uniform vec3 uOpenTop; uniform vec3 uOpenX; uniform vec3 uOpenZ;
  uniform vec3 uPastTop; uniform vec3 uPastX; uniform vec3 uPastZ;
  uniform vec3 uRuinTop; uniform vec3 uRuinX; uniform vec3 uRuinZ;
  uniform vec3 uMist; uniform vec3 uOutline; uniform vec3 uMoss; uniform vec3 uCoral; uniform vec3 uSky;
  uniform float uWeather;
  uniform float uFrom;
  uniform float uEnd;
  uniform float uGrow;
  uniform float uPale;
  uniform float uDash;
  uniform float uBreak;
  uniform float uFarPast;
  uniform float uRecede;
  uniform float uActive;
  uniform float uReveal;
  uniform float uHead;
  varying float vAcross;
  varying float vUp;
  varying float vWarm;
  varying float vAlong;
  varying float vBuilt;
  varying float vFirm;
  varying float vFade;

  float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
  float vnoise(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash(i), hash(i + vec2(1, 0)), u.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), u.x), u.y);
  }

  void main() {
    // Ends are finished in the geometry; this only follows a band while it is still growing or drawing back.
    if (vAlong > min(uEnd, uGrow) || vAlong < uFrom) discard;
    if (uBreak > 0.5) {
      float r = uEnd - vAlong;
      if (r > 0.5 && r < 0.72) discard;
    }
    if (uDash > 0.0 && fract(vAlong * uDash) > 0.42) discard;

    float b = vBuilt;
    float shown = mix(vFade, 1.0, uReveal);
    float sky = smoothstep(0.2, 0.95, vUp);
    vec3 top = mix(uOpenTop, uPastTop, vFirm);
    vec3 side = mix(mix(uOpenZ, uPastZ, vFirm), mix(uOpenX, uPastX, vFirm), vWarm);
    top = mix(top, uPastTop, 0.35 * uActive * (1.0 - vFirm)); // the branch you are on: a touch warmer and surer …
    // … with a fine coral line along its edges, surest on the first step: the one a merge would commit
    float fine = smoothstep(0.74, 0.86, abs(vAcross)) * smoothstep(0.15, 0.5, vUp) * uActive * mix(0.45, 1.0, 1.0 - smoothstep(uHead - 0.15, uHead + 0.15, vAlong));
    vec3 live = mix(mix(side, top, sky), uCoral, fine);

    // weathered: grey, with a little sage growth on top
    float growth = smoothstep(0.62, 0.74, vnoise(vec2(vAlong * 1.15, vAcross * 1.6 + 3.0)));
    vec3 worn = mix(mix(uRuinZ, uRuinX, vWarm), mix(uRuinTop, uMoss, growth * 0.8), sky);
    vec3 col = mix(live, worn, uWeather);

    // less likely: paler, going lavender, as well as thinner. Opaque throughout.
    col = mix(mix(uMist, col, 0.4), col, smoothstep(0.25, 0.62, b));
    // least likely: only its two drawn edges are left, on top; everything between and beneath is gone
    float stoneLeft = smoothstep(0.16, 0.24, b);
    if (stoneLeft < 0.5) {
      float edge = smoothstep(0.62, 0.8, abs(vAcross)) * step(0.2, vUp);
      if (edge < 0.5 || b < 0.03 || shown < 0.12) discard;
      col = mix(uOutline, uCoral, fine);
      col = mix(uSky, col, clamp(shown * 1.2, 0.0, 1.0));
    }

    if (uFarPast > 0.0) col = mix(uSky, col, smoothstep(0.0, uFarPast, vAlong)); // the far past comes in out of the haze
    col = mix(col, uSky, 0.55 * uRecede); // what you are not on recedes toward the sky: paler, never see-through
    col = mix(uSky, col, uPale);
    gl_FragColor = vec4(col, 1.0);
    #include <colorspace_fragment>
  }
`

const c = (hex: string) => new THREE.Color(hex)

export function ribbonMaterial(): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    vertexShader: vertex,
    fragmentShader: fragment,
    transparent: false,
    depthWrite: true,
    side: THREE.DoubleSide,
    toneMapped: false,
    uniforms: {
      uOpenTop: { value: c(stone.open.top) }, uOpenX: { value: c(stone.open.sideX) }, uOpenZ: { value: c(stone.open.sideZ) },
      uPastTop: { value: c(stone.past.top) }, uPastX: { value: c(stone.past.sideX) }, uPastZ: { value: c(stone.past.sideZ) },
      uRuinTop: { value: c(stone.ruin.top) }, uRuinX: { value: c(stone.ruin.sideX) }, uRuinZ: { value: c(stone.ruin.sideZ) },
      uMist: { value: c(ink.mist) }, uOutline: { value: c(ink.outline) }, uMoss: { value: c(ink.moss) }, uCoral: { value: c('#E2917A') }, uSky: { value: c('#FAEAE3') },
      uTime: { value: 0 }, uLift: { value: 0 }, uWeather: { value: 0 }, uFrom: { value: -1 }, uEnd: { value: 1e6 }, uGrow: { value: 1e6 },
      uPale: { value: 1 }, uDash: { value: 0 }, uBreak: { value: 0 }, uFarPast: { value: 0 }, uRecede: { value: 0 }, uActive: { value: 0 }, uReveal: { value: 0 }, uHead: { value: 1e6 },
    },
  })
}
