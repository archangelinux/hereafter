import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { BranchView } from '../types'

const WHEEL_MS = 600
const typing = () => ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName ?? '')

/**
 * Living a path, strictly one step at a time: one press of space (or an arrow) moves the cursor
 * exactly one step and waits. A step is one dated thing on the path — the choice it begins with,
 * each thing that happens, each commit. Nothing about it is on screen: what happens at the step
 * is read in the world itself, beside the ghost.
 */
export function useSteps(p: {
  view: BranchView | null
  seek: { step: number; nonce: number } | null
  /** island view: the figure is still walking to this step */
  walking: boolean
  followsFigure: boolean
  onStep: (step: number | null) => void
  onAdvance?: () => void
}) {
  const { view, walking, onStep, onAdvance } = p
  const years = view?.years ?? []
  const key = view ? `${view.branch.id}:${view.branch.revision}` : ''

  const stops = useMemo(() => {
    if (!view) return []
    const commits = new Set(view.branch.commits.map((c) => Math.max(0, years.findIndex((y) => y.at >= c.at))))
    return years.map((_, i) => i).filter((i) => i === 0 || years[i].events.length > 0 || commits.has(i))
  }, [view, years])

  const [pos, setPos] = useState(0)
  const queued = useRef<1 | -1 | null>(null)
  const posRef = useRef(0)
  posRef.current = pos
  useEffect(() => setPos(0), [key])

  const step = stops[Math.min(pos, stops.length - 1)] ?? 0
  useEffect(() => onStep(view ? step : null), [step, key]) // eslint-disable-line react-hooks/exhaustive-deps

  const move = useCallback((d: 1 | -1) => {
    const next = Math.max(0, Math.min(stops.length - 1, posRef.current + d))
    if (next === posRef.current) return
    if (next > posRef.current) onAdvance?.()
    setPos(next)
  }, [stops.length, onAdvance])

  /** one press, one step; while the figure walks, at most one further step is held */
  const press = useCallback((d: 1 | -1) => {
    if (walking) queued.current = d
    else move(d)
  }, [walking, move])
  useEffect(() => {
    if (walking || queued.current === null) return
    const d = queued.current
    queued.current = null
    move(d)
  }, [walking, move])

  useEffect(() => {
    if (!p.seek) return
    const target = stops.findIndex((s) => s >= p.seek!.step)
    setPos(target < 0 ? stops.length - 1 : target)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p.seek])

  useEffect(() => {
    if (!view) return
    const onKey = (e: KeyboardEvent) => {
      if (typing() || e.metaKey || e.ctrlKey || e.altKey) return
      const forward = e.key === ' ' || e.key === 'ArrowRight' || e.key === 'ArrowDown'
      const back = e.key === 'ArrowLeft' || e.key === 'ArrowUp'
      if (!forward && !back && e.key !== 'Home' && e.key !== 'End') return
      e.preventDefault()
      if (e.key === 'Home') return setPos(0)
      if (e.key === 'End') return setPos(stops.length - 1)
      if (e.repeat && !walking) return // holding a key down does not run through the path
      press(forward ? 1 : -1)
    }
    const onWheel = (e: WheelEvent) => {
      if (typing() || Math.abs(e.deltaY) < 12) return
      const now = Date.now()
      if (now - lastWheel.current < WHEEL_MS) return
      lastWheel.current = now
      press(e.deltaY > 0 ? 1 : -1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // the wheel belongs to the world (it zooms); stepping is by key and by click only
    void onWheel
  }, [press, walking, stops.length, view])
  const lastWheel = useRef(0)

  return { step, pos, stops, press, at: years[step] ?? null }
}
