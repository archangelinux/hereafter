import { useEffect, useRef, useState } from 'react'
import type { Action } from '../fixtures/decision'
import type { AnalysisView, Question } from '../types'

const pct = (x: number) => `${Math.round(x * 100)}%`

const THINK_MS = 650 // a beat after each answer
const READY_MS = 1300 // and the result takes a moment to arrive after the last one

interface Props {
  analysis: AnalysisView
  /** the path being looked at, or none for the decision as a whole */
  action: Action | null
  /** the next question, if any are left */
  question: Question | null
  answered: number
  total: number
  busy: boolean
  onAnswer: (q: Question, text: string) => void
}

/**
 * The side panel's headline. It asks its questions first and shows nothing until they are answered; then it
 * takes a moment; then it says, for the path selected (or the decision as a whole), the figure, the verdict and why.
 */
export function Summary({ analysis: a, action, question, answered, total, busy, onAnswer }: Props) {
  const [thinking, setThinking] = useState(false)
  const [ready, setReady] = useState(a.final)
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined)
  useEffect(() => () => clearTimeout(timer.current), [])
  // the result arrives a moment after the last answer, never with it (already-answered decisions show at once)
  useEffect(() => {
    setThinking(false)
    if (!a.final) return setReady(false)
    const t = setTimeout(() => setReady(true), ready ? 0 : READY_MS)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [a.final, question?.id])

  const ask = (q: Question, choice: string) => {
    setThinking(true)
    clearTimeout(timer.current)
    timer.current = setTimeout(() => onAnswer(q, choice), THINK_MS)
  }

  if (!a.final) {
    return (
      <section className="h-sum h-sum--ask" aria-label="A quick question">
        <p className="h-sum__lede">{answered === 0 ? 'A couple of quick questions first' : `Question ${answered + 1} of ${total}`}</p>
        {thinking ? (
          <p className="h-sum__thinking" role="status">Thinking<i /></p>
        ) : question && (
          <div className="h-sum__ask" key={question.id}>
            <p className="h-sum__q">{question.text}</p>
            <p className="h-sum__hint">{question.why}</p>
            <p className="h-sum__choices">
              {question.choices.map((c) => <button key={c} type="button" className="h-chip" disabled={busy} onClick={() => ask(question, c)}>{c}</button>)}
            </p>
          </div>
        )}
      </section>
    )
  }

  if (!ready) {
    return (
      <section className="h-sum h-sum--loading" role="status" aria-live="polite" aria-label="Working it out">
        <p className="h-sum__lede">Weighing what you told me…</p>
        <div className="h-sum__load" aria-hidden="true"><i /></div>
      </section>
    )
  }

  const view = action
    ? a.byPath[action]
    : { stat: pct(a.p), of: 'chance she’s interested', pick: a.headline, why: a.why, reasons: a.reasons }
  const published = a.sources.filter((s) => s.kind === 'published')

  return (
    <section className="h-sum" key={action ?? 'all'} aria-label="What the numbers say">
      <div className="h-sum__top">
        <b className="h-sum__pct" aria-live="polite">{view.stat}</b>
        <span className="h-sum__of">{view.of}</span>
      </div>
      {!action && <div className="h-sum__gauge" aria-hidden="true"><i style={{ width: pct(a.p) }} /><b style={{ left: pct(a.threshold) }} /></div>}

      <p className="h-sum__lede">{action ? 'For this path' : 'Where that leaves you'}</p>
      <p className="h-sum__pick">{view.pick}</p>
      <p className="h-sum__why">{view.why}</p>

      <ul className="h-sum__reasons">
        {view.reasons.map((r) => (
          <li key={r.text} className={`is-${r.effect}`}>
            <span aria-hidden="true">{r.effect === 'up' ? '↑' : r.effect === 'down' ? '↓' : '·'}</span>
            <span>{r.text}<em>{r.note}</em></span>
          </li>
        ))}
      </ul>

      {action && <p className="h-sum__best">Best overall: {a.headline}</p>}

      <details className="h-sum__src">
        <summary>Where this comes from</summary>
        <ul>{published.map((s) => <li key={s.id}><a href={s.url} target="_blank" rel="noreferrer">{s.cite}</a></li>)}</ul>
        <p>The starting chance, the size of each nudge and the points are assumptions for this demo. It is an illustration, not dating advice, and it knows nothing about her beyond your answers.</p>
      </details>
    </section>
  )
}
