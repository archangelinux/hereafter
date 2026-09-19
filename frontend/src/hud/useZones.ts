import { useEffect, useState } from 'react'
import type { Insets, Zone } from '../types'

const SELECTORS = ['.masthead', '.hud-right', '.hud-bottom .corner:not(.corner--right)', '.hud-bottom .narrate__box', '.actions', '.line__legend', '.line__recentre', '.reader', '.drawer', '.satchel']

/** Where the HUD actually is, measured. Views keep their labels out of these regions, and the
 *  free area between them is where "now" and the figure are framed. */
export function useZones(deps: unknown[]): { zones: Zone[]; free: Insets } {
  const [state, setState] = useState<{ zones: Zone[]; free: Insets }>({ zones: [], free: { top: 0, right: 0, bottom: 0, left: 0 } })
  useEffect(() => {
    const measure = () => {
      const zones: Zone[] = []
      for (const sel of SELECTORS) {
        document.querySelectorAll<HTMLElement>(sel).forEach((el) => {
          const r = el.getBoundingClientRect()
          if (r.width > 0 && r.height > 0) zones.push({ x: r.left - 6, y: r.top - 6, w: r.width + 12, h: r.height + 12 })
        })
      }
      const W = innerWidth
      const H = innerHeight
      const rect = (sel: string) => document.querySelector(sel)?.getBoundingClientRect()
      const left = rect('.masthead')
      const right = rect('.reader') ?? rect('.drawer') ?? rect('.hud-right') ?? rect('.actions')
      const bottom = rect('.hud-bottom .narrate__box')
      const free = { top: 0, left: left ? left.right + 10 : 0, right: right ? W - right.left + 10 : 0, bottom: bottom ? H - bottom.top + 10 : 0 }
      setState((prev) => (JSON.stringify(prev) === JSON.stringify({ zones, free }) ? prev : { zones, free }))
    }
    measure()
    // cards unfold over a moment; measure again once they have settled
    const timers = [setTimeout(measure, 350), setTimeout(measure, 1500)]
    addEventListener('resize', measure)
    return () => {
      timers.forEach(clearTimeout)
      removeEventListener('resize', measure)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  return state
}
