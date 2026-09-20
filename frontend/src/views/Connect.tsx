import { Brand } from './Brand'
import { PLATFORMS, type Platform } from './platforms'

interface Props {
  selected: Platform[]
  /** flip one account on or off (the parent updates from its latest state, so quick clicks never overwrite each other) */
  onToggle: (key: Platform) => void
}

/**
 * Accounts as icons. A click selects one, another click deselects it. Selecting only records the choice
 * (OfferingDraft.sources): nothing is read from the account yet. Reading them, from the person's own browser
 * through Browserbase, is wired in where the draft is sent (see `offer` in App.tsx).
 */
export function Connect({ selected, onToggle }: Props) {

  return (
    <div className="setup__field">
      <span id="connect-label">Connect your accounts</span>
      <div className="connect" role="group" aria-labelledby="connect-label">
        <div className="connect__row">
          {PLATFORMS.map((p) => {
            const on = selected.includes(p.key)
            return (
              <button
                key={p.key}
                type="button"
                className={`connect__icon ${on ? 'is-on' : ''}`}
                aria-pressed={on}
                aria-label={p.label}
                title={on ? `${p.label} selected` : `Select ${p.label}`}
                onClick={() => onToggle(p.key)}
              >
                <Brand kind={p.key} />
                {on && (
                  <span className="connect__tick" aria-hidden="true">
                    <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><path d="M2.6 6.4l2.3 2.2 4.5-4.8" /></svg>
                  </span>
                )}
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}
