// Label layout for the line. Every piece of text is a candidate with a priority; candidates are
// placed greedily, most important first, each trying a few positions beside its anchor. A label
// that cannot be placed without touching another label, the main line or the HUD is left out:
// it fades rather than overlaps.

import type { Zone } from '../types'
import type { Pt } from './layout'

export type LabelKind = 'card' | 'node' | 'commit' | 'rare' | 'name' | 'pick' | 'log'

export interface Candidate {
  id: string
  kind: LabelKind
  priority: number // lower is placed first
  anchor: Pt
  top: string // small caps line
  text: string // message line
  prefer: 1 | -1
  colour?: string
  reach?: number // how far, in px, the label may slide along the line from its anchor
  onClick?: () => void
}

export interface Placed extends Candidate {
  x: number // left edge of the text
  y: number // top of the box
  w: number
  h: number
  side: 1 | -1
  leader: string
}

const CHAR: Record<LabelKind, [top: number, text: number, max: number]> = {
  card: [6.6, 7.2, 40],
  node: [6.6, 6.7, 38],
  commit: [6.6, 7, 38],
  rare: [0, 6.6, 30],
  name: [6.6, 8.7, 30],
  pick: [6.6, 6.7, 32],
  log: [6.6, 6.7, 42],
}

export const clip = (s: string, n: number) => (s.length > n ? s.slice(0, n - 1).trimEnd() + '…' : s)

const hits = (a: Zone, b: Zone) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h

export function placeLabels(candidates: Candidate[], blocked: Zone[], bounds: Zone): Placed[] {
  const taken: Zone[] = [...blocked]
  const placed: Placed[] = []
  const ordered = [...candidates].sort((a, b) => a.priority - b.priority)
  for (const c of ordered) {
    const [topW, textW, max] = CHAR[c.kind]
    const text = clip(c.text, max)
    const pad = c.kind === 'card' ? 10 : 0
    const w = Math.max(c.top.length * topW, text.length * textW) + pad * 2 + 4
    const h = (c.top && text ? 31 : 17) + pad * 2
    const gap = c.kind === 'card' ? 30 : 24
    const reach = c.reach ?? 48
    const slides = [0]
    for (let d = 16; d <= reach; d += 16) slides.push(-d, d)
    let done = false
    for (const side of [c.prefer, -c.prefer as 1 | -1]) {
      for (const dy of slides) {
        const box = { x: side === 1 ? c.anchor.x + gap : c.anchor.x - gap - w, y: c.anchor.y + dy - h / 2, w, h }
        const grown = { x: box.x - 4, y: box.y - 2, w: w + 8, h: h + 4 }
        if (box.x < bounds.x || box.y < bounds.y || box.x + w > bounds.x + bounds.w || box.y + h > bounds.y + bounds.h) continue
        if (taken.some((t) => hits(grown, t))) continue
        const edge = side === 1 ? box.x - 3 : box.x + w + 3
        const from = c.anchor.x + side * 9
        const midY = box.y + h / 2
        placed.push({
          ...c, text, side, ...box,
          leader: `M${from} ${c.anchor.y} C ${from + side * 8} ${c.anchor.y}, ${edge - side * 10} ${midY}, ${edge} ${midY}`,
        })
        taken.push(box)
        done = true
        break
      }
      if (done) break
    }
  }
  return placed
}
