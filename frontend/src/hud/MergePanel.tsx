import { useEffect, useState } from 'react'
import type { Api } from '../api'
import { BasisMark } from '../page/marks'
import { MEASURES, MeasuresBlock, WORDS, markTone } from './MeasuresBlock'
import { theme } from '../theme'
import type { BranchView, Person, PossibleEvent, Question, ResearchStep, Scenario } from '../types'

interface Props {
  api: Api
  scenario: Scenario
  paths: BranchView[] // every path of this decision, in order
  head: BranchView | null // the path selected and being lived
  busy: string | null
  error: string | null
  notice: string | null
  research: ResearchStep | null
  question: Question | null
  onHead: (branchId: string) => void
  onMerge: (confirm: string) => void
  onCommit: () => void
  /** the commit box lives here now, not in a panel of its own */
  committing: boolean
  onCommitStep: (message: string) => Promise<void>
  onCancelCommit: () => void
  /** what is assumed on this path just now, by event key */
  assumed: string[]
  onDrop: (key: string) => void
  onUndo: () => void
  onCompare: () => void
  onInside: () => void
  onAnswer: (q: Question, a: string) => void
  onSkip: (q: Question) => void
  onModel: () => void
  /** open the numbers behind the recommendation, when this decision has them */
  onNumbers?: () => void
  /** commit a set of possibilities: "assume these happen". One commit, however many are ticked. */
  onPin: (keys: string[]) => void
  step: number | null
  person: Person | null
}

const WORD: Record<string, string> = { merged: 'chosen', faded: 'not taken', stale: 'closed', expired: 'closed' }

/** The right-hand panel: the decision, where HEAD is, and the merge that actually makes the choice. */
export function MergePanel(p: Props) {
  const [commitText, setCommitText] = useState('')
  const { scenario, paths, head } = p
  const [confirming, setConfirming] = useState(false)
  const [more, setMore] = useState(false) // narrow windows: the panel compacts to a bar; this opens the rest
  const [why, setWhy] = useState<string | null>(null)
  useEffect(() => setConfirming(false), [head?.branch.id, head?.branch.status])
  // a commit redraws the path; the tray starts empty again on the life that comes back

  const decided = paths.find((b) => b.branch.status === 'merged') ?? null
  const canMerge = !!head && head.branch.status === 'open' && !head.branch.forming && head.years.length > 0
  const label = head?.branch.label ?? ''
  // most likely first. Until the backend sends probabilities, the agreement share of the last step stands in.
  const last = head?.years[head.years.length - 1]
  const pOf = (e: PossibleEvent) => e.probability ?? last?.outlook[e.key]?.probability ?? last?.outlook[e.key]?.share ?? null
  // Earliest first: these are the things that could happen ON this path, in the order they could
  // happen. (They were ranked by probability, which made the order look arbitrary.)
  const events = [...(head?.branch.model.events ?? [])].sort((a, b) => {
    const at = (e: PossibleEvent) => (e.window?.[0] ?? 0) * 1000 - (pOf(e) ?? 0)
    return at(a) - at(b)
  })
  const lastCommit = head?.branch.commits[head.branch.commits.length - 1]
  const open = head?.branch.status === 'open' // only a path still open can take a pin

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
        {scenario.analysis && p.onNumbers && (
          <p className="h-merge__numbers"><button type="button" className="h-chip" onClick={p.onNumbers}>Show the numbers</button><span className="h-muted">{scenario.analysis.final ? scenario.analysis.headline : 'what it says so far'}</span></p>
        )}
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

        {events.length > 0 && (() => {
          // One at a time: the next thing that could happen WHERE THE GHOST STANDS. Move along the path
          // — a press, or a click on one of its circles — and this is the possibility of that point:
          // one whose own moment takes in this step, else the next one still ahead of it.
          const at = p.step ?? 0
          const live = (e: PossibleEvent) => !p.assumed.includes(e.key) && (e.probability ?? 0) < 0.999
          const next = events.find((e) => live(e) && e.window && at >= e.window[0] && at <= e.window[1])
            ?? events.find((e) => live(e) && (!e.window || e.window[1] >= at))
            ?? events.find(live)
          const mine = events.filter((e) => p.assumed.includes(e.key))
          return (
            <>
              {next && (
                <div className="h-next">
                  <p className="h-muted">Could happen here</p>
                  <p className="h-next__row">
                    <BasisMark basis={next.basis} />
                    <span className="h-next__label">{next.label}</span>
                    <span className="h-next__pct">{pct(next.probability)}</span>
                  </p>
                  <p className="h-foot__row">
                    <button type="button" className="h-link h-next__assume" disabled={!open || p.busy === 'commit'} onClick={() => p.onPin([next.key])}>
                      {p.busy === 'commit' ? 'redrawing' : 'Assume it'}
                    </button>
                    <button type="button" className="h-link" onClick={() => setWhy(why === next.key ? null : next.key)}>why</button>
                  </p>
                  {why === next.key && <Why event={next} api={p.api} />}
                </div>
              )}
              {mine.length > 0 && (
                <ul className="h-stage">
                  {mine.map((e) => (
                    <li key={e.key}>
                      <button type="button" className="h-stage__row is-on h-stage__pick" onClick={() => p.onDrop(e.key)} title="Take this assumption back">
                        <span className="h-stage__label">{e.label}</span>
                        <span className="h-stage__words">assumed</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              <p className="h-foot__row"><button type="button" className="h-link" onClick={p.onModel}>How these numbers are made</button></p>
            </>
          )
        })()}

        {head && p.committing && (
          <form
            className="h-commit"
            onSubmit={(e) => {
              e.preventDefault()
              const message = commitText.trim()
              if (message) void p.onCommitStep(message).then(() => setCommitText(''))
            }}
          >
            <label>
              <span>What you would do here</span>
              <input className="h-input" autoFocus value={commitText} onChange={(e) => setCommitText(e.target.value)} placeholder="in your own words" />
            </label>
            <p className="h-foot__row">
              <button type="submit" className="h-link" disabled={p.busy === 'commit' || !commitText.trim()}>{p.busy === 'commit' ? 'redrawing what follows' : 'commit'}</button>
              <button type="button" className="h-link" onClick={p.onCancelCommit}>never mind</button>
            </p>
          </form>
        )}

        {head && (
          <ul className="h-actions">
            {head.branch.status === 'open' && <li><button type="button" onClick={p.onCommit} title="Say what you would do at this moment; what follows is redrawn from it. You can undo it.">Commit <kbd>K</kbd></button></li>}
            {head.branch.status === 'open' && <li><button type="button" onClick={p.onInside} title="Split this path here into two or more paths.">Branch <kbd>B</kbd></button></li>}
            {lastCommit && <li><button type="button" onClick={p.onUndo} disabled={p.busy === 'undo'} title="Remove your last commit.">Undo “{lastCommit.message}” <kbd>U</kbd></button></li>}
            {paths.length > 1 && <li><button type="button" onClick={() => p.onHead(paths[(paths.findIndex((x) => x.branch.id === head.branch.id) + 1) % paths.length].branch.id)} title="Move to another path.">Switch <kbd>S</kbd></button></li>}
            {paths.length > 1 && <li><button type="button" onClick={p.onCompare} title="Put the paths side by side.">Compare <kbd>C</kbd></button></li>}
          </ul>
        )}
      </div>
    </section>

    {/* THE merge control: the dark button with the branch glyph, pinned bottom-right at every size */}
    <div className="h-dock">
      {p.notice && <p className="h-note">{p.notice}</p>}
      {p.error && <p className="h-note h-note--error">{p.error}</p>}
      {confirming && head && (
        <p className="h-panel h-merge__confirm">
          <span>Make “{label}” real on main? It can't be undone.</span>
          <span>
            <button type="button" className="h-primary" disabled={p.busy === 'merge'} onClick={() => p.onMerge(label)}>{p.busy === 'merge' ? 'Merging…' : 'Yes, merge'}</button>
            <button type="button" className="h-link" onClick={() => setConfirming(false)}>Cancel</button>
          </span>
        </p>
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


const pct = (x: number | undefined) => (typeof x === 'number' ? `${Math.round(x * 100)}%` : '')
const BASE_WORDS = { sourced: 'Published rate', personal: 'From your own history', estimated: 'An estimate', background: 'Life-course tables' } as const

/** How one number was made: base rate, what your personality changed, what it depends on, and the count. */
function Why({ event, api }: { event: PossibleEvent; api: Api }) {
  const b = event.breakdown
  if (!b) return <div className="h-why"><p>{event.basis === 'estimated' ? 'An estimate: no published figure was found.' : event.basis === 'sourced' ? 'From a published figure.' : 'From the life-course tables.'} The full breakdown is not available for this path yet.</p></div>
  return (
    <div className="h-why">
      <p>
        <b>{BASE_WORDS[b.base.kind]}: {b.base.range ? `${pct(b.base.range[0])}–${pct(b.base.range[1])}` : pct(b.base.value)}</b>
        {b.base.reference_class ? ` · ${b.base.reference_class}` : ''}
        {b.base.evidence_id && <> · <button type="button" className="h-link" onClick={() => void api.evidence({ ids: [b.base.evidence_id!] }).then(([ev]) => ev?.source_url && open(ev.source_url, '_blank', 'noopener'))}>source</button></>}
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
            return <span key={m} className={`h-chip h-tiny--${markTone(marks)}`}>{WORDS[m]} {marks}</span>
          })}
          <span className="h-muted">{event.effects_basis === 'sourced' ? 'from a published figure' : 'a judgement'}</span>
        </p>
      )}
      <p>Happened in <b>{Math.round(b.simulated * 1000).toLocaleString()} of 1,000</b> simulated lives.</p>
    </div>
  )
}
