import { Fragment, useState } from 'react'
import { dayLabel } from '../format'
import { theme } from '../theme'
import type { BranchView, Scenario } from '../types'

/** Everything still being turned over, soonest deadline first. Doubles as navigation. */
interface ExamplesEntry {
  open: boolean
  onToggle: () => void
  onDismiss: () => void
}

export function QuestLog({ scenarios, views, activeScenarioId, onOpen, onNew, examples }: { scenarios: Scenario[]; views: BranchView[]; activeScenarioId: string | null; onOpen: (branchId: string) => void; onNew: () => void; examples?: ExamplesEntry | null }) {
  const [open, setOpen] = useState(true)
  const rows = scenarios.map((s) => {
    const branches = s.branch_ids.flatMap((id) => views.filter((v) => v.branch.id === id))
    const live = branches.filter((b) => b.branch.status === 'open')
    const deadlines = [...s.options.map((o) => o.deadline), ...live.map((b) => b.branch.precondition?.match(/\d{4}-\d{2}-\d{2}/)?.[0] ?? null)].filter((d): d is string => !!d).sort()
    const decided = branches.find((b) => b.branch.status === 'merged')
    const state = decided ? `decided: ${decided.branch.label}` : live.length === 0 ? 'stale' : deadlines[0] ? `until ${dayLabel(deadlines[0])}` : 'open'
    const waiting = live.length > 0 && s.questions.some((q) => !q.answer)
    return { s, target: (decided ?? live[0] ?? branches[0])?.branch.id ?? null, live: live.length > 0, deadline: deadlines[0] ?? '9999', state, waiting, count: branches.length }
  })
  rows.sort((a, b) => Number(b.live) - Number(a.live) || a.deadline.localeCompare(b.deadline) || b.s.created_at.localeCompare(a.s.created_at))
  return (
    <nav className="quests" aria-label="decisions">
      <button type="button" className="caps quests__toggle" onClick={() => setOpen((v) => !v)} aria-expanded={open}>still turning over {open ? '−' : '+'}</button>
      {open && (
        <ul>
          {[rows.filter((r) => !r.s.example), rows.filter((r) => r.s.example)].map((group, g) => (
            <Fragment key={g}>
              {g === 1 && group.length > 0 && <li className="caps quests__heading">examples — a borrowed life</li>}
          {group.map(({ s, target, live, state, waiting, count }) => (
                <li key={s.id} className={`${live ? '' : 'quests--closed'} ${s.id === activeScenarioId ? 'quests--here' : ''}`}>
                  <button type="button" disabled={!target} onClick={() => target && onOpen(target)}>
                    <span className="quests__marks" aria-hidden="true">
                      {Array.from({ length: Math.min(count, 4) }, (_, i) => <i key={i} style={{ background: live ? theme.branch[i % theme.branch.length] : theme.color.ruin }} />)}
                    </span>
                    <span className="quests__what">{s.situation}</span>
                    <span className="quests__state">{state}{waiting ? ' · a question waits' : ''}</span>
                  </button>
                </li>
              ))}
            </Fragment>
          ))}
          {examples && (
            <li className="quests__examples">
              <button type="button" className="quiet" onClick={examples.onToggle}>{examples.open ? 'put the examples away' : 'examples'}</button>
              <button type="button" className="quiet" onClick={examples.onDismiss} title="do not show this again">dismiss</button>
            </li>
          )}
          <li><button type="button" className="verb verb--primary quests__new" onClick={onNew}>what are you deciding?</button></li>
        </ul>
      )}
    </nav>
  )
}
