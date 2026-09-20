import { useEffect, useRef, useState } from 'react'
import { scaleOf } from '../derive'
import { dayLabel } from '../format'
import type { BranchView, Scenario, TicketPatch } from '../types'

interface ExamplesEntry {
  open: boolean
  onToggle: () => void
  onDismiss: () => void
}

interface Props {
  scenarios: Scenario[]
  views: BranchView[]
  focusId: string | null
  onFocus: (scenarioId: string) => void
  onNew: () => void
  onEdit: (scenario: Scenario, patch: TicketPatch) => void
  /** remove an open decision and its paths (asked for first, inline) */
  onDelete: (scenario: Scenario) => void
  examples?: ExamplesEntry | null
}

/** The decisions still to make, as a plain list: a row per decision, the one being considered marked. Decided ones live in the log; the paths live in the panel on the right. */
export function Decisions({ scenarios, views, focusId, onFocus, onNew, onEdit, onDelete, examples }: Props) {
  const [editing, setEditing] = useState<string | null>(null)
  const [confirming, setConfirming] = useState<string | null>(null)
  const list = useRef<HTMLUListElement>(null)
  // the decision being considered is always in view
  useEffect(() => {
    list.current?.querySelector('.h-decision.is-focused')?.scrollIntoView({ block: 'nearest' })
  }, [focusId])
  const all = scenarios.map((s) => {
    const branches = s.branch_ids.flatMap((id) => views.filter((v) => v.branch.id === id))
    const live = branches.filter((b) => b.branch.status === 'open')
    const deadline = [...s.options.map((o) => o.deadline), ...live.map((b) => b.branch.precondition?.match(/\d{4}-\d{2}-\d{2}/)?.[0] ?? null)].filter((d): d is string => !!d).sort()[0] ?? null
    const decided = branches.some((b) => b.branch.status === 'merged')
    const forming = branches.length === 0 || branches.some((b) => b.branch.forming || b.years.length === 0)
    const state = decided ? 'decided' : forming ? 'forming' : live.length === 0 ? 'closed' : 'open'
    return { s, branches, state, deadline, live: live.length > 0 }
  })
  // decided decisions are history: they are in the log, as the merge that made them
  const rows = all.filter((r) => r.state !== 'decided')
  rows.sort((a, b) => Number(b.live) - Number(a.live) || (a.deadline ?? '9999').localeCompare(b.deadline ?? '9999') || b.s.created_at.localeCompare(a.s.created_at))

  return (
    <nav className="h-panel h-decisions" aria-label="open decisions">
      <header className="h-panel__head">
        <h2>{rows.length > 0 && rows.every((r) => r.s.example) ? 'Examples' : 'Open decisions'}</h2>
        <button type="button" className="h-link" onClick={onNew} title="Add a decision (N)">+ New</button>
      </header>
      {rows.length === 0 && <p className="h-muted">{all.length > 0 ? 'None open. The ones you decided are in the log.' : 'None yet.'}</p>}
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
                  <button type="button" className="h-decision__title" title={focused ? s.situation : `${s.situation} — consider this one`} aria-current={focused || undefined} onClick={() => onFocus(s.id)}>{s.situation}</button>
                )}
                {state === 'open' && focused && <button type="button" className="h-link h-decision__edit" onClick={() => setEditing(edit ? null : s.id)}>{edit ? 'Done' : 'Edit'}</button>}
                {state === 'open' && !s.example && !edit && (
                  <button type="button" className="h-decision__trash" aria-label={`Delete “${s.situation}”`} aria-expanded={confirming === s.id} title="Delete this decision" onClick={() => setConfirming(confirming === s.id ? null : s.id)}>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
                      <path d="M4 7h16" /><path d="M9 7V4.5h6V7" /><path d="M6.2 7l.9 12a2 2 0 0 0 2 1.8h5.8a2 2 0 0 0 2-1.8l.9-12" /><path d="M10 11v6M14 11v6" />
                    </svg>
                  </button>
                )}
              </div>
              {confirming === s.id && (
                <div className="h-decision__confirm" role="alertdialog" aria-label="Delete this decision?" onKeyDown={(e) => e.key === 'Escape' && (e.stopPropagation(), setConfirming(null))}>
                  <span>
                    Delete this decision and its paths?
                    {scenarios.some((x) => x.assuming_branch_id && s.branch_ids.includes(x.assuming_branch_id)) ? ' Decisions made inside them go too.' : ''} This can’t be undone.
                  </span>
                  <span className="h-decision__confirm-actions">
                    <button type="button" className="h-link h-decision__danger" onClick={() => (setConfirming(null), onDelete(s))}>Delete</button>
                    <button type="button" className="h-link" autoFocus onClick={() => setConfirming(null)}>Keep</button>
                  </span>
                </div>
              )}
              <p className="h-decision__meta">
                {state === 'open' && !s.example ? (
                  <button type="button" className="h-tag" title="Wrong? Click to change" onClick={() => onEdit(s, { scale: scale === 'big' ? 'small' : 'big' })}>{scale === 'big' ? 'life' : 'day to day'}</button>
                ) : (
                  <span className="h-tag">{scale === 'big' ? 'life' : 'day to day'}</span>
                )}
                <span>{s.example ? 'example · ' : ''}{state}{s.questions.some((q) => !q.answer) && state === 'open' ? ' · has a question' : ''}</span>
                {edit ? <label>by <input className="h-input h-input--date" type="date" defaultValue={deadline ?? ''} onChange={(e) => onEdit(s, { decide_by: e.target.value || null })} /></label> : deadline && <span>by {dayLabel(deadline)}</span>}
              </p>
              {/* the paths are shown on the right; here they only appear as fields, while editing */}
              {edit && <ul className="h-paths">
                {branches.filter((b) => b.branch.option_id).map((b) => (
                  <li key={b.branch.id}>
                    <input className="h-input" defaultValue={b.branch.label} aria-label="Rename this path" onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()} onBlur={(e) => e.target.value.trim() && e.target.value.trim() !== b.branch.label && onEdit(s, { rename: { option_id: b.branch.option_id!, title: e.target.value.trim() } })} />
                  </li>
                ))}
                {branches.length < 4 && (
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
