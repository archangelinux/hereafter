import { useState, type FormEvent } from 'react'
import type { BranchView } from '../types'
import { Sheet } from './Sheet'

/** The opposite of undo: slow, explicit, and it cannot be taken back. */
export function MergeCeremony({ view, siblings, busy, error, onConfirm, onClose }: { view: BranchView; siblings: BranchView[]; busy: boolean; error: string | null; onConfirm: (confirm: string) => void; onClose: () => void }) {
  const [typed, setTyped] = useState('')
  const label = view.branch.label
  const others = siblings.filter((s) => s.branch.id !== view.branch.id && s.branch.status === 'open')
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (typed === label) onConfirm(typed)
  }
  return (
    <Sheet title="Merge into main" eyebrow="this is the one thing here that cannot be undone" onClose={onClose} solemn>
      <div className="merge">
        <p className="merge__lead">
          Until now everything has been a what-if. A commit on a branch can be undone, because it was never real. A merge is different: it tells Hereafter
          that <em>{label}</em> is what you actually chose.
        </p>
        <ul className="merge__terms">
          <li>It is written onto main, today, as something that happened. Main is never edited and nothing can take it off again.</li>
          <li>Main continues along this branch. What the simulation drew ahead stays a projection, redrawn as your real life arrives.</li>
          {others.length > 0 && (
            <li>
              {others.map((o) => `“${o.branch.label}”`).join(' and ')} {others.length === 1 ? 'becomes a road' : 'become roads'} not taken: closed, kept, still readable. You may pick one moment from each to carry with you.
            </li>
          )}
        </ul>
        <form onSubmit={submit}>
          <label className="field">
            <span className="caps">to merge, write the name of the branch exactly</span>
            <input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder={label} autoFocus spellCheck={false} />
          </label>
          {error && <p className="page__error">{error}</p>}
          <div className="sheet__actions">
            <button type="submit" className="verb verb--merge" disabled={typed !== label || busy}>{busy ? 'writing it onto main' : 'merge. I chose this.'}</button>
            <button type="button" className="quiet" onClick={onClose}>not yet</button>
          </div>
        </form>
      </div>
    </Sheet>
  )
}
