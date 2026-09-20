import { useRef, useState, type DragEvent, type FormEvent } from 'react'
import type { IngestResult } from '../types'
import { Connect } from './Connect'
import type { Platform } from './platforms'

export interface OfferingDraft {
  text: string
  files: File[]
  /** the accounts chosen to learn from; nothing is read from them yet */
  sources: Platform[]
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
  const [sources, setSources] = useState<Platform[]>([])
  const [over, setOver] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  const drop = (e: DragEvent) => {
    e.preventDefault()
    setOver(false)
    setFiles((f) => [...f, ...Array.from(e.dataTransfer.files)])
  }
  const submit = (e: FormEvent) => {
    e.preventDefault()
    onSubmit({ text: text.trim(), files, sources })
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
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={5}
            placeholder="Write or paste anything: who you are, where you are in life, what is on your mind. Links work too." />
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

        <Connect selected={sources} onToggle={(key) => setSources((all) => (all.includes(key) ? all.filter((k) => k !== key) : [...all, key]))} />

        <div className="setup__actions">
          <button type="submit" className="setup__primary" disabled={busy}>{busy ? 'Reading…' : 'Continue'}</button>
        </div>
      </form>
    </div>
  )
}
