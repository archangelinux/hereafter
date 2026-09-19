import { useEffect, useRef, useState, type KeyboardEvent } from 'react'

interface Props {
  inside: string | null // branching: the path and date this decision forks from
  busy: boolean
  error: string | null
  onCreate: (decision: string, paths: string[]) => void
  onClose: () => void
}

/** A decision is written like a commit: its label, its paths, Enter. Nothing else. */
export function NewDecision({ inside, busy, error, onCreate, onClose }: Props) {
  const [decision, setDecision] = useState('')
  const [paths, setPaths] = useState(['', ''])
  const fields = useRef<(HTMLInputElement | null)[]>([])
  const focus = (i: number) => setTimeout(() => fields.current[i]?.focus(), 0)
  useEffect(() => {
    focus(0)
  }, [])

  const named = paths.map((p) => p.trim()).filter(Boolean)
  const ready = decision.trim().length > 0 && named.length >= 2 && !busy
  const submit = () => ready && onCreate(decision.trim(), named)

  const onKey = (i: number) => (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') return onClose()
    if (e.key === 'Enter') {
      e.preventDefault()
      if (i === paths.length && ready) return submit()
      return focus(Math.min(i + 1, paths.length))
    }
    if (e.key === 'Backspace' && i > 0 && paths[i - 1] === '' && paths.length > 2) {
      e.preventDefault()
      setPaths((all) => all.filter((_, n) => n !== i - 1))
      focus(i - 1)
    }
  }

  return (
    <form className="hud-card decide" onSubmit={(e) => (e.preventDefault(), submit())} aria-label="a new decision">
      <p className="caps decide__inside">{inside ? `Branch · on ${inside}` : 'New decision'}</p>
      <label>
        <span className="caps">decision</span>
        <input ref={(el) => void (fields.current[0] = el)} value={decision} onChange={(e) => setDecision(e.target.value)} onKeyDown={onKey(0)} maxLength={120} />
      </label>
      {paths.map((p, i) => (
        <label key={i}>
          <span className="caps">path</span>
          <input ref={(el) => void (fields.current[i + 1] = el)} value={p} onChange={(e) => setPaths((all) => all.map((x, n) => (n === i ? e.target.value : x)))} onKeyDown={onKey(i + 1)} maxLength={80} />
        </label>
      ))}
      <p className="decide__row caps">
        {paths.length < 4 ? <button type="button" onClick={() => (setPaths((all) => [...all, '']), focus(paths.length + 1))}>+ path</button> : <span />}
        {error && <span className="decide__error">{error}</span>}
        <button type="submit" disabled={!ready}>{busy ? 'branching' : 'branch'} <kbd>↵</kbd></button>
      </p>
    </form>
  )
}
