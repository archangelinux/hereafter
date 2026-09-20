import { useEffect, useState } from 'react'
import { Brand } from './Brand'
import { PLATFORMS, type Platform } from './platforms'

const STEP_MS = 1100 // one beat per account
const BUILD_MS = 1400 // then the profile being put together
/** How long the screen stays, so a fast answer never makes it flash: every account, the profile, and a breath. */
export const connectingMs = (accounts: number) => accounts * STEP_MS + BUILD_MS + 500

/**
 * The short wait between choosing accounts and the main page. It is timed, not tied to a real read: reading the
 * accounts (through Browserbase, from the person's own browser) is wired in where the draft is sent (`offer` in App.tsx),
 * and this screen should then follow that work instead of a clock.
 */
export function Connecting({ platforms }: { platforms: Platform[] }) {
  const chosen = PLATFORMS.filter((p) => platforms.includes(p.key))
  const [done, setDone] = useState(0)
  const [built, setBuilt] = useState(false)
  useEffect(() => {
    const timers = chosen.map((_, i) => window.setTimeout(() => setDone(i + 1), (i + 1) * STEP_MS))
    timers.push(window.setTimeout(() => setBuilt(true), chosen.length * STEP_MS + BUILD_MS))
    return () => timers.forEach(clearTimeout)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  const total = chosen.length + 1
  const finished = done + (built ? 1 : 0)

  const row = (key: string, mark: React.ReactNode, state: 'wait' | 'now' | 'done', text: string) => (
    <li key={key} className={`connecting__row is-${state}`}>
      <span className="connecting__mark">{mark}</span>
      <span className="connecting__text">{text}</span>
      <span className="connecting__state" aria-hidden="true">
        {state === 'done' ? <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><path d="M2.6 6.4l2.3 2.2 4.5-4.8" /></svg> : state === 'now' ? <i className="connecting__spin" /> : null}
      </span>
    </li>
  )

  return (
    <div className="setup-ground">
      <section className="setup connecting" role="status" aria-live="polite" aria-label="Connecting your accounts">
        <p className="setup__brand">Hereafter</p>
        <h1 className="setup__title">Connecting your accounts</h1>
        <p className="setup__sub">Just a moment.</p>
        <ul className="connecting__list">
          {chosen.map((p, i) => row(p.key, <Brand kind={p.key} />, done > i ? 'done' : done === i ? 'now' : 'wait', done > i ? `${p.label} connected` : done === i ? `Reading ${p.label}…` : p.label))}
          {row('profile', <span className="connecting__dot" />, built ? 'done' : done >= chosen.length ? 'now' : 'wait', built ? 'Profile ready' : 'Building your profile…')}
        </ul>
        <div className="connecting__bar" aria-hidden="true"><i style={{ width: `${(finished / total) * 100}%` }} /></div>
      </section>
    </div>
  )
}
