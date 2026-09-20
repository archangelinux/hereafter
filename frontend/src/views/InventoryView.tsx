import { useEffect, useState, type FormEvent } from 'react'
import type { Api } from '../api'
import { dateLabel, SOURCE_WORDS } from '../format'
import type { Inventory } from '../types'
import { Sheet } from './Sheet'

export function InventoryView({ api, personId, onOffer, onErased, onChanged, onClose }: { api: Api; personId: string; onOffer: () => void; onErased: () => void; onChanged: () => void; onClose: () => void }) {
  const [inv, setInv] = useState<Inventory | null>(null)
  const [typed, setTyped] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [forgetting, setForgetting] = useState<string | null>(null)

  const forget = async (origin: string) => {
    setBusy(true)
    setError(null)
    try {
      await api.forget(personId, origin)
      setForgetting(null)
      setInv(await api.inventory(personId))
      onChanged()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Nothing was forgotten.')
    } finally {
      setBusy(false)
    }
  }

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
    <Sheet title="What Hereafter knows" eyebrow="and where it came from" lede="Everything held about you, and where it came from." onClose={onClose}>
      <p className="log__tell"><button type="button" className="verb verb--primary" onClick={onOffer}>give Hereafter more</button></p>
      {!inv && !error && <p className="dim">counting</p>}
      {inv && (
        <div className="inventory">
          {!!inv.offerings?.length && (
            <section className="offered">
              <h2 className="caps">what you have offered</h2>
              <ul>
                {inv.offerings.map((o) => (
                  <li key={o.origin}>
                    <span><b>{o.origin}</b> <span className="offered__how" title={`${o.count} entries on main`}>· gave Hereafter {o.count <= 2 ? 'a little' : o.count <= 8 ? 'some' : 'a lot'} · last {dateLabel(o.newest)}</span></span>
                    <button type="button" className="quiet" onClick={() => setForgetting(forgetting === o.origin ? null : o.origin)}>forget this</button>
                    {forgetting === o.origin && (
                      <p className="offered__confirm">
                        <span>Everything Hereafter learned from this goes. You can offer it again later.</span>
                        <button type="button" className="verb" disabled={busy} onClick={() => void forget(o.origin)}>{busy ? 'forgetting' : 'forget it'}</button>
                        <button type="button" className="quiet" onClick={() => setForgetting(null)}>keep it</button>
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}
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
            <p>Removes everything about you, everywhere. It cannot be undone.</p>
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

const words = (n: number) => `${n}`
