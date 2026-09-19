import { useEffect, useState, type FormEvent } from 'react'
import type { Api } from '../api'
import { theme } from '../theme'
import type { BranchView, Horizon, OptionDraft, ResearchResponse, Scenario } from '../types'
import { Sheet } from './Sheet'

const EXAMPLES = [
  'Noor texted for the first time since March. Answer tonight, in the morning, or not at all?',
  'A month without drinking, starting Monday, or just cutting back?',
  'The party on Friday or the problem set due Saturday?',
  'Lend my brother the money, part of it, or say no?',
  'Take the offer in San Francisco, stay for the master’s, or the bank job in Toronto?',
]

const HORIZONS: { label: string; value: Horizon | null }[] = [
  { label: 'let Hereafter judge', value: null },
  { label: 'tonight and the days after', value: { unit: 'days', count: 10 } },
  { label: 'weeks', value: { unit: 'weeks', count: 12 } },
  { label: 'months', value: { unit: 'months', count: 12 } },
  { label: 'years', value: { unit: 'years', count: 40 } },
]

interface Props {
  api: Api
  personId: string
  onMade: (scenario: Scenario, branches: BranchView[]) => void
  onEnter: (branchId: string) => void
  onClose?: () => void
  /** decide something inside this life: the new decision forks from that branch instead of from now */
  assuming?: BranchView | null
  /** the live branches, so a placeholder can be seen filling in */
  views: BranchView[]
  onWatch: () => void
}

const blank = (): OptionDraft => ({ title: '', details: '', deadline: '' })

export function Composer({ api, personId, onMade, onEnter, onClose, assuming, views, onWatch }: Props) {
  const [situation, setSituation] = useState('')
  const [options, setOptions] = useState<OptionDraft[]>([blank(), blank()])
  const [horizon, setHorizon] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [made, setMade] = useState<{ scenario: Scenario; branches: BranchView[] } | null>(null)
  const [feeds, setFeeds] = useState<Record<string, ResearchResponse>>({})

  const set = (i: number, patch: Partial<OptionDraft>) => setOptions((o) => o.map((x, n) => (n === i ? { ...x, ...patch } : x)))
  const ready = situation.trim().length > 0 && options.filter((o) => o.title.trim()).length >= 2

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!ready) return
    setBusy(true)
    setError(null)
    try {
      const drafts = options.filter((o) => o.title.trim()).map((o) => ({ title: o.title.trim(), details: o.details.trim(), ...(o.deadline ? { deadline: o.deadline } : {}) }))
      const res = await api.createScenario(personId, situation.trim(), drafts, { ...(HORIZONS[horizon].value ? { horizon: HORIZONS[horizon].value! } : {}), ...(assuming ? { assuming_branch_id: assuming.branch.id } : {}) })
      setMade(res)
      onMade(res.scenario, res.branches)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'That did not go through. Nothing was changed.')
    } finally {
      setBusy(false)
    }
  }

  // while the branches form: what Hereafter is reading about each option, as it reads
  useEffect(() => {
    if (!made) return
    let live = true
    const poll = async () => {
      const next = await Promise.all(made.branches.map((b) => api.research(b.branch.id).catch(() => null)))
      if (!live) return
      setFeeds(Object.fromEntries(next.filter((r): r is ResearchResponse => !!r).map((r) => [r.branch_id, r])))
      if (next.some((r) => r && (r.research === 'pending' || r.research === 'running'))) timer = setTimeout(poll, theme.motion.busyPollMs)
    }
    let timer = setTimeout(poll, 300)
    return () => {
      live = false
      clearTimeout(timer)
    }
  }, [made, api])

  if (made) {
    const settled = made.branches.every((b) => ['done', 'failed', 'none'].includes(feeds[b.branch.id]?.research ?? 'pending'))
    return (
      <Sheet title={`${['No', 'One', 'Two', 'Three', 'Four'][made.branches.length] ?? 'Several'} lives are being drawn`} eyebrow="branching" lede={`“${made.scenario.situation}”`} onClose={onClose} wide>
        <div className="forming">
          {made.branches.map((b, i) => {
            const feed = feeds[b.branch.id]
            const current = views.find((v) => v.branch.id === b.branch.id) ?? b
            const drawn = current.years.length > 0 && !current.branch.forming
            return (
              <section key={b.branch.id} className="forming__branch" style={{ ['--accent' as string]: theme.branch[i % theme.branch.length] }}>
                <h2>{b.branch.label}</h2>
                <p className="caps">{!drawn ? 'being drawn' : feed?.research === 'done' ? 'read, and simulated again with what was found' : feed?.research === 'failed' ? 'nothing could be read; simulated from the tables alone' : feed?.research === 'none' ? 'simulated' : 'Hereafter is reading'}</p>
                <ol className="feed">
                  {(feed?.steps ?? []).map((s, n) => (
                    <li key={n} className={`feed__step feed__step--${s.state}`}>
                      <span>{s.message}</span>
                      {s.url && <a href={s.url} target="_blank" rel="noreferrer">{hostOf(s.url)}</a>}
                      {s.session_url && <a className="feed__session" href={s.session_url} target="_blank" rel="noreferrer">watch the browser session</a>}
                    </li>
                  ))}
                </ol>
                <button type="button" className="verb" disabled={!drawn} onClick={() => onEnter(b.branch.id)}>{drawn ? 'live this one' : 'not yet walkable'}</button>
              </section>
            )
          })}
        </div>
        <p className="sheet__foot"><button type="button" className="verb verb--primary" onClick={onWatch}>watch them take shape</button></p>
        <p className="sheet__foot dim">{settled ? 'Everything found has been folded in.' : 'You can start reading now; a branch redraws itself quietly when its research lands.'}</p>
      </Sheet>
    )
  }

  return (
    <Sheet
      title="What are you deciding?"
      eyebrow={assuming ? `inside “${assuming.branch.label}”` : 'a new decision'}
      lede={assuming
        ? `Assuming you are living “${assuming.branch.label}”: what would you be deciding there? These branches fork from that life, not from now.`
        : 'Anything you are turning over, large or small. One sentence and the names of the things you could do are enough; Hereafter fills in the rest from what it already knows, reads up on each option, and only then asks. Each option becomes a branch you can live through before you choose.'}
      onClose={onClose}
      wide
    >
      <form onSubmit={submit} className="composer">
        <label className="field">
          <span className="caps">the situation</span>
          <textarea value={situation} onChange={(e) => setSituation(e.target.value)} rows={3} placeholder={EXAMPLES[0]} />
        </label>
        <p className="composer__examples">
          <span className="caps">for instance</span>
          {EXAMPLES.slice(1).map((ex) => (
            <button key={ex} type="button" className="quiet" onClick={() => setSituation(ex)}>{ex}</button>
          ))}
        </p>

        <div className="options">
          {options.map((o, i) => (
            <fieldset key={i} className="option" style={{ ['--accent' as string]: theme.branch[i % theme.branch.length] }}>
              <legend className="caps">option {'abcd'[i]}</legend>
              <input value={o.title} onChange={(e) => set(i, { title: e.target.value })} placeholder={['Answer tonight', 'Answer in the morning', 'Leave it', 'Something else'][i]} aria-label="what you would do" />
              <textarea value={o.details} onChange={(e) => set(i, { details: e.target.value })} rows={3} placeholder="Optional. In your own words: what, where, with whom, what it costs, what you are afraid of." aria-label="details, optional" />
              <label className="option__deadline">
                <span className="caps">open until</span>
                <input type="date" value={o.deadline ?? ''} onChange={(e) => set(i, { deadline: e.target.value })} />
              </label>
              {options.length > 2 && <button type="button" className="quiet" onClick={() => setOptions((all) => all.filter((_, n) => n !== i))}>remove</button>}
            </fieldset>
          ))}
          {options.length < 4 && (
            <button type="button" className="option option--add" onClick={() => setOptions((all) => [...all, blank()])}>
              <span className="caps">another option</span>
            </button>
          )}
        </div>

        <fieldset className="horizon">
          <legend className="caps">how far to look</legend>
          {HORIZONS.map((h, i) => (
            <label key={h.label} className={horizon === i ? 'is-on' : ''}>
              <input type="radio" name="horizon" checked={horizon === i} onChange={() => setHorizon(i)} />
              {h.label}
            </label>
          ))}
        </fieldset>

        {error && <p className="page__error">{error}</p>}
        <div className="sheet__actions">
          <button type="submit" className="verb verb--primary" disabled={!ready || busy}>{busy ? 'drawing the branches' : 'branch'}</button>
          <span className="dim">Nothing here is real until you merge one of them.</span>
        </div>
      </form>
    </Sheet>
  )
}

const hostOf = (url: string) => {
  try {
    return new URL(url).host.replace(/^www\./, '')
  } catch {
    return url
  }
}
