import { useRef, useState, type DragEvent, type FormEvent } from 'react'
import type { Handles, IngestResult } from '../types'
import { Sheet } from './Sheet'

export interface OfferingDraft {
  text: string
  files: File[]
  handles: Handles
  display_name: string
  birth_year?: number
}

interface Props {
  busy: boolean
  firstRun: boolean
  result: IngestResult | 'silent' | null // 'silent': the request itself failed; say nothing alarming
  onSubmit: (v: OfferingDraft) => void
  onEnter: () => void
  onDemo: () => void
  onClose?: () => void
}

/** The one intake surface: words, files, handles. All optional, any combination. */
export function Offering({ busy, firstRun, result, onSubmit, onEnter, onDemo, onClose }: Props) {
  const [text, setText] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [handles, setHandles] = useState<Handles>({})
  const [name, setName] = useState('')
  const [born, setBorn] = useState('')
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
    onSubmit({ text: text.trim(), files, handles: clean, display_name: name.trim(), birth_year: born ? Number(born) : undefined })
  }

  if (result) {
    const outcome = result === 'silent' ? null : result
    return (
      <Sheet title="Received" eyebrow="the offering">
        <ul className="outcomes">
          {outcome?.inputs.map((i) => (
            <li key={i.name}><span className="caps">{i.name}</span>{i.outcome}</li>
          ))}
          {!outcome?.inputs.length && <li>Hereafter will begin with what it has.</li>}
        </ul>
        {outcome?.personality?.mbti && <p className="outcomes__type">You said you are <b>{outcome.personality.mbti}</b>. Hereafter will keep that in mind, lightly.</p>}
        <div className="sheet__actions">
          <button type="button" className="verb verb--primary" onClick={onEnter}>go on</button>
        </div>
      </Sheet>
    )
  }

  return (
    <Sheet title="Hereafter" lede="Give Hereafter anything about your life. Links, files, or just words. More in, clearer futures." onClose={firstRun ? undefined : onClose}>
      <form onSubmit={submit} className="offering">
        <label className="field">
          <span className="caps">words</span>
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={4} placeholder="Where you have lived, what you are turning over, a pasted resume, a personality result, a link or two." />
        </label>

        <div className={`dropzone ${over ? 'dropzone--over' : ''}`} onDragOver={(e) => (e.preventDefault(), setOver(true))} onDragLeave={() => setOver(false)} onDrop={drop} onClick={() => input.current?.click()} role="button" tabIndex={0}>
          <span className="caps">lay files here</span>
          <span className="dim">{files.length ? files.map((f) => f.name).join(', ') : 'chat exports, a resume, anything else'}</span>
          <input ref={input} type="file" multiple hidden onChange={(e) => setFiles((f) => [...f, ...Array.from(e.target.files ?? [])])} />
        </div>

        <div className="field-row">
          {(['github', 'linkedin', 'site', 'instagram'] as const).map((k) => (
            <label key={k} className="field">
              <span className="caps">{k === 'site' ? 'personal site' : k}</span>
              <input value={handles[k] ?? ''} onChange={(e) => setHandles((h) => ({ ...h, [k]: e.target.value }))} spellCheck={false} />
            </label>
          ))}
        </div>
        <p className="dim offering__consent">Only your own handles. Hereafter reads nothing about anyone else, never signs in anywhere, and keeps no raw chats or files.</p>

        <div className="field-row">
          <label className="field"><span className="caps">what to call you</span><input value={name} onChange={(e) => setName(e.target.value)} /></label>
          <label className="field"><span className="caps">year of birth</span><input value={born} onChange={(e) => setBorn(e.target.value.replace(/\D/g, '').slice(0, 4))} inputMode="numeric" /></label>
        </div>

        <div className="sheet__actions">
          <button type="submit" className="verb verb--primary" disabled={busy}>{busy ? 'reading' : 'offer it'}</button>
          {firstRun && <button type="button" className="quiet" onClick={onDemo}>walk a borrowed life instead</button>}
        </div>
      </form>
    </Sheet>
  )
}
