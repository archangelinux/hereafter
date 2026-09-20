import { useRef, useState, type DragEvent, type FormEvent } from 'react'
import type { Handles, IngestResult } from '../types'

export interface OfferingDraft {
  text: string
  files: File[]
  handles: Handles
  display_name: string
  birth_year?: number
  income?: number
  net_worth?: number
  currency?: string
}

interface Props {
  busy: boolean
  firstRun: boolean
  result: IngestResult | 'silent' | null // 'silent': the request itself failed; say nothing alarming
  onSubmit: (v: OfferingDraft) => void
  onEnter: () => void
  onClose?: () => void
}

/** The one intake surface: words, files, handles. All optional, any combination. */
export function Offering({ busy, firstRun, result, onSubmit, onEnter, onClose }: Props) {
  const [text, setText] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [handles, setHandles] = useState<Handles>({})
  const [name, setName] = useState('')
  const [born, setBorn] = useState('')
  const [income, setIncome] = useState('')
  const [worth, setWorth] = useState('')
  const [currency, setCurrency] = useState('CAD')
  const [over, setOver] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  const drop = (e: DragEvent) => {
    e.preventDefault()
    setOver(false)
    setFiles((f) => [...f, ...Array.from(e.dataTransfer.files)])
  }
  const submit = (e: FormEvent) => {
    e.preventDefault()
    const clean = Object.fromEntries(Object.entries(handles).filter(([, v]) => v?.trim())) as Handles
    const n = (v: string) => (v.replace(/[^\d.]/g, '') ? Number(v.replace(/[^\d.]/g, '')) : undefined)
    onSubmit({ text: text.trim(), files, handles: clean, display_name: name.trim(), birth_year: born ? Number(born) : undefined, income: n(income), net_worth: n(worth), currency: n(income) !== undefined || n(worth) !== undefined ? currency : undefined })
  }

  if (result) {
    const outcome = result === 'silent' ? null : result
    return (
      <div className="setup-ground">
        <section className="setup" role="dialog" aria-label="Added">
          <h1 className="setup__title">Added</h1>
          <ul className="setup__results">
            {outcome?.inputs.map((i) => (
              <li key={i.name}><b>{i.name}</b><span>{i.outcome}</span></li>
            ))}
            {!outcome?.inputs.length && <li><span>Nothing to read yet. You can add more any time.</span></li>}
          </ul>
          {outcome?.personality?.mbti && <p className="setup__note">Personality type noted: {outcome.personality.mbti}.</p>}
          <div className="setup__actions">
            <button type="button" className="setup__primary" onClick={onEnter}>Continue</button>
          </div>
        </section>
      </div>
    )
  }

  return (
    <div className="setup-ground">
      <form onSubmit={submit} className="setup" aria-label="Tell Hereafter about yourself">
        <header className="setup__head">
          <p className="setup__brand">Hereafter</p>
          {!firstRun && onClose && <button type="button" className="setup__link" onClick={onClose}>Close</button>}
        </header>
        <h1 className="setup__title">Tell Hereafter about yourself</h1>
        <p className="setup__sub">All optional. The more it knows, the more specific your paths get.</p>

        <label className="setup__field">
          <span>About you</span>
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3}
            placeholder="Write or paste anything: where you are in life, what is on your mind. Links work too." />
        </label>

        <div className="setup__field">
          <span>Files</span>
          <div className={`setup__drop ${over ? 'setup__drop--over' : ''}`} onDragOver={(e) => (e.preventDefault(), setOver(true))}
            onDragLeave={() => setOver(false)} onDrop={drop} onClick={() => input.current?.click()} role="button" tabIndex={0}
            onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && input.current?.click()}>
            {files.length
              ? <span className="setup__files">{files.map((f) => f.name).join(', ')}</span>
              : <><b>Drop files or click to choose</b><span>Chat exports (WhatsApp, Claude, ChatGPT), a resume, notes</span></>}
            <input ref={input} type="file" multiple hidden onChange={(e) => setFiles((f) => [...f, ...Array.from(e.target.files ?? [])])} />
          </div>
        </div>

        <div className="setup__grid">
          {([['github', 'GitHub', 'username'], ['linkedin', 'LinkedIn', 'username'], ['site', 'Website', 'yourname.com'], ['instagram', 'Instagram', 'username']] as const).map(([k, label, hint]) => (
            <label key={k} className="setup__field">
              <span>{label}</span>
              <input value={handles[k] ?? ''} placeholder={hint} onChange={(e) => setHandles((h) => ({ ...h, [k]: e.target.value }))} spellCheck={false} autoCapitalize="off" />
            </label>
          ))}
          <label className="setup__field">
            <span>Name</span>
            <input value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label className="setup__field">
            <span>Birth year</span>
            <input value={born} placeholder="2003" onChange={(e) => setBorn(e.target.value.replace(/\D/g, '').slice(0, 4))} inputMode="numeric" />
          </label>
        </div>

        <div className="setup__grid setup__grid--money">
          <label className="setup__field"><span>Income a year (optional)</span><input value={income} onChange={(e) => setIncome(e.target.value)} inputMode="numeric" /></label>
          <label className="setup__field"><span>Savings or net worth (optional)</span><input value={worth} onChange={(e) => setWorth(e.target.value)} inputMode="numeric" /></label>
          <label className="setup__field"><span>Currency</span><input value={currency} onChange={(e) => setCurrency(e.target.value.toUpperCase().slice(0, 3))} /></label>
        </div>

        <p className="setup__note">Only your own accounts. Files are read once and never stored.</p>

        <div className="setup__actions">
          <button type="submit" className="setup__primary" disabled={busy}>{busy ? 'Reading…' : 'Continue'}</button>
        </div>
      </form>
    </div>
  )
}
