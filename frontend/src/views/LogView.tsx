import { dayLabel, SOURCE_WORDS, sureness } from '../format'
import type { LifeEvent, Reconciliation } from '../types'
import { Sheet } from './Sheet'

/** Main, read as history. Read-only: nothing here responds, because nothing here can change. */
export function LogView({ events, reconciliation, onTell, onClose }: { events: LifeEvent[]; reconciliation: Reconciliation[]; onTell: () => void; onClose: () => void }) {
  const log = [...events].sort((a, b) => b.date.localeCompare(a.date))
  return (
    <Sheet title="The log" eyebrow="main" lede="What actually happened, newest first. Entries are only ever added. None can be edited, and none removed, short of erasing everything." onClose={onClose}>
      <p className="log__tell"><button type="button" className="verb verb--primary" onClick={onTell}>tell Hereafter something</button></p>
      <ol className="log">
        {log.map((e) => (
          <li key={e.id} className={`log__entry log__entry--${e.event_type}`}>
            <p className="caps log__date">{dayLabel(e.date)}</p>
            <p className="log__message">{e.text}</p>
            <p className="log__meta">
              <span className="caps">{e.domain}</span> · {e.event_type === 'decision' ? 'a merge' : e.event_type === 'goal' ? 'picked from a road not taken' : (SOURCE_WORDS[e.source] ?? e.source)} · {sureness(e.confidence)}
            </p>
          </li>
        ))}
      </ol>
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
