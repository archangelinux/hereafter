import { useState, type FormEvent } from 'react'
import { Sheet } from './Sheet'

export function Tell({ busy, error, onSubmit, onClose }: { busy: boolean; error: string | null; onSubmit: (text: string) => void; onClose: () => void }) {
  const [text, setText] = useState('')
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (text.trim()) onSubmit(text.trim())
  }
  return (
    <Sheet title="Tell Hereafter something" eyebrow="onto main" lede="Added to main, as of today." onClose={onClose}>
      <form onSubmit={submit}>
        <label className="field">
          <span className="caps">what happened</span>
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} autoFocus placeholder="" />
        </label>
        {error && <p className="page__error">{error}</p>}
        <div className="sheet__actions">
          <button type="submit" className="verb verb--primary" disabled={busy || !text.trim()}>{busy ? 'adding it' : 'add to main'}</button>
        </div>
      </form>
    </Sheet>
  )
}
