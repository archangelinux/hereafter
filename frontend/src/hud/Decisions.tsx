import { useEffect, useRef, useState } from 'react'
import { scaleOf } from '../derive'
import { dayLabel } from '../format'
import { theme } from '../theme'
import { TinyMarks } from './MeasuresBlock'
import type { BranchView, Scenario, TicketPatch } from '../types'

interface ExamplesEntry {
  open: boolean
  onToggle: () => void
  onDismiss: () => void
}

interface Props {
  scenarios: Scenario[]
  views: BranchView[]
  activeId: string | null
  focusId: string | null
  onFocus: (scenarioId: string) => void
  onOpen: (branchId: string) => void
  onNew: () => void
  onEdit: (scenario: Scenario, patch: TicketPatch) => void
  examples?: ExamplesEntry | null
}

const PATH_WORD: Record<string, string> = { merged: 'chosen', faded: 'not taken', stale: 'closed', expired: 'closed' }

/** The decisions, as a plain list: a row per decision, its paths indented beneath, the selected one filled. */
export function Decisions({ scenarios, views, activeId, focusId, onFocus, onOpen, onNew, onEdit, examples }: Props) {
  const [editing, setEditing] = useState<string | null>(null)
  const list = useRef<HTMLUListElement>(null)
  // the path being lived is always in view
  useEffect(() => {
    list.current?.querySelector('.h-path.is-on')?.scrollIntoView({ block: 'nearest' })
  }, [activeId, focusId])
  const rows = scenarios.map((s) => {
    const branches = s.branch_ids.flatMap((id) => views.filter((v) => v.branch.id === id))
    const live = branches.filter((b) => b.branch.status === 'open')
    const deadline = [...s.options.map((o) => o.deadline), ...live.map((b) => b.branch.precondition?.match(/\d{4}-\d{2}-\d{2}/)?.[0] ?? null)].filter((d): d is string => !!d).sort()[0] ?? null
    const decided = branches.some((b) => b.branch.status === 'merged')
    const forming = branches.length === 0 || branches.some((b) => b.branch.forming || b.years.length === 0)
    const state = decided ? 'decided' : forming ? 'forming' : live.length === 0 ? 'closed' : 'open'
    return { s, branches, state, deadline, live: live.length > 0 }
  })
  rows.sort((a, b) => Number(b.live) - Number(a.live) || (a.deadline ?? '9999').localeCompare(b.deadline ?? '9999') || b.s.created_at.localeCompare(a.s.created_at))

  return (
    <nav className="h-panel h-decisions" aria-label="decisions">
      <header className="h-panel__head">
        <h2>{rows.length > 0 && rows.every((r) => r.s.example) ? 'Examples' : 'Decisions'}</h2>
        <button type="button" className="h-link" onClick={onNew} title="Add a decision (N)">+ New</button>
      </header>
      {rows.length === 0 && <p className="h-muted">None yet.</p>}
      <ul className="h-decisions__list" ref={list}>
        {rows.map(({ s, branches, state, deadline }) => {
          const edit = editing === s.id && state === 'open'
          const focused = s.id === focusId
          const scale = scaleOf(s)
          return (
            <li key={s.id} className={`h-decision ${focused ? 'is-focused' : ''}`}>
              <div className="h-decision__row">
                {edit ? (
                  <input className="h-input" defaultValue={s.situation} aria-label="Rename this decision" onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()} onBlur={(e) => e.target.value.trim() && e.target.value.trim() !== s.situation && onEdit(s, { situation: e.target.value.trim() })} />
                ) : (
                  <button type="button" className="h-decision__title" title={s.situation} onClick={() => onFocus(s.id)} aria-expanded={focused}>{s.situation}</button>
                )}
                {state === 'open' && focused && <button type="button" className="h-link h-decision__edit" onClick={() => setEditing(edit ? null : s.id)}>{edit ? 'Done' : 'Edit'}</button>}
              </div>
              <p className="h-decision__meta">
                {state === 'open' && !s.example ? (
                  <button type="button" className="h-tag" title="Wrong? Click to change" onClick={() => onEdit(s, { scale: scale === 'big' ? 'small' : 'big' })}>{scale === 'big' ? 'life' : 'day to day'}</button>
                ) : (
                  <span className="h-tag">{scale === 'big' ? 'life' : 'day to day'}</span>
                )}
                <span>{s.example ? 'example · ' : ''}{state}{s.questions.some((q) => !q.answer) && state === 'open' ? ' · has a question' : ''}</span>
                {edit ? <label>by <input className="h-input h-input--date" type="date" defaultValue={deadline ?? ''} onChange={(e) => onEdit(s, { decide_by: e.target.value || null })} /></label> : deadline && <span>by {dayLabel(deadline)}</span>}
              </p>
              {focused && <ul className="h-paths">
                {branches.map((b, i) => {
                  const colour = b.branch.status === 'open' ? theme.branch[i % theme.branch.length] : theme.color.ruin
                  return (
                    <li key={b.branch.id}>
                      {edit && b.branch.option_id ? (
                        <input className="h-input" defaultValue={b.branch.label} aria-label="Rename this path" onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()} onBlur={(e) => e.target.value.trim() && e.target.value.trim() !== b.branch.label && onEdit(s, { rename: { option_id: b.branch.option_id!, title: e.target.value.trim() } })} />
                      ) : (
                        <button type="button" className={`h-path ${b.branch.id === activeId ? 'is-on' : ''}`} onClick={() => onOpen(b.branch.id)} title="Select this path and live it">
                          <i style={{ background: colour }} />
                          <span>{b.branch.label}</span>
                          {b.branch.measures && <TinyMarks measures={b.branch.measures} />}
                          {PATH_WORD[b.branch.status] && <em>{PATH_WORD[b.branch.status]}</em>}
                        </button>
                      )}
                    </li>
                  )
                })}
                {edit && branches.length < 4 && (
                  <li><input className="h-input" placeholder="Add a path" aria-label="Add a path" onKeyDown={(e) => { if (e.key === 'Enter' && e.currentTarget.value.trim()) { onEdit(s, { add_option: e.currentTarget.value.trim() }); e.currentTarget.value = '' } }} /></li>
                )}
              </ul>}
            </li>
          )
        })}
      </ul>
      {examples && (
        <p className="h-decisions__foot">
          <button type="button" className="h-link" onClick={examples.onToggle}>{examples.open ? 'Hide examples' : 'Show examples'}</button>
          <button type="button" className="h-link" onClick={examples.onDismiss}>Dismiss</button>
        </p>
      )}
    </nav>
  )
}
