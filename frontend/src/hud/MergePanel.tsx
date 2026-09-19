import { useEffect, useState, type FormEvent } from 'react'
import { BasisMark } from '../page/marks'
import { MEASURES, MeasuresBlock, markTone } from './MeasuresBlock'
import { theme } from '../theme'
import type { BranchView, Person, PossibleEvent, Question, ResearchStep, Scenario, Which } from '../types'

interface Props {
  scenario: Scenario
  paths: BranchView[] // every path of this decision, in order
  head: BranchView | null // the path selected and being lived
  which: Which
  busy: string | null
  error: string | null
  notice: string | null
  research: ResearchStep | null
  question: Question | null
  onHead: (branchId: string) => void
  onMerge: (confirm: string) => void
  onEvidence: (ids: string[]) => void
  onCommit: () => void
  onUndo: () => void
  onCompare: () => void
  onWhich: (w: Which) => void
  onInside: () => void
  onAnswer: (q: Question, a: string) => void
  onSkip: (q: Question) => void
  onModel: () => void
  /** commit one possibility as a step on this path: "assume this happens" */
  onAssume: (event: PossibleEvent) => void
  step: number | null
  person: Person | null
}

const WORD: Record<string, string> = { merged: 'chosen', faded: 'not taken', stale: 'closed', expired: 'closed' }

/** The right-hand panel: the decision, where HEAD is, and the merge that actually makes the choice. */
export function MergePanel(p: Props) {
  const { scenario, paths, head } = p
  const [confirming, setConfirming] = useState(false)
  const [typed, setTyped] = useState('')
  const [more, setMore] = useState(false) // narrow windows: the panel compacts to a bar; this opens the rest
  const [allEvents, setAllEvents] = useState(false)
  const [why, setWhy] = useState<string | null>(null)
  useEffect(() => (setConfirming(false), setTyped('')), [head?.branch.id, head?.branch.status])

  const decided = paths.find((b) => b.branch.status === 'merged') ?? null
  const canMerge = !!head && head.branch.status === 'open' && !head.branch.forming && head.years.length > 0
  const label = head?.branch.label ?? ''
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (typed.trim() === label) p.onMerge(label)
  }
  // most likely first. Until the backend sends probabilities, the agreement share of the last step stands in.
  const last = head?.years[head.years.length - 1]
  const pOf = (e: PossibleEvent) => e.probability ?? last?.outlook[e.key]?.probability ?? last?.outlook[e.key]?.share ?? null
  const events = [...(head?.branch.model.events ?? [])].sort((a, b) => (pOf(b) ?? -1) - (pOf(a) ?? -1))
  const lastCommit = head?.branch.commits[head.branch.commits.length - 1]

  return (
    <>
    <section className={`h-panel h-merge ${more ? 'is-expanded' : ''}`} aria-label="this decision">
      <header className="h-panel__head">
        <h2 title={scenario.situation}>{scenario.situation}</h2>
        <button type="button" className="h-link h-merge__more" onClick={() => setMore((v) => !v)}>{more ? 'Close' : 'Paths and actions'}</button>
      </header>

      <ul className="h-heads">
        {paths.map((b, i) => {
          const on = b.branch.id === head?.branch.id
          return (
            <li key={b.branch.id}>
              <button type="button" className={`h-path ${on ? 'is-on' : ''}`} onClick={() => p.onHead(b.branch.id)} title={on ? 'HEAD is here' : 'Move HEAD here'}>
                <b className="h-heads__head">{on ? 'HEAD →' : ''}</b>
                <i style={{ background: b.branch.status === 'open' ? theme.branch[i % theme.branch.length] : theme.color.ruin }} />
                <span>{b.branch.label}</span>
                {(WORD[b.branch.status] || b.branch.forming) && <em>{b.branch.forming ? 'forming' : WORD[b.branch.status]}</em>}
              </button>
            </li>
          )
        })}
      </ul>

      <div className="h-merge__rest">
        {p.question && head?.branch.status === 'open' && (
          <div className="h-ask">
            <p><b>{p.question.text}</b></p>
            <p className="h-muted">{p.question.why}</p>
            <p className="h-ask__choices">
              {p.question.choices.map((c) => <button key={c} type="button" className="h-chip" disabled={p.busy === `answer:${p.question!.id}`} onClick={() => p.onAnswer(p.question!, c)}>{c}</button>)}
              <button type="button" className="h-link" onClick={() => p.onSkip(p.question!)}>Skip</button>
            </p>
          </div>
        )}

        {p.research && (
          <p className="h-muted h-merge__research">
            {p.research.message}
            {p.research.url && <> · <a href={p.research.url} target="_blank" rel="noreferrer">{new URL(p.research.url).host.replace(/^www\./, '')}</a></>}
          </p>
        )}

        {head?.branch.measures && <MeasuresBlock measures={head.branch.measures} step={p.step} person={p.person} />}

        {events.length > 0 && (
          <>
            <h3>What could happen, most likely first</h3>
            <ul className="h-could">
              {events.slice(0, allEvents ? undefined : 5).map((e) => {
                const pr = pOf(e)
                const open = why === e.key
                return (
                  <li key={e.key}>
                    <button type="button" className="h-could__row" aria-expanded={open} onClick={() => setWhy(open ? null : e.key)} title="How this number was made">
                      <BasisMark basis={e.basis} />
                      <span className="h-could__label">{e.label}</span>
                      <span className="h-could__pct">{pr === null ? e.words : `${Math.round(pr * 100)}%`}</span>
                      {pr !== null && <i className="h-could__bar" style={{ width: `${Math.round(pr * 100)}%` }} />}
                    </button>
                    {head?.branch.status === 'open' && p.which === 'typical' && <button type="button" className="h-link h-could__commit" onClick={() => p.onAssume(e)} disabled={p.busy === 'commit'} title="Assume this happens: add it to this path as a step. You can undo it.">commit</button>}
                    {open && <Why event={e} onEvidence={p.onEvidence} />}
                  </li>
                )
              })}
            </ul>
            <p className="h-foot__row">
              {events.length > 5 && <button type="button" className="h-link" onClick={() => setAllEvents((v) => !v)}>{allEvents ? 'Fewer' : `${events.length - 5} more`}</button>}
              <button type="button" className="h-link" onClick={p.onModel}>How these numbers are made</button>
            </p>
          </>
        )}

        {head && (
          <ul className="h-actions">
            {head.branch.status === 'open' && p.which === 'typical' && <li><button type="button" onClick={p.onCommit} title="Add one step to this path. You can undo it.">Commit <kbd>K</kbd></button></li>}
            {head.branch.status === 'open' && p.which === 'typical' && <li><button type="button" onClick={p.onInside} title="Split this path here into two or more paths.">Branch <kbd>B</kbd></button></li>}
            {lastCommit && <li><button type="button" onClick={p.onUndo} disabled={p.busy === 'undo'} title="Remove your last commit.">Undo “{lastCommit.message}” <kbd>U</kbd></button></li>}
            {paths.length > 1 && <li><button type="button" onClick={() => p.onHead(paths[(paths.findIndex((x) => x.branch.id === head.branch.id) + 1) % paths.length].branch.id)} title="Move to another path.">Switch <kbd>S</kbd></button></li>}
            {paths.length > 1 && <li><button type="button" onClick={p.onCompare} title="Put the paths side by side.">Compare <kbd>C</kbd></button></li>}
            <li><button type="button" onClick={() => p.onWhich(p.which === 'typical' ? 'rare' : 'typical')} disabled={p.busy === 'rare'} title="The least likely version of this path. Nothing in it is impossible.">{p.which === 'typical' ? 'Rarest life' : 'Typical life'} <kbd>R</kbd></button></li>
          </ul>
        )}
      </div>
    </section>

    {/* THE merge control: the dark button with the branch glyph, pinned bottom-right at every size */}
    <div className="h-dock">
      {p.notice && <p className="h-note">{p.notice}</p>}
      {p.error && <p className="h-note h-note--error">{p.error}</p>}
      {confirming && head && (
        <form onSubmit={submit} className="h-panel h-merge__confirm">
          <label htmlFor="merge-confirm">Type “{label}” and press Enter</label>
          <input id="merge-confirm" className="h-input" autoFocus value={typed} onChange={(e) => setTyped(e.target.value)} onKeyDown={(e) => e.key === 'Escape' && setConfirming(false)} spellCheck={false} />
          <div>
            <button type="submit" className="h-primary" disabled={typed.trim() !== label || p.busy === 'merge'}>{p.busy === 'merge' ? 'Merging…' : 'Merge'}</button>
            <button type="button" className="h-link" onClick={() => setConfirming(false)}>Cancel</button>
          </div>
        </form>
      )}
      <p className="h-dock__note">
        {decided ? `Merged: “${decided.branch.label}” is on main. What lies ahead on it is still a projection.` : !head ? 'Select a path to live it. HEAD moves there.' : "Records this choice on main. It can't be undone. The life you walked through stays a simulation."}
      </p>
      {!decided && (
        <button type="button" className="actions__merge" disabled={!canMerge || confirming} onClick={() => setConfirming(true)} title={!head ? 'Select a path first' : canMerge ? 'This is what I actually chose. Permanent.' : head.branch.forming ? 'This path is still forming' : 'This path is closed'}>
          <svg viewBox="0 0 28 28" width={20} height={20} aria-hidden="true">
            <path d="M8 25 V14 C8 8 20 10 20 3 M20 25 V3" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" />
          </svg>
          {head ? <><span className="actions__merge-path">merge “{label}”</span><span>into main</span></> : <span>Pick a path to merge</span>}
        </button>
      )}
    </div>
    </>
  )
}


const pct = (x: number) => `${Math.round(x * 100)}%`
const BASE_WORDS = { sourced: 'Published rate', personal: 'From your own history', estimated: 'An estimate', background: 'Life-course tables' } as const

/** How one number was made: base rate, what your personality changed, what it depends on, and the count. */
function Why({ event, onEvidence }: { event: PossibleEvent; onEvidence: (ids: string[]) => void }) {
  const b = event.breakdown
  if (!b) return <div className="h-why"><p>{event.basis === 'estimated' ? 'An estimate: no published figure was found.' : event.basis === 'sourced' ? 'From a published figure.' : 'From the life-course tables.'} The full breakdown is not available for this path yet.</p></div>
  return (
    <div className="h-why">
      <p>
        <b>{BASE_WORDS[b.base.kind]}: {b.base.range ? `${pct(b.base.range[0])}–${pct(b.base.range[1])}` : pct(b.base.value)}</b>
        {b.base.reference_class ? ` · ${b.base.reference_class}` : ''}
        {b.base.evidence_id && <> · <button type="button" className="h-link" onClick={() => onEvidence([b.base.evidence_id!])}>source</button></>}
      </p>
      {b.base.note && <p className="h-muted">{b.base.note}</p>}
      {b.personality.map((t) => (
        <p key={t.trait}>
          You lean {t.z >= 0 ? 'more' : 'less'} toward {t.trait_name} than most → {Math.abs(t.shift_logodds) < 0.1 ? 'barely' : Math.abs(t.shift_logodds) < 0.35 ? 'a little' : 'noticeably'} {t.shift_logodds >= 0 ? 'more' : 'less'} likely
          <span className="h-muted"> ({t.basis === 'published' ? 'published effect' : 'assumed small effect'}; {t.confidence < 0.5 ? 'low' : 'fair'} confidence in the estimate)</span>
        </p>
      ))}
      {b.personality.length > 0 && <p>After personality: <b>{pct(b.adjusted)}</b></p>}
      {b.dependencies.map((d) => <p key={d.on}>Depends on “{d.label}”: ×{d.multiplier.toFixed(2)}</p>)}
      {event.effects && MEASURES.some((m) => event.effects![m]) && (
        <p className="h-effects">
          {MEASURES.filter((m) => event.effects![m]).map((m) => {
            const v = event.effects![m]
            const marks = (v > 0 ? '+' : '−').repeat(Math.abs(v))
            return <span key={m} className={`h-chip h-tiny--${markTone(marks)}`}>{m} {marks}</span>
          })}
          <span className="h-muted">{event.effects_basis === 'sourced' ? 'from a published figure' : 'a judgement'}</span>
        </p>
      )}
      <p>Happened in <b>{Math.round(b.simulated * 1000).toLocaleString()} of 1,000</b> simulated lives.</p>
    </div>
  )
}
