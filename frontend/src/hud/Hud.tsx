import { theme } from '../theme'
import type { BranchView, LifeEvent } from '../types'

/** Satchel: the moments picked from roads not taken, carried on main. */
export function Satchel({ goals, views, onClose }: { goals: LifeEvent[]; views: BranchView[]; onClose: () => void }) {
  return (
    <aside className="hud-card satchel">
      <header><b>Picked moments</b><button type="button" className="h-link" onClick={onClose}>Close</button></header>
      {goals.length === 0 && <p className="dim">Empty.</p>}
      <ul>
        {goals.map((g) => {
          const from = views.find((v) => v.branch.id === g.payload.from_branch)
          return (
            <li key={g.id}>
              <svg viewBox="0 0 12 18" width={10} height={16} aria-hidden="true"><path d="M6 1 C11 5 11 13 6 17 C1 13 1 5 6 1 Z" fill={theme.color.gold} stroke={theme.color.goldDeep} /></svg>
              <div>
                <p>{g.text}</p>
                {from && <p className="satchel__from">picked from “{from.branch.label}”</p>}
              </div>
            </li>
          )
        })}
      </ul>
    </aside>
  )
}
