import { isUndated, preciseDate, SOURCE_WORDS, sureness } from '../format'
import type { LifeEvent, Reconciliation } from '../types'
import { Sheet } from './Sheet'

/** Main, read as history. Read-only: nothing here responds, because nothing here can change. */
export function LogView({ events, reconciliation, onTell, onClose }: { events: LifeEvent[]; reconciliation: Reconciliation[]; onTell: () => void; onClose: () => void }) {
  const log = [...events].filter((e) => !isUndated(e)).sort((a, b) => b.date.localeCompare(a.date))
  const undated = events.filter(isUndated)
  return (
    <Sheet title="The log" eyebrow="main" lede="What happened. Added to, never edited." onClose={onClose}>
      <p className="log__tell"><button type="button" className="verb verb--primary" onClick={onTell}>tell Hereafter something</button></p>
      <ol className="log">
        {log.map((e) => (
          <li key={e.id} className={`log__entry log__entry--${e.event_type}`}>
            <p className="caps log__date">{preciseDate(e)}</p>
            <p className="log__message">{e.text}</p>
            <p className="log__meta">
              <span className="caps">{e.domain}</span> · {e.event_type === 'decision' ? 'a merge' : e.event_type === 'goal' ? 'picked from a road not taken' : (SOURCE_WORDS[e.source] ?? e.source)} · {sureness(e.confidence)}{e.origin ? ` · from ${e.origin}` : ''}
            </p>
          </li>
        ))}
      </ol>
      {undated.length > 0 && (
        <section className="log__rulings">
          <h2 className="caps">Undated</h2>
          <ul>{undated.map((e) => <li key={e.id}>{e.text} <span className="dim">· {SOURCE_WORDS[e.source] ?? e.source}{e.origin ? ` · from ${e.origin}` : ''}</span></li>)}</ul>
        </section>
      )}
      {reconciliation.length > 0 && (
        <section className="log__rulings">
          <h2 className="caps">where your sources disagreed</h2>
          <ul>
            {reconciliation.map((r) => (
              <li key={r.slot}>
                <b>{r.slot.replace(/_/g, ' ')}</b>: kept “{r.chosen}” over {r.over.map((o) => `“${o}”`).join(', ')}. <span className="dim">{r.reason}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </Sheet>
  )
}
