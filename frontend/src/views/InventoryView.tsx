import { useEffect, useState, type FormEvent } from 'react'
import type { Api } from '../api'
import { dateLabel, SOURCE_WORDS } from '../format'
import type { Inventory } from '../types'
import { Sheet } from './Sheet'

export function InventoryView({ api, personId, onOffer, onErased, onClose }: { api: Api; personId: string; onOffer: () => void; onErased: () => void; onClose: () => void }) {
  const [inv, setInv] = useState<Inventory | null>(null)
  const [typed, setTyped] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.inventory(personId).then(setInv).catch(() => setError('The inventory could not be read just now.'))
  }, [api, personId])

  const erase = async (e: FormEvent) => {
    e.preventDefault()
    if (typed !== 'erase') return
    setBusy(true)
    try {
      await api.erase(personId)
      onErased()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Nothing was erased.')
      setBusy(false)
    }
  }

  return (
    <Sheet title="What Hereafter knows" eyebrow="and where it came from" lede="Everything held about you, by source. Your name and birth year stay on this machine, encrypted; the life log is keyed by a random id." onClose={onClose}>
      <p className="log__tell"><button type="button" className="verb verb--primary" onClick={onOffer}>give Hereafter more</button></p>
      {!inv && !error && <p className="dim">counting</p>}
      {inv && (
        <div className="inventory">
          <section>
            <h2 className="caps">held, by source</h2>
            <ul className="inventory__sources">
              {inv.sources.map((s) => (
                <li key={s.source}>
                  <p><b>{SOURCE_WORDS[s.source] ?? s.source}</b> <span className="dim">· {words(s.count)} · newest {dateLabel(s.newest)}</span></p>
                  <ul>{s.examples.map((e) => <li key={e.id}>{e.text}</li>)}</ul>
                </li>
              ))}
            </ul>
            <p className="dim">Pages kept from your own links: {words(inv.cached_pages)}, encrypted on disk.</p>
            {inv.handles.length > 0 && <p className="dim">Handles you gave: {inv.handles.map((h) => (typeof h === 'string' ? h : `${h.source} (${h.handle})`)).join(', ')}.</p>}
          </section>
          <section>
            <h2 className="caps">sent to the language model, and only this</h2>
            <ul>{inv.sent_to_llm.map((x) => <li key={x}>{x}</li>)}</ul>
          </section>
          <section>
            <h2 className="caps">stored nowhere</h2>
            <ul>{inv.stored_nowhere.map((x) => <li key={x}>{x}</li>)}</ul>
          </section>
          <section className="inventory__erase">
            <h2 className="caps">erase</h2>
            <p>You cannot rewrite your past here, but you can burn the book. Erasing removes the log, every branch, the evidence gathered for you and every kept page, everywhere. It is the only deletion Hereafter has.</p>
            <form onSubmit={erase}>
              <label className="field">
                <span className="caps">write the word erase</span>
                <input value={typed} onChange={(e) => setTyped(e.target.value)} spellCheck={false} />
              </label>
              <button type="submit" className="verb verb--merge" disabled={typed !== 'erase' || busy}>{busy ? 'erasing' : 'erase everything'}</button>
            </form>
          </section>
        </div>
      )}
      {error && <p className="page__error">{error}</p>}
    </Sheet>
  )
}

/** Counts in words: the inventory is not the evidence drawer. */
function words(n: number): string {
  const small = ['none', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve']
  if (n < small.length) return `${small[n]} ${n === 1 ? 'entry' : 'entries'}`
  return n < 40 ? 'a few dozen entries' : n < 200 ? 'many dozens of entries' : 'hundreds of entries'
}
