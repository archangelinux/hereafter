import { useRef, type ReactNode, type RefObject } from 'react'
import * as THREE from 'three'
import { useFrame, useThree } from '@react-three/fiber'

export interface Insets {
  top: number
  right: number
  bottom: number
  left: number
}

export interface LabelSpec {
  id: string
  priority: number // when two would overlap, the lower one is hidden
  at: () => { x: number; y: number; z: number }
  align: 'left' | 'right' | 'above'
  className?: string
  node: ReactNode
  onClick?: () => void
}

/** The DOM side: one absolutely placed element per label, in a layer over the canvas. */
export function LabelLayer({ specs, els }: { specs: LabelSpec[]; els: RefObject<Map<string, HTMLElement>> }) {
  return (
    <div className="hw-labels">
      {specs.map((s) => (
        <div
          key={s.id}
          ref={(el) => void (el ? els.current.set(s.id, el) : els.current.delete(s.id))}
          className={`hw-label ${s.className ?? ''} ${s.onClick ? 'hw-label--button' : ''}`}
          onClick={s.onClick}
        >
          {s.node}
        </div>
      ))}
    </div>
  )
}

const v = new THREE.Vector3()

/**
 * The scene side: every frame, put each label where its anchor is on screen. Labels stay out of
 * the HUD's regions (the safe insets), and no two ever overlap: by priority, the lesser one hides.
 */
export function LabelProjector({ specs, els, insets }: { specs: LabelSpec[]; els: RefObject<Map<string, HTMLElement>>; insets: Insets }) {
  const size = useThree((s) => s.size)
  const sizes = useRef(new Map<string, { w: number; h: number; text: string }>())
  useFrame(({ camera }) => {
    const placed: { x0: number; y0: number; x1: number; y1: number }[] = []
    const ordered = [...specs].sort((a, b) => b.priority - a.priority)
    for (const s of ordered) {
      const el = els.current.get(s.id)
      if (!el) continue
      const text = el.textContent ?? ''
      let dim = sizes.current.get(s.id)
      if (!dim || dim.text !== text) sizes.current.set(s.id, (dim = { w: el.offsetWidth, h: el.offsetHeight, text }))
      const p = s.at()
      v.set(p.x, p.y, p.z).project(camera)
      const px = (v.x * 0.5 + 0.5) * size.width
      const py = (-v.y * 0.5 + 0.5) * size.height
      const x0 = s.align === 'right' ? px + 14 : s.align === 'left' ? px - 14 - dim.w : px - dim.w / 2
      const y0 = s.align === 'above' ? py - dim.h - 6 : py - dim.h / 2
      const r = { x0: x0 - 5, y0: y0 - 3, x1: x0 + dim.w + 5, y1: y0 + dim.h + 3 }
      const inside = r.x0 >= insets.left && r.x1 <= size.width - insets.right && r.y0 >= insets.top && r.y1 <= size.height - insets.bottom
      const clear = inside && !placed.some((q) => r.x0 < q.x1 && r.x1 > q.x0 && r.y0 < q.y1 && r.y1 > q.y0)
      if (clear) placed.push(r)
      el.style.transform = `translate(${x0.toFixed(1)}px, ${y0.toFixed(1)}px)`
      el.classList.toggle('is-shown', clear)
    }
  })
  return null
}
