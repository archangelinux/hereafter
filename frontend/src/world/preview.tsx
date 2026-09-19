// A standalone stage for the world, fed from the fixtures: http://localhost:5642/world-preview.html
//   ?active=br-sf&step=6      walk a branch        ?rare=br-tonight     show the rarest life there
//   ?state=merged             decide the open three-way fork (masters), so its siblings weather
// The buttons do the same things live, so growing, merging, weathering and undo can be watched.

import { StrictMode, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource/cormorant-garamond/400.css'
import '@fontsource/cormorant-garamond/500.css'
import '@fontsource/cormorant-garamond/400-italic.css'
import '@fontsource/cormorant-garamond/500-italic.css'
import '@fontsource/cormorant-sc/500.css'
import { demoBranches, demoRare, demoScenarios, demoTrunkEvents } from '../fixtures/demo'
import type { BranchView, LifeEvent, Scenario } from '../types'
import { World } from './World'

const params = new URLSearchParams(location.search)
const today = new Date().toISOString().slice(0, 10)

function decide(views: BranchView[], scenarios: Scenario[], events: LifeEvent[], chosen: string) {
  const scenario = scenarios.find((s) => s.branch_ids.includes(chosen))!
  return {
    views: views.map((v) => (scenario.branch_ids.includes(v.branch.id) ? { ...v, branch: { ...v.branch, status: v.branch.id === chosen ? ('merged' as const) : ('faded' as const) } } : v)),
    scenarios: scenarios.map((s) => (s === scenario ? { ...s, status: 'decided' as const, decided_branch_id: chosen } : s)),
    events: [...events, { id: 'main-decided', person_id: 'demo', source: 'told' as const, branch_id: 'main', date: today, domain: 'work', event_type: 'decision', payload: { from_branch: chosen }, confidence: 1, text: 'Chose' }],
  }
}

function Preview() {
  const [data, setData] = useState(() => {
    const base = { views: demoBranches, scenarios: demoScenarios, events: demoTrunkEvents }
    const withCommit = { ...base, views: base.views.map((v) => (v.branch.id === 'br-sf' ? { ...v, branch: { ...v.branch, commits: [{ id: 'c1', branch_id: 'br-sf', year: v.years[3].year, at: v.years[3].at, message: 'We agreed I would come home for the winters', patch: {}, created_at: today }] } } : v)) }
    return params.get('state') === 'merged' ? decide(withCommit.views, withCommit.scenarios, withCommit.events, 'br-masters') : withCommit
  })
  const [hidden, setHidden] = useState<string[]>(params.get('hide')?.split(',') ?? [])
  const [activeId, setActiveId] = useState<string | null>(params.get('active'))
  const [step, setStep] = useState<number | null>(params.has('step') ? Number(params.get('step')) : null)
  const [rareId, setRareId] = useState<string | null>(params.get('rare'))
  const [heard, setHeard] = useState('')

  const scenarios = useMemo(() => data.scenarios.filter((s) => !hidden.includes(s.id)), [data, hidden])
  const views = useMemo(() => data.views.filter((v) => scenarios.some((s) => s.branch_ids.includes(v.branch.id))), [data, scenarios])
  const now = useMemo(() => new Date().toISOString(), [])
  const rare = rareId && rareId === activeId ? (demoRare[rareId]?.years ?? null) : null

  return (
    <div style={{ position: 'fixed', inset: 0 }}>
      <World
        now={now}
        events={data.events}
        views={views}
        scenarios={scenarios}
        activeId={activeId}
        hereStep={step}
        rare={rare}
        onSwitch={(id) => (setActiveId((a) => (a === id ? null : id)), setStep(0))}
        onSeek={(id, s) => (setActiveId(id), setStep(s))}
        safeInsets={params.has('hud') ? { top: 24, right: 24, bottom: 210, left: 370 } : { top: 44 }}
        onOpenLog={() => setHeard('open log')}
        onArrive={(eventId) => setHeard(`arrived: ${eventId}`)}
      />
      <div style={{ position: 'fixed', left: 16, top: 12, display: 'flex', gap: 14, font: "13px 'Cormorant SC', serif", letterSpacing: '0.1em', color: '#8a8073' }}>
        <button onClick={() => (setActiveId(null), setStep(null))}>overview</button>
        <button onClick={() => setStep((s) => (s ?? 0) + 1)}>step on</button>
        <button onClick={() => setStep((s) => Math.max(0, (s ?? 0) - 1))}>step back</button>
        <button onClick={() => setData((d) => decide(d.views, d.scenarios, d.events, 'br-masters'))}>merge masters</button>
        <button onClick={() => setHidden((h) => (h.includes('sc-noor') ? h.filter((x) => x !== 'sc-noor') : [...h, 'sc-noor']))}>undo / redo noor</button>
        <button onClick={() => setRareId((r) => (r ? null : activeId))}>rare life</button>
        <span>{heard}</span>
      </div>
    </div>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Preview />
  </StrictMode>,
)
