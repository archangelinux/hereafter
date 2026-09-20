import { useCallback, useEffect, useState } from 'react'
import type { Api } from '../api'
import type { EvidenceHealth, ModelCard } from '../types'
import { Sheet } from './Sheet'

/** How the numbers are made: the model card, in plain words. */
export function ModelSheet({ api, personId, onClose }: { api: Api; personId: string; onClose: () => void }) {
  const [card, setCard] = useState<ModelCard | null>(null)
  useEffect(() => void api.model().then(setCard).catch(() => undefined), [api])
  return (
    <Sheet title="How these numbers are made" eyebrow={card ? `model ${card.version}` : undefined} lede={card?.summary} onClose={onClose}>
      {!card && <p className="dim">Loading…</p>}
      {card && (
        <div className="model">
          <ol>{card.steps.map((s) => <li key={s.title}><b>{s.title}.</b> {s.text}</li>)}</ol>
          {card.constants.length > 0 && <><h2>Constants</h2><dl>{card.constants.map((c) => [<dt key={c.name}>{c.name}{c.value !== '' ? ` = ${c.value}` : ''}</dt>, <dd key={c.name + 'm'}>{c.meaning}</dd>])}</dl></>}
          {!card.steps.some((x) => /measure/i.test(x.title)) && (
            <><h2>Four measures</h2><p>Health, joy (short term), fulfilment (long term) and money are tracked along every path as a difference from now. Each event nudges them up or down by a judged amount, or by a published or stated figure for money; the lines show the average of the thousand lives and the band shows where most of them fall.</p></>
          )}
          <Freshness api={api} personId={personId} />
          <h2>Limits</h2>
          <ul>{card.limits.map((l) => <li key={l}>{l}</li>)}</ul>
        </div>
      )}
    </Sheet>
  )
}

const dayLabel = (days?: number) => (days === undefined ? '' : days === 0 ? 'the same day' : days === 1 ? 'a day' : days < 60 ? `${days} days` : `${Math.round(days / 30)} months`)

function when(at?: string): string {
  if (!at) return 'not yet'
  const mins = Math.round((Date.now() - new Date(at).getTime()) / 60000)
  if (!Number.isFinite(mins)) return 'not yet'
  if (mins < 2) return 'just now'
  if (mins < 60) return `${mins} minutes ago`
  if (mins < 48 * 60) return `${Math.round(mins / 60)} hours ago`
  return `${Math.round(mins / 1440)} days ago`
}

/**
 * A published figure is a fact about a moment, so the evidence behind a path has a shelf life.
 * A workflow on the Elastic cluster checks it daily and marks what has aged out; anything marked
 * is never reused from memory, it is researched again. This is that state, and a way to ask for
 * the check now rather than waiting for tomorrow.
 */
function Freshness({ api, personId }: { api: Api; personId: string }) {
  const [health, setHealth] = useState<EvidenceHealth | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    api.evidenceHealth(personId).then(setHealth).catch(() => setHealth({ available: false }))
  }, [api, personId])
  useEffect(load, [load])

  const check = async () => {
    setBusy(true)
    setError(null)
    try {
      const result = await api.auditEvidence(personId)
      setHealth(result.health)
      if (result.status !== 'completed') setError(result.error || `The audit ended as ${result.status}.`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The audit did not run.')
    } finally {
      setBusy(false)
    }
  }

  if (!health) return null
  if (!health.available) {
    return (
      <>
        <h2>How fresh the evidence is</h2>
        <p className="dim">{health.reason || 'Not available on this backend.'}</p>
      </>
    )
  }

  const { researched = 0, usable = 0, stale = 0, last_run: last } = health
  return (
    <>
      <h2>How fresh the evidence is</h2>
      <p>
        A published figure is a fact about a moment, so the research behind a path does not stay
        true forever. A scheduled job on the search cluster checks every figure once a day and
        marks anything older than {dayLabel(health.max_age_days)}. A marked figure is never reused
        from memory — the next path that needs it goes and looks it up again.
      </p>
      <dl className="freshness">
        <dt>Figures held</dt><dd>{researched}</dd>
        <dt>Still current</dt><dd>{usable}</dd>
        <dt>Aged out</dt><dd>{stale === 0 ? 'none' : stale}</dd>
        <dt>Last checked</dt><dd>{when(last?.at)}</dd>
      </dl>
      <p><button type="button" className="quiet" onClick={check} disabled={busy}>{busy ? 'checking' : 'check now'}</button></p>
      {error && <p className="page__error">{error}</p>}
    </>
  )
}
