import { useCallback, useEffect, useRef, useState, type CSSProperties, type KeyboardEvent, type PointerEvent } from 'react'

type Side = 'left' | 'right'
interface Rail {
  width: number | null // null: the layout's own default for this window size
  collapsed: boolean
}
type Rails = Record<Side, Rail>

const KEY = 'hereafter.rails'
const MIN = 220
const MAX = 480
const CENTRE_MIN = 360
const FRESH: Rails = { left: { width: null, collapsed: false }, right: { width: null, collapsed: false } }

const load = (): Rails => {
  try {
    return { ...FRESH, ...(JSON.parse(localStorage.getItem(KEY) ?? '{}') as Partial<Rails>) }
  } catch {
    return FRESH
  }
}

/** Both rails can be dragged wider or narrower, folded to a tab, and remember how they were left. */
export function useRails() {
  const [rails, setRails] = useState<Rails>(load)
  const [narrow, setNarrow] = useState(() => matchMedia('(max-width: 900px)').matches)
  const frame = useRef(0)

  useEffect(() => {
    const mq = matchMedia('(max-width: 900px)')
    const on = () => setNarrow(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])
  useEffect(() => localStorage.setItem(KEY, JSON.stringify(rails)), [rails])

  const widthOf = (side: Side) => document.querySelector(`.hud__${side}`)?.getBoundingClientRect().width ?? 264
  const clamp = useCallback((side: Side, w: number) => {
    const other = widthOf(side === 'left' ? 'right' : 'left')
    return Math.round(Math.max(MIN, Math.min(MAX, innerWidth - other - CENTRE_MIN - 48, w)))
  }, [])
  const set = useCallback((side: Side, patch: Partial<Rail>) => {
    // one update a frame, so the scene can re-centre smoothly while a rail is dragged
    cancelAnimationFrame(frame.current)
    frame.current = requestAnimationFrame(() => setRails((r) => ({ ...r, [side]: { ...r[side], ...patch } })))
  }, [])

  const grip = (side: Side) => {
    const sign = side === 'left' ? 1 : -1
    return {
      className: `h-grip h-grip--${side}`,
      role: 'separator' as const,
      tabIndex: 0,
      'aria-orientation': 'vertical' as const,
      'aria-label': `Resize the ${side} panel`,
      title: 'Drag to resize. Double-click to reset.',
      onPointerDown: (e: PointerEvent<HTMLDivElement>) => {
        const el = e.currentTarget
        const startX = e.clientX
        const startW = widthOf(side)
        el.setPointerCapture(e.pointerId)
        document.body.classList.add('is-resizing')
        const move = (ev: globalThis.PointerEvent) => set(side, { width: clamp(side, startW + sign * (ev.clientX - startX)) })
        const up = () => {
          document.body.classList.remove('is-resizing')
          el.removeEventListener('pointermove', move)
          el.removeEventListener('pointerup', up)
          el.removeEventListener('pointercancel', up)
        }
        el.addEventListener('pointermove', move)
        el.addEventListener('pointerup', up)
        el.addEventListener('pointercancel', up)
      },
      onDoubleClick: () => set(side, { width: null }),
      onKeyDown: (e: KeyboardEvent<HTMLDivElement>) => {
        if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
        e.preventDefault()
        set(side, { width: clamp(side, widthOf(side) + sign * (e.key === 'ArrowRight' ? 16 : -16)) })
      },
    }
  }

  const style: CSSProperties = narrow ? {} : ({
    ...(rails.left.collapsed ? { '--rail': 'max-content' } : rails.left.width ? { '--rail': `${rails.left.width}px` } : {}),
    ...(rails.right.collapsed ? { '--rail-right': 'max-content' } : rails.right.width ? { '--rail-right': `${rails.right.width}px` } : {}),
  } as CSSProperties)

  return {
    style,
    grip,
    narrow,
    collapsed: (side: Side) => !narrow && rails[side].collapsed,
    toggle: (side: Side) => set(side, { collapsed: !rails[side].collapsed }),
    key: JSON.stringify(rails),
  }
}
