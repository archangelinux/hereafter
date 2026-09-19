import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import type { Api } from '../api'
import { isByYear, stepDate } from '../format'
import { stepsOf, useChapters } from '../page/useChapters'
import type { BranchView, BranchYear, LivesResponse, Which } from '../types'

interface Props {
  api: Api
  view: BranchView
  which: Which
  rare: LivesResponse | null
  seek: { step: number; nonce: number } | null
  committing: boolean
  /** island view: the figure is still on its way to this step */
  walking: boolean
  /** island view: the text waits for the figure to arrive */
  followsFigure?: boolean
  busy: string | null
  onStep: (step: number) => void
  onEvidence: (ids: string[], step: BranchYear | null) => void
  onCollect: (ids: string[]) => void
  onCommit: (at: string, message: string) => Promise<void>
  onCancelCommit: () => void
  onReadAll: () => void
  onAdvance?: () => void
}

interface Para {
  text: string
  evidence: string[]
}

const WHEEL_MS = 600
const DIM_MS = 300
const typing = () => ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName ?? '')

/** Living a path, strictly one step at a time. A step is one dated thing on the path: step zero is the
 *  choice, then each event of the lived life, and each commit. One press moves one step, then waits. */
export function Narration(p: Props) {
  const { api, view, which, onStep, onCollect, onAdvance, walking } = p
  const years = which === 'rare' && p.rare ? p.rare.years : view.years
  const { chapters, loading, loadNext, done, key } = useChapters(api, view, which, years)
  const byYear = isByYear(years)

  // the stops: every step of the path on which something happens, and always step zero
  const stops = useMemo(() => {
    const commits = new Set(view.branch.commits.map((c) => Math.max(0, years.findIndex((y) => y.at >= c.at))))
    return years.map((_, i) => i).filter((i) => i === 0 || years[i].events.length > 0 || commits.has(i))
  }, [years, view.branch.commits])

  const [pos, setPos] = useState(0) // index into `stops`
  const [shown, setShown] = useState(0) // the stop whose text is on screen (lags `pos` while the figure walks)
  const [message, setMessage] = useState('')
  const queued = useRef<1 | -1 | null>(null)
  const lastWheel = useRef(0)
  const body = useRef<HTMLDivElement>(null)

  useEffect(() => (setPos(0), setShown(0)), [key])
  const step = stops[Math.min(pos, stops.length - 1)] ?? 0

  // the prose that belongs to each step: a chapter's paragraphs are dealt, in order, across that chapter's stops
  const proseByStep = useMemo(() => {
    const out = new Map<number, { title: string; paras: Para[] }>()
    for (const c of chapters) {
      const inside = stepsOf(c, years).map(({ i }) => i).filter((i) => stops.includes(i))
      if (!inside.length) continue
      c.paragraphs.forEach((para, n) => {
        const at = inside[Math.min(inside.length - 1, Math.floor((n * inside.length) / c.paragraphs.length))]
        const entry = out.get(at) ?? { title: c.title, paras: [] }
        entry.paras.push({ text: para.text, evidence: para.evidence_ids })
        out.set(at, entry)
      })
    }
    return out
  }, [chapters, years, stops])

  // chapters are fetched as far as the step being read
  const covered = chapters.length ? chapters[chapters.length - 1].to_at : ''
  useEffect(() => {
    if (!done && years[step] && years[step].at > covered) void loadNext()
  }, [step, covered, done, years, loadNext])

  // the cursor in both views follows the step; the text follows once the figure has arrived
  useEffect(() => onStep(step), [step, key]) // eslint-disable-line react-hooks/exhaustive-deps
  // In the island view the text changes when the figure ARRIVES: wait until it has set off and come to
  // rest again (with a short fallback for when it has nowhere to walk, e.g. reduced motion).
  const setOff = useRef(false)
  useEffect(() => {
    if (!p.followsFigure) return setShown(pos)
    if (walking) {
      setOff.current = true
      return
    }
    if (setOff.current) {
      setOff.current = false
      return setShown(pos)
    }
    const fallback = setTimeout(() => setShown(pos), 1200)
    return () => clearTimeout(fallback)
  }, [walking, pos, p.followsFigure])
  const [dimmed, setDimmed] = useState(false)
  useEffect(() => {
    if (shown === pos) return setDimmed(false)
    setDimmed(true)
    const timer = setTimeout(() => setDimmed(false), DIM_MS)
    return () => clearTimeout(timer)
  }, [shown, pos])

  const posRef = useRef(0)
  posRef.current = pos
  const move = useCallback((d: 1 | -1) => {
    const next = Math.max(0, Math.min(stops.length - 1, posRef.current + d))
    if (next === posRef.current) return
    if (next > posRef.current) onAdvance?.()
    setPos(next)
  }, [stops.length, onAdvance])

  /** one press, one step. While the figure is still walking, at most one further step is held. */
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

  // a step mark clicked on the line or in the scene: go there
  useEffect(() => {
    if (!p.seek) return
    const target = stops.findIndex((s) => s >= p.seek!.step)
    setPos(target < 0 ? stops.length - 1 : target)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p.seek])

  useEffect(() => {
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
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [press, walking, stops.length])

  const onWheel = (e: React.WheelEvent) => {
    const text = body.current
    if (text && text.scrollHeight > text.clientHeight + 1 && text.contains(e.target as Node)) return // a long step scrolls inside its box
    const t = Date.now()
    if (t - lastWheel.current < WHEEL_MS || Math.abs(e.deltaY) < 12) return
    lastWheel.current = t
    press(e.deltaY > 0 ? 1 : -1)
  }

  // what this step says
  const at = stops[Math.min(shown, stops.length - 1)] ?? 0
  const here = years[at]
  const prose = proseByStep.get(at)
  const commits = view.branch.commits.filter((c) => Math.max(0, years.findIndex((y) => y.at >= c.at)) === at)
  const paras: Para[] = prose?.paras ?? (here?.events ?? []).map((e) => ({ text: `${e.text}.`, evidence: typeof e.payload.evidence_id === 'string' ? [e.payload.evidence_id] : [] }))
  const arriving = shown !== pos

  useEffect(() => {
    body.current?.scrollTo({ top: 0 })
    const ids = [...paras.flatMap((x) => x.evidence), ...(here?.events ?? []).map((e) => e.payload.evidence_id).filter((x): x is string => typeof x === 'string')]
    if (ids.length) onCollect(ids)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [at, key, prose])

  const submitCommit = async (e: FormEvent) => {
    e.preventDefault()
    const when = years[step]?.at
    if (!when || !message.trim()) return
    await p.onCommit(when, message.trim())
    setMessage('')
  }

  const label = here ? stepDate(here.at, byYear) : ''

  return (
    <div className="narrate" onWheel={onWheel}>
      {p.committing ? (
        <form className="narrate__box narrate__box--commit" onSubmit={submitCommit}>
          <header className="narrate__head"><p className="caps">Commit a step · {years[step] ? stepDate(years[step].at, byYear) : ''}</p></header>
          <input className="h-input" autoFocus value={message} onChange={(e) => setMessage(e.target.value)} placeholder="ask for the transfer" aria-label="step" />
          <p className="narrate__note">Adds one step to this path. You can undo it.</p>
          <p className="narrate__controls caps">
            <span className="narrate__buttons">
              <button type="submit" disabled={p.busy === 'commit' || !message.trim()}>{p.busy === 'commit' ? 'redrawing what follows' : 'commit'}</button>
              <button type="button" onClick={p.onCancelCommit}>never mind</button>
            </span>
          </p>
        </form>
      ) : (
        <div className="narrate__box">
          <header className="narrate__head">
            <p className="caps">{at === 0 ? `The choice · ${label}` : label}{which === 'rare' ? ' · the rarest life here' : ''}</p>
            {prose && <h2 className="narrate__chapter">{prose.title}</h2>}
          </header>
          <div className={`narrate__body ${arriving && dimmed ? 'is-dimmed' : ''}`} ref={body} aria-live="polite">
            {arriving && !dimmed ? (
              <p className="narrate__text narrate__walking">walking…</p>
            ) : (
              <>
                {commits.map((c) => <p key={c.id} className="narrate__text narrate__commit">Your commit · {label} — {c.message}</p>)}
                {paras.length === 0 && commits.length === 0 && <p className="narrate__text">{loading ? 'Being written…' : 'Nothing marked here.'}</p>}
                {paras.map((para, n) => (
                  <p key={n} className="narrate__text">
                    {para.text}
                    {para.evidence.length > 0 && (
                      <button type="button" className="note" onClick={() => p.onEvidence(para.evidence, here ?? null)} aria-label="see the evidence for this" title="see the evidence for this">
                        {para.evidence.map((_, k) => <i key={k} />)}
                      </button>
                    )}
                  </p>
                ))}
              </>
            )}
          </div>
          <p className="narrate__controls caps">
            <span className="narrate__position">
              <button type="button" onClick={() => press(-1)} disabled={pos === 0} aria-label="one step back" title="One step back (←)">←</button>
              step {pos + 1} of {stops.length}
              <button type="button" onClick={() => press(1)} disabled={pos >= stops.length - 1} aria-label="one step forward" title="One step forward (Space or →)">→</button>
            </span>
            {pos < stops.length - 1 ? <button type="button" onClick={() => press(1)}><kbd>space</kbd> next step</button> : <span>the simulation stops looking here</span>}
            <button type="button" onClick={p.onReadAll}>read the whole chapter</button>
          </p>
        </div>
      )}
    </div>
  )
}
