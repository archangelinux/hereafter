export type Mode = 'island' | 'line'

/** Like a map's layer switch: a small picture of the other view of the same place. */
export function ModeSwitch({ mode, onToggle }: { mode: Mode; onToggle: () => void }) {
  const other: Mode = mode === 'island' ? 'line' : 'island'
  return (
    <button type="button" className="mode" onClick={onToggle} title={`switch to ${other} view (V)`}>
      <svg viewBox="0 0 64 44" width={64} height={44} aria-hidden="true">
        {other === 'line' ? (
          <g fill="none" strokeLinecap="round">
            <path d="M22 42 V22" stroke="#5C5347" strokeWidth="3.2" />
            <path d="M22 22 C22 12 34 14 36 3" stroke="#C4705A" strokeWidth="2.2" />
            <path d="M22 22 C22 14 46 18 50 6" stroke="#6E9C86" strokeWidth="2.2" strokeDasharray="5 4" />
            <path d="M22 22 C22 16 10 16 8 8" stroke="#C2923F" strokeWidth="1.8" strokeDasharray="1 5" />
            <path d="M17 30 h10 M17 36 h10" stroke="#D9A588" strokeWidth="2" />
          </g>
        ) : (
          <g>
            <ellipse cx="20" cy="30" rx="15" ry="6" fill="#E8D5C0" />
            <path d="M5 30 Q20 46 35 30 Z" fill="#D9A588" />
            <ellipse cx="46" cy="16" rx="11" ry="4.5" fill="#F5EFE4" />
            <path d="M35 16 Q46 28 57 16 Z" fill="#DDD1C2" />
            <path d="M22 28 C30 24 34 20 44 16" fill="none" stroke="#C4705A" strokeWidth="2" strokeLinecap="round" />
            <circle cx="50" cy="8" r="4" fill="#FFFDF8" />
          </g>
        )}
      </svg>
      <span className="caps">{other} view</span>
      <kbd>V</kbd>
    </button>
  )
}
