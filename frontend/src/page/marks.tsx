// Small drawn marks, all SVG, never emoji. The same three treatments are used on the line.

import type { Basis } from '../types'

/** sourced: a full stroke. estimated: an open stroke. background: a faint stroke. commit: a knot. */
export function BasisMark({ basis }: { basis: Basis | 'commit' }) {
  return (
    <svg className={`basis basis--${basis}`} viewBox="0 0 18 14" width={18} height={14} aria-hidden="true">
      {basis === 'commit' ? (
        <path d="M9 1 L15 7 L9 13 L3 7 Z" />
      ) : basis === 'estimated' ? (
        <path d="M1 7 H6 M12 7 H17" />
      ) : (
        <path d="M1 7 H17" />
      )}
    </svg>
  )
}

export function Wave({ className = '', width = 220 }: { className?: string; width?: number }) {
  const d = `M2 7 C ${width * 0.12} 1, ${width * 0.22} 13, ${width * 0.36} 7 S ${width * 0.6} 1, ${width * 0.72} 7 S ${width * 0.9} 11, ${width - 2} 6`
  return (
    <svg className={`wave ${className}`} viewBox={`0 0 ${width} 14`} width={width} height={14} aria-hidden="true" preserveAspectRatio="none">
      <path d={d} fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" />
    </svg>
  )
}
