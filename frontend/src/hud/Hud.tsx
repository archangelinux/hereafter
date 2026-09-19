import { useState } from 'react'
import { dayLabel, deadlineOf } from '../format'
import { BasisMark } from '../page/marks'
import { theme } from '../theme'
import type { BranchView, LifeEvent, Question, Scenario, Which } from '../types'

const STATUS: Record<string, string> = { open: 'open branch', merged: 'merged into main', faded: 'a road not taken', stale: 'stale' }

/** Top right: which life you are in, and what could happen in it. Compact, collapsible. */
export function BranchCard({ view, scenario, accent, onEvidence }: { view: BranchView; scenario: Scenario | null; accent: string; onEvidence: (ids: string[]) => void }) {
  const [more, setMore] = useState(false)
  const [open, setOpen] = useState(true)
  const [all, setAll] = useState(false)
  const { branch } = view
  const deadline = deadlineOf(branch.precondition)
  const option = scenario?.options.find((o) => o.id === branch.option_id)
  return (
    <section className="hud-card branch-card" style={{ ['--accent' as string]: accent }}>
      {scenario && (
        <button type="button" className={`branch-card__situation ${more ? 'is-open' : ''}`} onClick={() => setMore((v) => !v)} title={more ? 'less' : 'more'}>
          “{scenario.situation}”
        </button>
      )}
      <p className="caps branch-card__status">
        {STATUS[branch.status] ?? branch.status}
        {branch.status === 'open' && deadline ? ` · until ${dayLabel(deadline)}` : ''}
        {scenario?.assuming_branch_id ? ' · inside another life' : ''}
      </p>
      <h1 className="branch-card__title">{branch.label}</h1>
      {more && option?.details && <p className="branch-card__details">{option.details}</p>}
      {branch.model.events.length > 0 && (
        <div className="could">
          <button type="button" className="caps could__toggle" onClick={() => setOpen((v) => !v)} aria-expanded={open}>what could happen {open ? '−' : '+'}</button>
          {open && (
            <ul>
              {branch.model.events.slice(0, all ? undefined : 4).map((e) => (
                <li key={e.key} title={e.label + ' — ' + (e.basis === 'estimated' ? 'an estimate, no published figure found' : e.basis === 'sourced' ? 'from a published figure' : 'from the life-course tables')}>
                  <BasisMark basis={e.basis} />
                  {e.basis === 'sourced' && e.evidence_id ? (
                    <button type="button" className="quiet could__label" onClick={() => onEvidence([e.evidence_id!])}>{e.label}</button>
                  ) : (
                    <span className="could__label">{e.label}</span>
                  )}
                  <span className="could__words">{e.words}</span>
                </li>
              ))}
              {branch.model.events.length > 4 && (
                <li><span /><button type="button" className="quiet" onClick={() => setAll((v) => !v)}>{all ? 'fewer' : 'and more'}</button></li>
              )}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}

/** A clarifying question, asked small, by the figure. Skipping costs nothing but mist. */
export function Asking({ question, busy, onAnswer, onSkip }: { question: Question; busy: boolean; onAnswer: (a: string) => void; onSkip: () => void }) {
  const [own, setOwn] = useState('')
  return (
    <aside className="hud-card asking" aria-label="a question from Hereafter">
      <p className="asking__text">{question.text}</p>
      <p className="asking__why">{question.why}. Until then these branches stay faint.</p>
      <div className="asking__choices">
        {question.choices.map((c) => (
          <button key={c} type="button" className="chip" disabled={busy} onClick={() => onAnswer(c)}>{c}</button>
        ))}
      </div>
      <form className="asking__own" onSubmit={(e) => (e.preventDefault(), own.trim() && onAnswer(own.trim()))}>
        <input value={own} onChange={(e) => setOwn(e.target.value)} placeholder="or in your own words" aria-label="your own answer" />
        <button type="button" className="quiet" onClick={onSkip}>{busy ? 'redrawing' : 'skip'}</button>
      </form>
    </aside>
  )
}

interface BarProps {
  view: BranchView
  siblings: BranchView[]
  which: Which
  busy: string | null
  scenarios: Scenario[]
  onSwitch: (id: string) => void
  onCompare: () => void
  onCommit: () => void
  onUndo: () => void
  onWhich: (w: Which) => void
  onInside: () => void
  onMerge: () => void
  onOverview: () => void
}

/** Bottom right: the gestures. Light ones together; merge set apart, and heavier. */
export function ActionBar(p: BarProps) {
  const [lanes, setLanes] = useState(false)
  const { branch } = p.view
  const open = branch.status === 'open'
  const others = p.siblings.filter((s) => s.branch.id !== branch.id)
  return (
    <nav className="actions" aria-label="what you can do on this branch">
      {lanes && (
        <ul className="hud-card actions__lanes">
          {others.length === 0 && <li className="dim">No other branch in this decision.</li>}
          {others.map((s) => {
            const i = Math.max(0, p.scenarios.find((x) => x.id === s.branch.scenario_id)?.branch_ids.indexOf(s.branch.id) ?? 0)
            return (
              <li key={s.branch.id}>
                <button type="button" className="quiet" onClick={() => (setLanes(false), p.onSwitch(s.branch.id))}>
                  <i style={{ background: s.branch.status === 'open' ? theme.branch[i % theme.branch.length] : theme.color.ruin }} />
                  {s.branch.label}
                  {s.branch.status !== 'open' && <span className="caps"> {STATUS[s.branch.status]}</span>}
                </button>
              </li>
            )
          })}
          <li><button type="button" className="quiet" onClick={() => (setLanes(false), p.onOverview())}>step back to the whole view</button></li>
        </ul>
      )}
      <div className="hud-card actions__light">
        <Act label="switch" hint="S" onClick={() => setLanes((v) => !v)} />
        {others.length > 0 && <Act label="compare" hint="C" onClick={p.onCompare} />}
        {open && p.which === 'typical' && <Act label="commit here" hint="K" onClick={p.onCommit} />}
        {open && branch.commits.length > 0 && <Act label="undo" hint="U" onClick={p.onUndo} disabled={p.busy === 'undo'} title={`undo “${branch.commits[branch.commits.length - 1].message}”. It was never real.`} />}
        <Act label={p.which === 'typical' ? 'rarest life' : 'typical life'} hint="R" strange onClick={() => p.onWhich(p.which === 'typical' ? 'rare' : 'typical')} disabled={p.busy === 'rare'} />
        {open && p.which === 'typical' && <Act label="decide inside" hint="D" onClick={p.onInside} title="decide something inside this life" />}
      </div>
      {open && (
        <button type="button" className="actions__merge" onClick={p.onMerge} title="This is what I actually chose. It cannot be undone.">
          <svg viewBox="0 0 28 28" width={24} height={24} aria-hidden="true">
            <path d="M8 25 V14 C8 8 20 10 20 3 M20 25 V3" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" />
          </svg>
          <span>merge into main</span>
        </button>
      )}
    </nav>
  )
}

function Act({ label, hint, onClick, disabled, title, strange }: { label: string; hint: string; onClick: () => void; disabled?: boolean; title?: string; strange?: boolean }) {
  return (
    <button type="button" className={`act ${strange ? 'act--strange' : ''}`} onClick={onClick} disabled={disabled} title={title}>
      <span>{label}</span>
      <kbd>{hint}</kbd>
    </button>
  )
}

/** Satchel: the moments picked from roads not taken, carried on main. */
export function Satchel({ goals, views, onClose }: { goals: LifeEvent[]; views: BranchView[]; onClose: () => void }) {
  return (
    <aside className="hud-card satchel">
      <header><p className="caps">the satchel</p><button type="button" className="quiet" onClick={onClose}>close</button></header>
      {goals.length === 0 && <p className="dim">Empty. From a road not taken you may pick one moment to carry onto main.</p>}
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
