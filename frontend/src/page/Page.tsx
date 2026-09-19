import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import type { Api } from '../api'
import { likelihoodWords, stateWords } from '../derive'
import { dayLabel, deadlineOf, isByYear, sentence, stepDate } from '../format'
import { basisOf } from '../line/layout'
import { theme } from '../theme'
import type { Basis, BranchView, BranchYear, LivesResponse, Scenario, Which } from '../types'
import { BasisMark, Wave } from './marks'
import { stepsOf, useChapters } from './useChapters'

interface Props {
  api: Api
  view: BranchView
  scenario: Scenario | null
  accent: string
  which: Which
  rare: LivesResponse | null
  seek: { step: number; nonce: number } | null
  busy: string | null
  error: string | null
  onHere: (step: number) => void
  onEvidence: (ids: string[], step: BranchYear | null) => void
  onCommit: (at: string, message: string) => Promise<void>
  onPick: (eventId: string) => void
  onClose: () => void
}

const STATUS_LINE: Record<string, string> = {
  open: 'an open branch',
  merged: 'merged into main: this is what you chose',
  faded: 'a road not taken: closed, still readable',
  stale: 'stale: it can be read, but no longer merged',
}

export function Page(p: Props) {
  const { api, view, which, onHere } = p
  const { branch } = view
  const years = which === 'rare' && p.rare ? p.rare.years : view.years
  const [commitAt, setCommitAt] = useState<string | null>(null)
  const [message, setMessage] = useState('')
  const scroller = useRef<HTMLDivElement>(null)
  const sentinel = useRef<HTMLDivElement>(null)
  const { chapters, loading, loadNext, done, key } = useChapters(api, view, which, years)

  const long = (p.scenario?.horizon.unit ?? 'years') === 'years'
  const byYear = isByYear(years)
  const when = (y: BranchYear) => stepDate(y.at, byYear)
  const open = branch.status === 'open'
  const closed = branch.status === 'faded' || branch.status === 'stale'

  useEffect(() => {
    setCommitAt(null)
    scroller.current?.scrollTo({ top: 0 })
  }, [key])

  // later chapters arrive as the reader approaches the end
  useEffect(() => {
    const el = sentinel.current
    if (!el) return
    const io = new IntersectionObserver((entries) => entries[0].isIntersecting && void loadNext(), { root: scroller.current, rootMargin: '500px' })
    io.observe(el)
    return () => io.disconnect()
  }, [loadNext])

  // the reader's place: the step nearest a line a third of the way down the page
  const onScroll = useCallback(() => {
    const root = scroller.current
    if (!root) return
    const mark = root.getBoundingClientRect().top + root.clientHeight * 0.36
    let best = -1
    let bestDist = Infinity
    root.querySelectorAll<HTMLElement>('[data-step]').forEach((el) => {
      const d = Math.abs(el.getBoundingClientRect().top - mark)
      if (d < bestDist) {
        bestDist = d
        best = Number(el.dataset.step)
      }
    })
    if (best >= 0) onHere(best)
  }, [onHere])
  useEffect(onScroll, [chapters, onScroll])

  // a node clicked on the line: load as far as that step, then bring it into view
  useEffect(() => {
    if (!p.seek) return
    const el = scroller.current?.querySelector<HTMLElement>(`[data-step="${p.seek.step}"]`)
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    else void loadNext()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p.seek, chapters.length])

  const submitCommit = async (e: FormEvent) => {
    e.preventDefault()
    if (!commitAt || !message.trim()) return
    await p.onCommit(commitAt, message.trim())
    setMessage('')
    setCommitAt(null)
  }

  const deadline = deadlineOf(branch.precondition)
  const option = p.scenario?.options.find((o) => o.id === branch.option_id)
  const assumed = p.scenario?.assuming_branch_id ?? null

  return (
    <div className="page" ref={scroller} onScroll={onScroll} style={{ ['--accent' as string]: closed ? theme.color.textDim : branch.status === 'merged' ? theme.color.text : p.accent }}>
      <button type="button" className="quiet page__close" onClick={p.onClose}>fold the page away</button>
      <header className="page__head">
        {assumed && <p className="caps page__assuming">decided inside another life, not from now</p>}
        {p.scenario && <p className="page__situation">“{p.scenario.situation}”</p>}
        <p className="caps page__status">
          {STATUS_LINE[branch.status] ?? branch.status}
          {open && deadline ? ` · open until ${dayLabel(deadline)}` : ''}
          {branch.status === 'stale' && deadline ? ` · closed ${dayLabel(deadline)}` : ''}
        </p>
        <h1 className="page__title">{branch.label}</h1>
        {option?.details && <p className="page__details">{option.details}</p>}

        {which === 'rare' && p.rare && (
          <p className="page__rare">
            {p.rare.rarity_words}
          </p>
        )}
        {p.error && <p className="page__error">{p.error}</p>}
        <Wave className="page__wave" width={260} />
      </header>

      {chapters.map((c) => {
        const steps = stepsOf(c, years)
        const span = steps.length ? (steps.length === 1 ? when(steps[0].y) : `${when(steps[0].y)} to ${when(steps[steps.length - 1].y)}`) : ''
        return (
          <article key={c.from_at} className={`chapter ${c.status === 'writing' ? 'chapter--writing' : ''} ${/^[\p{L}“"]/u.test(c.paragraphs[0]?.text ?? '') ? 'chapter--prose' : ''}`}>
            <header>
              <p className="caps chapter__span">{span}</p>
              <h2 className="chapter__title">{c.title}</h2>
              {c.status === 'writing' && <p className="chapter__writing">Being written…</p>}
            </header>
            <div className="chapter__body">
              <div className="chapter__prose">
                {c.paragraphs.map((para, n) => (
                  <p key={n}>
                    {para.text}
                    {para.evidence_ids.length > 0 && (
                      <button type="button" className="note" onClick={() => p.onEvidence(para.evidence_ids, steps[0]?.y ?? null)} aria-label="the evidence for this paragraph" title="the evidence for this">
                        {para.evidence_ids.map((_, k) => (
                          <i key={k} />
                        ))}
                      </button>
                    )}
                  </p>
                ))}
              </div>
              <aside className="chapter__margin" aria-label="what the simulation settled in this stretch">
                {steps.map(({ y, i }) => (
                  <div key={y.at} className="step" data-step={i}>
                    <p className="caps step__label">{when(y)}</p>
                    {y.events.length === 0 && <p className="step__quiet">nothing marked</p>}
                    {y.events.map((e) => {
                      const basis: Basis = basisOf(e)
                      const evidenceId = typeof e.payload.evidence_id === 'string' ? e.payload.evidence_id : null
                      return (
                        <div key={e.id} className="step__event">
                          <BasisMark basis={basis} />
                          <div>
                            <p>{sentence(e.text)}</p>
                            <p className="step__meta">
                              <span className="caps">{e.domain}</span> · {likelihoodWords(y.solidity)}
                              {basis === 'estimated' && ' · an estimate, no published figure found'}
                              {evidenceId && (
                                <>
                                  {' · '}
                                  <button type="button" className="quiet" onClick={() => p.onEvidence([evidenceId], y)}>the evidence</button>
                                </>
                              )}
                              {closed && !branch.carried_event_id && which === 'typical' && (
                                <>
                                  {' · '}
                                  <button type="button" className="quiet quiet--gold" onClick={() => p.onPick(e.id)}>pick this</button>
                                </>
                              )}
                              {branch.carried_event_id === e.id && <span className="step__picked"> · picked onto main</span>}
                            </p>
                          </div>
                        </div>
                      )
                    })}
                    <p className="step__actions">
                      <button type="button" className="quiet" onClick={() => p.onEvidence([], y)}>how the thousand lives spread</button>
                      {open && which === 'typical' && (
                        <button type="button" className="quiet" onClick={() => (setCommitAt(y.at), setMessage(''))}>commit a step here</button>
                      )}
                    </p>
                    {commitAt === y.at && (
                      <form className="commit" onSubmit={submitCommit}>
                        <label className="caps" htmlFor={`commit-${i}`}>{when(y)}: step</label>
                        <input id={`commit-${i}`} autoFocus value={message} onChange={(e) => setMessage(e.target.value)} placeholder="I say no to the second date" />
                        <p className="commit__note">Adds one step to this path. You can undo it.</p>
                        <div>
                          <button type="submit" className="verb" disabled={p.busy === 'commit' || !message.trim()}>{p.busy === 'commit' ? 'redrawing what follows' : 'commit'}</button>
                          <button type="button" className="quiet" onClick={() => setCommitAt(null)}>never mind</button>
                        </div>
                      </form>
                    )}
                    {branch.commits.filter((cm) => cm.at === y.at || (cm.at.slice(0, 4) === y.at.slice(0, 4) && long)).map((cm) => (
                      <p key={cm.id} className="step__commit"><BasisMark basis="commit" /> your commit: “{cm.message}”</p>
                    ))}
                    {long && y.state.alive && <p className="step__background">in the background: {stateWords(y.state)}</p>}
                  </div>
                ))}
              </aside>
            </div>
          </article>
        )
      })}

      <div ref={sentinel} className="page__end">
        {loading ? <span className="dim">turning the page</span> : done ? <span className="dim">Here the simulation stops looking. The rest is not known.</span> : null}
      </div>
    </div>
  )
}

