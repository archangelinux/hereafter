import { useEffect, type ReactNode } from 'react'
import { Wave } from '../page/marks'

/** A full sheet of paper laid over the line and the page. Unfolds; closes on Escape. */
export function Sheet({ title, eyebrow, lede, onClose, wide, solemn, children }: { title: string; eyebrow?: string; lede?: string; onClose?: () => void; wide?: boolean; solemn?: boolean; children: ReactNode }) {
  useEffect(() => {
    if (!onClose) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className={`sheet-ground ${solemn ? 'sheet-ground--solemn' : ''}`}>
      <section className={`sheet ${wide ? 'sheet--wide' : ''}`} role="dialog" aria-label={title}>
        <header className="sheet__head">
          <div>
            {eyebrow && <p className="caps">{eyebrow}</p>}
            <h1>{title}</h1>
          </div>
          {onClose && <button type="button" className="quiet" onClick={onClose}>close</button>}
        </header>
        <Wave className="sheet__wave" width={220} />
        {lede && <p className="sheet__lede">{lede}</p>}
        {children}
      </section>
    </div>
  )
}
