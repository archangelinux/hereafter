import { useEffect, useState } from 'react'
import type { Api } from '../api'
import { aspectLabel } from '../derive'
import { dayLabel, inEveryTen } from '../format'
import type { Branch, BranchYear, Evidence } from '../types'

interface Props {
  api: Api
  branch: Branch | undefined
  ids: string[]
  step: BranchYear | null
  /** the codex: everything gathered so far, rather than one claim */
  collected?: boolean
  onClose: () => void
}

const KIND: Record<Evidence['kind'], string> = { researched: 'researched, read from the live web', statistic: 'a published statistic', personal: 'from your own log' }

/** The one place in Hereafter where figures appear. */
export function EvidenceDrawer({ api, branch, ids, step, collected, onClose }: Props) {
  const [items, setItems] = useState<Evidence[] | null>(null)

  useEffect(() => {
    let live = true
    setItems(null)
    const ask = ids.length ? api.evidence({ ids }) : Promise.resolve([])
    ask.then((e) => live && setItems(e)).catch(() => live && setItems([]))
    return () => {
      live = false
    }
  }, [api, ids])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <aside className="drawer" aria-label="evidence">
      <header>
        <p className="caps">{collected ? 'the codex' : 'the evidence'}</p>
        <button type="button" className="quiet" onClick={onClose}>close</button>
      </header>
      {api.offline && <p className="drawer__sample">Hereafter is offline. Researched items here are samples; the Statistics Canada figures are real.</p>}

      {items === null && <p className="dim">looking it up</p>}
      {collected && <p className="dim drawer__lede">What you have come across so far, with its sources. Figures appear here and nowhere else.</p>}
      {items?.length === 0 && (ids.length > 0 || collected) && <p className="dim">{collected ? 'Nothing gathered yet. Evidence collects here as you walk.' : 'Nothing is on file for this yet.'}</p>}
      {items?.map((e) => (
        <article key={e.id} className={`evidence evidence--${e.kind}`}>
          <p className="caps evidence__kind">{KIND[e.kind]}</p>
          <p className="evidence__claim">{e.claim}</p>
          {e.value && (
            <p className="evidence__figure">
              <b>{e.value}</b> {e.unit}
            </p>
          )}
          {e.snippet && <blockquote>“{e.snippet}”</blockquote>}
          <p className="evidence__source">
            {e.source_url ? <a href={e.source_url} target="_blank" rel="noreferrer">{e.source_title}</a> : e.source_title}
            <span className="dim"> · read {dayLabel(e.retrieved_at)}</span>
          </p>
          {e.used_for && <p className="evidence__used"><span className="caps">what it changed</span> {e.used_for}</p>}
        </article>
      ))}

      {step && (
        <section className="spread">
          <p className="caps">how the thousand lives spread · {step.label}</p>
          <p className="dim spread__lede">The page follows the most typical of a thousand simulated lives. This is how many of the others agree with it at this point.</p>
          <ul>
            {Object.entries(step.outlook).map(([aspect, o]) => (
              <li key={aspect}>
                <span className="spread__aspect">{aspectLabel(aspect, branch ? [branch] : [])}</span>
                <span className="spread__value">{o.value}</span>
                <span className="spread__share">{inEveryTen(o.share)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </aside>
  )
}
