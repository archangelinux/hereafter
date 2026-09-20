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
  upOnly?: boolean // a step on a path stays with its step: it may slide up the path, never down past now
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

// average advance per character at the type scale: label 12px small caps, body 16px italic, title 20px
const CHAR: Record<LabelKind, [top: number, text: number, max: number]> = {
  card: [6.2, 6.8, 40],
  node: [6.2, 6.5, 36],
  commit: [6.2, 6.8, 36],
  rare: [0, 6.2, 30],
  name: [6.2, 7.6, 24], // a long path name clips rather than going unplaced: the panel has it in full
  pick: [6.2, 6.5, 30],
  log: [6.2, 6.5, 38],
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
    const pad = c.kind === 'card' ? 8 : 0
    const w = Math.max(c.top.length * topW, text.length * textW) + pad * 2 + 4
    const h = (c.top && text ? 36 : 20) + pad * 2
    const gap = c.kind === 'card' ? 30 : 24
    const reach = c.reach ?? 48
    const slides = [0]
    for (let d = 20; d <= reach; d += 20) slides.push(...(c.upOnly ? [-d] : [-d, d]))
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
