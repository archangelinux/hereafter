import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import type { Api } from '../api'
import { stepsOf, useChapters } from '../page/useChapters'
import type { BranchView, BranchYear, LivesResponse, Which } from '../types'

interface Beat {
  text: string
  evidence: string[]
  step: number
  chapter: string
}

interface Props {
  api: Api
  view: BranchView
  which: Which
  rare: LivesResponse | null
  seek: { step: number; nonce: number } | null
  committing: boolean
  /** island view: the figure is still on its way to this step, so the lines wait for it */
  walking: boolean
  busy: string | null
  onStep: (step: number) => void
  onEvidence: (ids: string[], step: BranchYear | null) => void
  onCollect: (ids: string[]) => void
  onCommit: (at: string, message: string) => Promise<void>
  onCancelCommit: () => void
  onReadAll: () => void
}

const BEAT_CHARS = 210
const typing = () => ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName ?? '')

/** A few lines at a time, the way a storybook game tells it. The figure walks as you read. */
export function Narration(p: Props) {
  const { api, view, which, onStep, onCollect } = p
  const years = which === 'rare' && p.rare ? p.rare.years : view.years
  const { chapters, loading, loadNext, done, key } = useChapters(api, view, which, years)
  const [index, setIndex] = useState(0)
  const [message, setMessage] = useState('')
  const pendingSeek = useRef<number | null>(null)
  const lastWheel = useRef(0)

  const beats = useMemo(() => {
    const out: Beat[] = []
    for (const c of chapters) {
      const steps = stepsOf(c, years)
      if (!steps.length) continue
      c.paragraphs.forEach((para, n) => {
        const step = steps[Math.min(steps.length - 1, Math.floor((n * steps.length) / c.paragraphs.length))].i
        const sentences = para.text.match(/[^.!?…]+[.!?…]+["”’)]*\s*|.+$/g) ?? [para.text]
        let current = ''
        const chunks: string[] = []
        for (const s of sentences) {
          if (current && (current + s).length > BEAT_CHARS) {
            chunks.push(current.trim())
            current = ''
          }
          current += s
        }
        if (current.trim()) chunks.push(current.trim())
        chunks.forEach((text, k) => out.push({ text, step, chapter: c.title, evidence: k === chunks.length - 1 ? para.evidence_ids : [] }))
      })
    }
    return out
  }, [chapters, years])

  useEffect(() => setIndex(0), [key])

  const beat = beats[Math.min(index, beats.length - 1)] as Beat | undefined
  const step = beat?.step ?? 0
  const atEnd = done && index >= beats.length - 1

  // the figure walks with the reading; landmarks announce themselves as it arrives
  useEffect(() => {
    if (!beat) return
    onStep(step)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, key, beats.length > 0])

  useEffect(() => {
    if (beat?.evidence.length) onCollect(beat.evidence)
    const sourced = (years[step]?.events ?? []).map((e) => e.payload.evidence_id).filter((id): id is string => typeof id === 'string')
    if (sourced.length) onCollect(sourced)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index, key])

  useEffect(() => {
    if (beats.length - index < 4 && !done) void loadNext()
  }, [beats.length, index, done, loadNext])

  const go = useCallback((d: 1 | -1) => setIndex((i) => Math.max(0, Math.min(beats.length - 1, i + d))), [beats.length])

  // a landmark clicked in the world or on the line: read from there
  useEffect(() => {
    if (p.seek) pendingSeek.current = p.seek.step
  }, [p.seek])
  useEffect(() => {
    const target = pendingSeek.current
    if (target === null) return
    const found = beats.findIndex((b) => b.step >= target)
    if (found >= 0) {
      setIndex(found)
      pendingSeek.current = null
    } else if (!done) void loadNext()
    else pendingSeek.current = null
  }, [p.seek, beats, done, loadNext])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (typing() || e.metaKey || e.ctrlKey || e.altKey) return
      if (e.key === ' ' || e.key === 'ArrowRight' || e.key === 'ArrowDown') (e.preventDefault(), go(1))
      else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') (e.preventDefault(), go(-1))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [go])

  const onWheel = (e: React.WheelEvent) => {
    const t = Date.now()
    if (t - lastWheel.current < 420 || Math.abs(e.deltaY) < 12) return
    lastWheel.current = t
    go(e.deltaY > 0 ? 1 : -1)
  }

  const submitCommit = async (e: FormEvent) => {
    e.preventDefault()
    const at = years[step]?.at
    if (!at || !message.trim()) return
    await p.onCommit(at, message.trim())
    setMessage('')
  }

  const label = years[step]?.label ?? ''
  const sentences = beat ? (beat.text.match(/[^.!?…]+[.!?…]+["”’)]*\s*|.+$/g) ?? [beat.text]) : []

  return (
    <div className="narrate" onWheel={onWheel}>
      {p.committing ? (
        <form className="narrate__box narrate__box--commit" onSubmit={submitCommit}>
          <p className="caps narrate__when">{label} · a commit on this branch</p>
          <input autoFocus value={message} onChange={(e) => setMessage(e.target.value)} placeholder="What do you do differently here?" aria-label="what you do differently" />
          <p className="narrate__hint">
            <span>Everything after this is simulated again. It is only a what-if: undo takes it back completely.</span>
            <span className="narrate__buttons">
              <button type="submit" className="verb" disabled={p.busy === 'commit' || !message.trim()}>{p.busy === 'commit' ? 'redrawing' : 'commit'}</button>
              <button type="button" className="quiet" onClick={p.onCancelCommit}>never mind</button>
            </span>
          </p>
        </form>
      ) : (
        <div className="narrate__box" onClick={(e) => !(e.target as HTMLElement).closest('button, a') && go(1)} role="button" tabIndex={0} aria-label="go on">
          <p className="narrate__when">
            <span className="caps">{label}</span>
            {beat && <span className="narrate__chapter">{beat.chapter}</span>}
            {p.walking && <span className="narrate__walking">walking there</span>}
            {which === 'rare' && <span className="narrate__strange">the rarest life here</span>}
          </p>
          <p className="narrate__text" key={`${key}:${index}`} aria-live="polite">
            {!beat && (loading ? 'The path is being read out…' : 'Nothing is written here yet.')}
            {sentences.map((s, n) => (
              <span key={n} style={{ animationDelay: `${n * 420}ms`, animationPlayState: p.walking ? 'paused' : 'running' }}>{s}</span>
            ))}
            {beat && beat.evidence.length > 0 && (
              <button type="button" className="note" onClick={() => p.onEvidence(beat.evidence, years[step])} aria-label="the evidence for this" title="the evidence for this">
                {beat.evidence.map((_, k) => <i key={k} />)}
              </button>
            )}
          </p>
          <p className="narrate__hint">
            <span>{atEnd ? 'Here the simulation stops looking. The rest is not known.' : <><kbd>space</kbd> to go on{index > 0 && <> · <kbd>←</kbd> back</>}</>}</span>
            <button type="button" className="quiet" onClick={p.onReadAll}>read the whole chapter</button>
          </p>
        </div>
      )}
    </div>
  )
}
