import { Component, lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState, type ComponentType, type ReactNode } from 'react'
import { clearSession, getApi, loadSession, saveSession, setToken, type Api } from './api'
import { Decisions } from './hud/Decisions'
import { MergePanel } from './hud/MergePanel'
import type { Mode } from './hud/ModeSwitch'
import { NewDecision } from './hud/NewDecision'
import { useSteps } from './hud/useSteps'
import { useRails } from './hud/useRails'
import { useZones } from './hud/useZones'
import { withGuides } from './derive'
import { belongsOnLine } from './format'
import { Line } from './line/Line'
import { theme } from './theme'
import type { BranchView, IngestResult, Insets, ResearchStep, TicketPatch, LifeEvent, Question, Scenario, Session, TrunkResponse, Zone } from './types'
import { Compare } from './views/Compare'
import { InventoryView } from './views/InventoryView'
import { LogView } from './views/LogView'
import { ModelSheet } from './views/ModelSheet'
import { Offering, type OfferingDraft } from './views/Offering'
import { Tell } from './views/Tell'

type Sheet = 'offering' | 'compare' | 'model' | 'log' | 'inventory' | 'tell' | null

/** Both views of the same place take exactly these props. */
interface ViewProps {
  now: string
  events: LifeEvent[]
  views: BranchView[]
  scenarios: Scenario[]
  activeId: string | null
  hereStep: number | null
  onSwitch: (branchId: string) => void
  onSeek: (branchId: string, step: number) => void
  onOpenLog: () => void
}

/** what only the island view takes: where the HUD is, and word of the figure's walking */
interface WorldExtras {
  safeInsets?: Insets
  onArrive?: (eventId: string, branchId: string) => void
  onWalking?: (moving: boolean) => void
  onFocusScenario?: (scenarioId: string) => void // the World's name for focusing a decision (Line calls it onFocusDecision)
}

// Island view: the 3D world, a drop-in module built beside this one. If it has not landed, or
// WebGL is unavailable, or it throws, Line view is simply the only view and the switch hides.
const worldModules = import.meta.glob('./world/World.tsx')
const loadWorld = worldModules['./world/World.tsx']
const World = loadWorld
  ? lazy(async () => {
      const m = (await loadWorld()) as { World?: ComponentType<ViewProps & WorldExtras>; default?: ComponentType<ViewProps & WorldExtras> }
      return { default: (m.World ?? m.default)! }
    })
  : null
const hasWebGL = (() => {
  try {
    const c = document.createElement('canvas')
    return !!(c.getContext('webgl2') ?? c.getContext('webgl'))
  } catch {
    return false
  }
})()

class Boundary extends Component<{ onFail: () => void; children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  componentDidCatch(err: unknown) {
    console.info('[hereafter] island view failed; staying in line view', err)
    this.props.onFail()
  }
  render() {
    return this.state.failed ? null : this.props.children
  }
}

const params = new URLSearchParams(location.search)
const NO_INSETS: Insets = { top: 0, right: 0, bottom: 0, left: 0 }
const asking0 = (s: Scenario | null, a: BranchView | null, skipped: string[]) => (a?.branch.status === 'open' ? (s?.questions ?? []).filter((q) => !q.answer && !skipped.includes(q.id)).length : 0)
const typing = () => ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName ?? '')

export default function App() {
  const [api, setApi] = useState<Api | null>(null)
  const [session, setSession] = useState<Session | null>(loadSession)
  const [onboarding, setOnboarding] = useState(() => !loadSession()) // a new person sees only the intake pages until they press Continue on the last one
  const [ownTrunk, setTrunk] = useState<TrunkResponse | null>(null)
  const [ownViews, setViews] = useState<BranchView[]>([])
  const [ownScenarios, setScenarios] = useState<Scenario[]>([])
  const [focusedId, setFocusedId] = useState<string | null | undefined>(undefined) // undefined: not chosen yet; null: nothing in focus
  const [done, setDone] = useState<Record<string, number>>(() => JSON.parse(localStorage.getItem('hereafter.hints') ?? '{}') as Record<string, number>)
  const [advances, setAdvances] = useState(0)
  const [justMerged, setJustMerged] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [activeId, setActiveId] = useState<string | null>(params.get('branch'))
  const [hereStep, setHereStep] = useState<number | null>(null)
  const [seek, setSeek] = useState<{ step: number; nonce: number } | null>(null)
  const [sheet, setSheet] = useState<Sheet>(params.get('sheet') === 'decision' ? null : ((params.get('sheet') as Sheet) ?? null))
  const [deciding, setDeciding] = useState(params.get('sheet') === 'decision')
  const [research, setResearch] = useState<ResearchStep | null>(null)
  const [committing, setCommitting] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [ingested, setIngested] = useState<IngestResult | 'silent' | null>(null)
  const [assuming, setAssuming] = useState<BranchView | null>(null)
  const [firmed, setFirmed] = useState(false)
  const [skipped, setSkipped] = useState<string[]>([])
  const [mode, setMode] = useState<Mode>(() => (params.get('view') as Mode) ?? (localStorage.getItem('hereafter.mode') as Mode) ?? 'island')
  const [worldFailed, setWorldFailed] = useState(false)
  const [fading, setFading] = useState(false)
  const [mapOpen, setMapOpen] = useState(() => innerWidth > 1100 && innerHeight > 680)
  const [rail, setRail] = useState(false)
  const [walking, setWalking] = useState(false)
  const walkTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const loaded = useRef(false)

  const islandAvailable = !!World && hasWebGL && !worldFailed
  const view: Mode = islandAvailable ? mode : 'line'

  const [bootError, setBootError] = useState(false)
  useEffect(() => void getApi().then(setApi).catch(() => setBootError(true)), [])

  // A stored session opens that person's own main and decisions.
  const views = ownViews
  const scenarios = ownScenarios
  const trunk = ownTrunk
  useEffect(() => {
    if (api?.offline && !session) (setSession({ person_id: 'offline', token: 'offline' }), setOnboarding(false))
  }, [api, session])

  const refresh = useCallback(async () => {
    if (!api || !session) return
    try {
      setToken(session.token || null)
      const t = await api.trunk(session.person_id)
      const b = await api.branches(session.person_id)
      const s = await api.scenarios(session.person_id)
      setTrunk(t)
      setViews(b.branches)
      setScenarios(s)
      loaded.current = true
    } catch (err) {
      console.info('[hereafter] could not refresh', err)
    }
  }, [api, session])

  // "now" advances on its own: main and the branches are asked again every minute, and more
  // often while a branch is still being researched
  const researching = views.some((v) => v.branch.forming || v.years.length === 0 || v.branch.research === 'pending' || v.branch.research === 'running')
  useEffect(() => {
    void refresh()
    const timer = setInterval(refresh, researching ? theme.motion.busyPollMs : theme.motion.pollMs)
    return () => clearInterval(timer)
  }, [refresh, researching])

  // point of view: a branch you have switched to, or none (the whole view)
  const active = useMemo(() => views.find((v) => v.branch.id === activeId) ?? null, [views, activeId])
  const newest = useMemo(() => {
    const open = scenarios.filter((s) => s.branch_ids.some((id) => views.find((v) => v.branch.id === id)?.branch.status === 'open'))
    return [...(open.length ? open : scenarios)].sort((a, b) => b.created_at.localeCompare(a.created_at))[0] ?? null
  }, [scenarios, views])
  const scenario = scenarios.find((s) => s.id === active?.branch.scenario_id) ?? null
  const siblings = useMemo(() => (scenario ? scenario.branch_ids.flatMap((id) => views.filter((v) => v.branch.id === id)) : active ? [active] : []), [scenario, views, active])
  const shown = scenario ?? (focusedId === undefined ? newest : (scenarios.find((x) => x.id === focusedId) ?? null))

  const did = useCallback((what: string) => {
    setDone((d) => {
      const next = { ...d, [what]: (d[what] ?? 0) + 1 }
      localStorage.setItem('hereafter.hints', JSON.stringify(next))
      return next
    })
  }, [])

  const switchTo = useCallback((id: string | null) => {
    setActiveId(id)
    setAdvances(0)
    setJustMerged(false)
    if (id) did('pick')
    setHereStep(null)
    setError(null)
    setFirmed(false)
    setCommitting(false)
    setNotice(null)
  }, [did])

  const focusOn = useCallback((scenarioId: string | null) => {
    setFocusedId(scenarioId)
    if (activeId && views.find((v) => v.branch.id === activeId)?.branch.scenario_id !== scenarioId) switchTo(null)
  }, [activeId, views, switchTo])

  const toggleMode = useCallback(() => {
    if (!islandAvailable) return
    setFading(true)
    setMode((m) => {
      const next = m === 'island' ? 'line' : 'island'
      localStorage.setItem('hereafter.mode', next)
      return next
    })
    setTimeout(() => setFading(false), 1500)
  }, [islandAvailable])

  // island view: the figure walks to where the reading is. Lines wait for it, but never for long.
  // The world says when it comes to rest; this is only a net for a dropped frame, so it has to outlast
  // the longest walk there is — the whole way out to a path's end platform. Cut it short and a press
  // held during that walk fires early and pulls the figure back a step or two.
  const onWalking = useCallback((moving: boolean) => {
    if (walkTimer.current) clearTimeout(walkTimer.current)
    setWalking(moving)
    if (moving) walkTimer.current = setTimeout(() => setWalking(false), 8000)
  }, [])


  /** an example can be walked and read, never changed */
  const real = (fn: () => void) => fn

  const replaceView = (v: BranchView) => setViews((all) => all.map((x) => (x.branch.id === v.branch.id ? v : x)))
  const fail = (err: unknown, fallback: string) => setError(err instanceof Error ? err.message : fallback)

  const createDecision = async (decision: string, paths: string[]) => {
    if (!api || !session) return
    setBusy('decide')
    setError(null)
    try {
      const made = await api.createScenario(session.person_id, decision, paths.map((title) => ({ title, details: '' })), assuming ? { assuming_branch_id: assuming.branch.id } : undefined)
      setScenarios((all) => [...all.filter((x) => x.id !== made.scenario.id), made.scenario])
      setViews((all) => [...all.filter((v) => !made.branches.some((m) => m.branch.id === v.branch.id)), ...made.branches])
      setDeciding(false)
      setAssuming(null)
      switchTo(null)
      setFocusedId(made.scenario.id) // a new decision, including one made inside a life, opens as the decision in focus
      did('add')
    } catch (err) {
      fail(err, 'That did not go through.')
    } finally {
      setBusy(null)
    }
  }

  const editTicket = async (scenario: Scenario, patch: TicketPatch) => {
    if (!api) return
    try {
      const res = await api.editTicket(scenario, patch)
      setScenarios((all) => all.map((x) => (x.id === res.scenario.id ? res.scenario : x)))
      setViews((all) => [...all.filter((v) => !res.branches.some((b) => b.branch.id === v.branch.id)), ...res.branches])
    } catch (err) {
      fail(err, 'That edit did not take.')
    }
  }

  const commit = async (at: string, message: string, eventKeys?: string[]) => {
    if (!api || !active) return
    setBusy('commit')
    setError(null)
    try {
      replaceView(await api.commit(active.branch.id, at, message, eventKeys))
      did('commit')
      setCommitting(false)
    } catch (err) {
      fail(err, 'The commit did not take.')
    } finally {
      setBusy(null)
    }
  }

  /** take back one assumption (any of them, in any order), or the last one made */
  const undo = useCallback(async (commitId?: string) => {
    if (!api || !active || !active.branch.commits.length || active.branch.example) return
    setBusy('undo')
    setError(null)
    try {
      replaceView(await api.undo(active.branch.id, commitId))
    } catch (err) {
      fail(err, 'There was nothing to undo.')
    } finally {
      setBusy(null)
    }
  }, [api, active])

  const answer = async (question: Question, text: string) => {
    if (!api) return
    setBusy(`answer:${question.id}`)
    setError(null)
    try {
      const res = await api.answer(question.scenario_id, { [question.id]: text })
      setScenarios((all) => all.map((x) => (x.id === res.scenario.id ? res.scenario : x)))
      setViews((all) => all.map((v) => res.branches.find((b) => b.branch.id === v.branch.id) ?? v))
      setFirmed(true)
    } catch (err) {
      fail(err, 'That answer could not be taken in just now.')
    } finally {
      setBusy(null)
    }
  }

  const merge = async (confirm: string) => {
    if (!api || !active) return
    setBusy('merge')
    setError(null)
    try {
      await api.merge(active.branch.id, confirm)
      did('merge')
      setJustMerged(true)
      await refresh()
    } catch (err) {
      fail(err, 'The merge did not go through. Nothing was changed.')
    } finally {
      setBusy(null)
    }
  }

  const offer = async (draft: OfferingDraft) => {
    if (!api) return
    setBusy('offer')
    try {
      let s = session
      if (!s) {
        s = await api.createPerson({ display_name: draft.name || undefined })
        saveSession(s)
        setToken(s.token || null)
        setSession(s)
      }
      setIngested(await api.ingest({
        person_id: s.person_id, display_name: draft.name || undefined, text: draft.text || undefined,
        files: draft.files, // draft.sources (the accounts chosen) is not sent yet: reading them comes with the Browserbase hookup
      }))
    } catch {
      setIngested('silent')
    } finally {
      setBusy(null)
    }
  }

  const tell = async (text: string) => {
    if (!api || !session) return
    setBusy('tell')
    setError(null)
    try {
      await api.ingest({ person_id: session.person_id, text })
      setSheet(null)
      await refresh()
    } catch (err) {
      fail(err, 'That could not be added just now.')
    } finally {
      setBusy(null)
    }
  }

  // the keyboard: light gestures only. Merge has no shortcut on purpose.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (onboarding || typing() || e.metaKey || e.ctrlKey || e.altKey) return
      const k = e.key.toLowerCase()
      if (k === 'escape') {
        if (deciding) setDeciding(false)
        else if (committing) setCommitting(false)
        else if (!sheet && active) (setFocusedId(active.branch.scenario_id), switchTo(null))
        else if (!sheet && shown) setFocusedId(null)
        return
      }
      if (sheet) return
      if (k === 'v' || k === 'm') return toggleMode()
      if (!active) return
      if (k === 's' && siblings.length > 1) {
        const i = siblings.findIndex((s) => s.branch.id === active.branch.id)
        switchTo(siblings[(i + 1) % siblings.length].branch.id)
      } else if (k === 'c' && siblings.length > 1) setSheet('compare')
      else if (k === 'k' && active.branch.status === 'open') (e.preventDefault(), real(() => setCommitting(true))())
      else if (k === 'u') void undo()
      else if (k === 'b' && active.branch.status === 'open') real(() => (setAssuming(active), setDeciding(true)))()
    }
    // N opens the decision box on key-up, so the letter itself never lands in the field
    const onUp = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === 'n' && !onboarding && !typing() && !sheet && !e.metaKey && !e.ctrlKey && !e.altKey) (setAssuming(null), setDeciding(true))
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener('keyup', onUp)
    return () => (window.removeEventListener('keydown', onKey), window.removeEventListener('keyup', onUp))
  }, [active, siblings, sheet, committing, deciding, switchTo, toggleMode, undo, shown, onboarding])

  // Living a path is stepping through it in the world itself — there is no panel of prose.
  const steps = useSteps({
    view: active,
    seek,
    walking: view === 'island' && walking,
    followsFigure: view === 'island',
    onStep: setHereStep,
    onAdvance: () => (setAdvances((n) => n + 1), did('walk')),
  })

  const drawn = useMemo(() => (trunk ? withGuides(views, scenarios, trunk.now, trunk.state) : views), [views, scenarios, trunk])
  // The past is continuous: once a decision is settled it keeps its paths for good — the one chosen
  // and the ones dropped — so the tree only ever grows. Only a decision still open, and not the one
  // being considered, collapses to its circle on main; a decision made INSIDE a path needs that path
  // drawn to hang off, so the chain it was made in stays open too.
  const open = useMemo(() => {
    const byBranch = new Map(views.map((v) => [v.branch.id, v.branch.scenario_id]))
    const ids = new Set<string>()
    for (const s of scenarios) {
      const branches = s.branch_ids.flatMap((id) => views.filter((v) => v.branch.id === id))
      if (branches.length > 0 && !branches.some((b) => b.branch.status === 'open')) ids.add(s.id)
    }
    const chain = new Set<string>() // the decision being considered, and the paths it was made inside
    let at = shown ?? null
    while (at && !chain.has(at.id)) {
      chain.add(at.id)
      ids.add(at.id)
      const parent = at.assuming_branch_id ? byBranch.get(at.assuming_branch_id) : null
      at = parent ? (scenarios.find((x) => x.id === parent) ?? null) : null
    }
    return ids
  }, [shown, scenarios, views])
  // Every decision's paths go to the scene — the ones that are only a circle need theirs to know
  // they exist at all — and the layout draws lanes for the open ones alone.
  // every path ever drawn stays in the scene, closed ones included: they are drawn back as ruins, not removed
  const sceneViews = useMemo(
    // No dates on a projected step: nothing here has happened. Only a commit the person made carries one.
    () => drawn.map((v) => ({ ...v, years: v.years.map((y) => ({ ...y, label: '' })) })),
    [drawn],
  )
  const sceneScenarios = useMemo(() => scenarios.map((x) => ({ ...x, collapsed: !open.has(x.id) })), [scenarios, open])
  const sceneEvents = useMemo(() => (trunk?.events ?? []).filter((e) => e.event_type !== 'goal' && (e.branch_id !== 'main' || belongsOnLine(e))), [trunk])

  // exactly one plain next-step line, gone once the person has done that thing twice
  const hint = justMerged ? 'Recorded on main. The other paths are closed.'
    : scenarios.length === 0 ? ((done.add ?? 0) < 2 ? 'Press N to add a decision' : null)
    : !shown ? ((done.pick ?? 0) < 2 ? 'Click a decision on main to open it' : null)
    : !active ? ((done.pick ?? 0) < 2 ? 'Pick a path to live it' : null)
    : advances < 3 ? ((done.walk ?? 0) < 6 ? 'Space to live it forward' : null)
    : active.branch.status === 'open' && (done.commit ?? 0) + (done.add ?? 0) < 2 && advances < 7 ? 'Commit pins what you would have happen and redraws what follows. Branch splits the path. Both can be undone — only Merge is permanent.'
    : active.branch.status === 'open' && (done.merge ?? 0) < 2 ? 'Merge makes this choice real. Or pick another path.' : null

  const rails = useRails()
  const { zones, free } = useZones([rails.key, hint, deciding, shown?.id, !!active, view, mapOpen, asking0(scenario, active, skipped), scenarios.length, !!trunk])
  const watch = active && !active.branch.example && (active.branch.forming || active.years.length === 0 || active.branch.research === 'pending' || active.branch.research === 'running') ? active.branch.id : null
  useEffect(() => {
    setResearch(null)
    if (!api || !watch) return
    let live = true
    const poll = () => void api.research(watch).then((r) => live && setResearch(r.steps[r.steps.length - 1] ?? null)).catch(() => undefined)
    poll()
    const timer = setInterval(poll, theme.motion.busyPollMs)
    return () => {
      live = false
      clearInterval(timer)
    }
  }, [api, watch])

  if (!api) {
    return bootError ? (
      <div className="boot boot--error" role="alert">
        <p>Hereafter can’t reach its backend.</p>
        <p>Start it (uvicorn on port 8642), then reload this page.</p>
      </div>
    ) : <div className="boot" />
  }

  const firstRun = !session
  const showOffering = firstRun || sheet === 'offering' || ingested !== null
  const intake = onboarding && showOffering // nothing of the app itself shows behind the intake pages
  const asking = active?.branch.status === 'open' ? (scenario?.questions ?? []).filter((q) => !q.answer && !skipped.includes(q.id) && (q.applies_to.length === 0 || q.applies_to.includes(active.branch.option_id ?? ''))) : []

  const viewProps: ViewProps | null = trunk && {
    now: trunk.now,
    events: sceneEvents,
    views: sceneViews,
    scenarios: sceneScenarios,
    activeId: active?.branch.id ?? null,
    hereStep,
    onSwitch: switchTo,
    onSeek: (id, step) => (id !== active?.branch.id && switchTo(id), setSeek({ step, nonce: Date.now() })),
    onOpenLog: () => setSheet('log'),
  }

  return (
    <div className={`app app--${view}`}>
      {/* two views of the same place; the HUD sits over whichever is on */}
      {!intake && <div className="stage">
        {viewProps && World && islandAvailable && (view === 'island' || fading) && (
          <div className={`stage__layer ${view === 'island' ? 'is-on' : ''}`}>
            <Boundary onFail={() => setWorldFailed(true)}>
              <Suspense fallback={null}>
                <World {...viewProps} safeInsets={free} onWalking={onWalking} onFocusScenario={focusOn} />
              </Suspense>
            </Boundary>
          </div>
        )}
        {viewProps && (view === 'line' || fading) && (
          <div className={`stage__layer ${view === 'line' ? 'is-on' : ''}`}>
            <Line {...viewProps} zones={zones as Zone[]} free={free} onFocusDecision={focusOn} />
          </div>
        )}
      </div>}

      {!intake && <div className="hud" style={rails.style}>
        <div className="hud__top">
          <button type="button" className="h-link" onClick={() => setRail((v) => !v)}>{rail ? 'Close' : 'Decisions'}</button>
          <span>Hereafter</span>
        </div>

        <aside className={`hud__left ${rail ? 'is-open' : ''} ${rails.collapsed('left') ? 'is-collapsed' : ''}`}>
          {!rails.narrow && !rails.collapsed('left') && <div {...rails.grip('left')} />}
          {rails.collapsed('left') && <button type="button" className="h-tab" onClick={() => rails.toggle('left')} title="Open the decisions panel">Decisions ›</button>}
          <header className="h-brand">
            <button type="button" className="h-fold" onClick={() => rails.toggle('left')} title="Fold this panel away" aria-label="Fold the decisions panel away">‹</button>
            <h1>Hereafter</h1>
            <p>{trunk?.person.display_name || ''}{trunk?.person.personality?.mbti ? ` · ${trunk.person.personality.mbti}` : ''}{api.offline ? ' · no data' : ''}</p>
          </header>
          <Decisions
            scenarios={scenarios}
            views={drawn}
            focusId={shown?.id ?? null}
            onFocus={(id) => (focusOn(id), setRail(false))}
            onEdit={(sc, patch) => void editTicket(sc, patch)}
            onNew={() => (setAssuming(null), setDeciding(true), setRail(false))}
          />
          {error && !shown && <p className="h-note h-note--error">{error}</p>}
          <div className="h-fill" />
          {/* the two views mirror each other: each shows a small live preview of the other. Only one full World is ever mounted. */}
          {view === 'line' && !fading && viewProps && World && islandAvailable && (
            <div className="h-map">
              <button type="button" className="h-link" onClick={() => setMapOpen((v) => !v)}>{mapOpen ? 'Hide the 3D preview' : 'Show the 3D preview'}</button>
              {mapOpen && (
                <div className="h-map__frame h-map__frame--world">
                  <Boundary onFail={() => setWorldFailed(true)}>
                    <Suspense fallback={null}>
                      <World {...viewProps} safeInsets={NO_INSETS} />
                    </Suspense>
                  </Boundary>
                  <button type="button" className="h-map__switch" onClick={toggleMode} title="Switch to the 3D view (V)" aria-label="Switch to the 3D view" />
                </div>
              )}
            </div>
          )}
          {view === 'island' && viewProps && (
            <div className="h-map">
              <button type="button" className="h-link" onClick={() => setMapOpen((v) => !v)}>{mapOpen ? 'Hide the line map' : 'Show the line map'}</button>
              {mapOpen && <div className="h-map__frame"><Line {...viewProps} compact onFocusDecision={focusOn} /></div>}
            </div>
          )}
          <footer className="h-foot">
            {World && hasWebGL && (
              <div className="h-seg" role="group" aria-label="view" title="Switch view (V)">
                <button type="button" className={view === 'island' ? 'is-on' : ''} disabled={worldFailed} onClick={() => view !== 'island' && toggleMode()}>Island (3D)</button>
                <button type="button" className={view === 'line' ? 'is-on' : ''} onClick={() => view !== 'line' && toggleMode()}>Line</button>
              </div>
            )}
            {(worldFailed || !hasWebGL || !World) && <p className="h-muted">3D view unavailable — showing the line.</p>}
            <nav className="h-foot__row" aria-label="more">
              <button type="button" className="h-link" onClick={() => setSheet('log')}>Log</button>
              <button type="button" className="h-link" onClick={() => setSheet('inventory')}>Your data</button>
            </nav>
          </footer>
        </aside>

        <div className="hud__bottom">
          {hint && !deciding && <p className="h-hint" key={hint}>{hint}</p>}
          {deciding && session ? (
            <NewDecision inside={assuming ? assuming.branch.label : null} busy={busy === 'decide'} error={error} onCreate={(d, ps) => void createDecision(d, ps)} onClose={() => setDeciding(false)} />
          ) : null}

        </div>

        <div className={`hud__right ${rails.collapsed('right') ? 'is-collapsed' : ''}`}>
          {!rails.narrow && !rails.collapsed('right') && shown && <div {...rails.grip('right')} />}
          {shown && !rails.narrow && (
            <button type="button" className={rails.collapsed('right') ? 'h-tab h-tab--right' : 'h-fold h-fold--right'} onClick={() => rails.toggle('right')} title={rails.collapsed('right') ? 'Open this panel' : 'Fold this panel away'}>
              {rails.collapsed('right') ? `‹ ${shown.situation}` : '›'}
            </button>
          )}
          {shown && (
            <MergePanel
              api={api}
              committing={committing}
              onCommitStep={(message) => { const at = steps.at?.at; return at ? commit(at, message) : Promise.resolve() }}
              onCancelCommit={() => setCommitting(false)}
              assumed={(active?.branch.commits ?? []).map((c) => c.event_key ?? '').filter(Boolean)}
              onDrop={(key) => void undo((active?.branch.commits ?? []).find((c) => c.event_key === key)?.id)}
              scenario={shown}
              paths={shown.branch_ids.flatMap((id) => drawn.filter((v) => v.branch.id === id))}
              head={active && active.branch.scenario_id === shown.id ? active : null}
              busy={busy}
              error={error}
              notice={firmed ? 'Added to main. The paths it speaks to have firmed up.' : notice}
              research={research}
              question={asking[0] ?? null}
              onHead={switchTo}
              onMerge={(confirm) => void merge(confirm)}
              onCommit={real(() => setCommitting(true))}
              onUndo={() => void undo()}
              onCompare={() => setSheet('compare')}
              onInside={real(() => (setAssuming(active), setDeciding(true)))}
              onAnswer={(q, a2) => void answer(q, a2)}
              onSkip={(q) => setSkipped((all) => [...all, q.id])}
              onModel={() => setSheet('model')}
              onPin={(keys) => { const at = (active?.years[hereStep ?? 0] ?? active?.years[0])?.at; if (at) void commit(at, '', keys) }}
              step={hereStep}
              person={trunk?.person ?? null}
            />
          )}
        </div>
      </div>}

      {sheet === 'compare' && active && <Compare api={api} views={[active, ...siblings.filter((s) => s.branch.id !== active.branch.id)]} scenario={scenario} onSwitch={(id) => (switchTo(id), setSheet(null))} onClose={() => setSheet(null)} />}
      {sheet === 'model' && <ModelSheet api={api} onClose={() => setSheet(null)} />}
      {sheet === 'log' && trunk && <LogView events={trunk.events} reconciliation={trunk.reconciliation ?? []} onTell={() => setSheet('tell')} onClose={() => setSheet(null)} />}
      {sheet === 'inventory' && session && (
        <InventoryView api={api} personId={session.person_id} onChanged={() => void refresh()} onOffer={() => (setIngested(null), setSheet('offering'))} onErased={() => (clearSession(), setSession(null), setTrunk(null), setViews([]), setScenarios([]), setSheet(null), setOnboarding(true), switchTo(null))} onClose={() => setSheet(null)} />
      )}
      {sheet === 'tell' && <Tell busy={busy === 'tell'} error={error} onSubmit={tell} onClose={() => setSheet(null)} />}
      {showOffering && (
        <Offering
          busy={busy === 'offer'}
          firstRun={firstRun}
          result={ingested}
          onSubmit={offer}
          onEnter={() => (setIngested(null), setSheet(null), setOnboarding(false), void refresh())}
          onClose={() => setSheet(null)}
        />
      )}
    </div>
  )
}
