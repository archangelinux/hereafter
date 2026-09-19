import { Component, lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState, type ComponentType, type ReactNode } from 'react'
import { clearSession, getApi, loadSession, saveSession, setToken, type Api } from './api'
import { Decisions } from './hud/Decisions'
import { Satchel } from './hud/Hud'
import { MergePanel } from './hud/MergePanel'
import type { Mode } from './hud/ModeSwitch'
import { NewDecision } from './hud/NewDecision'
import { Narration } from './hud/Narration'
import { useRails } from './hud/useRails'
import { useZones } from './hud/useZones'
import { withGuides } from './derive'
import { belongsOnLine, isByYear, stepDate } from './format'
import { accentOf, Line } from './line/Line'
import { EvidenceDrawer } from './page/EvidenceDrawer'
import { Page } from './page/Page'
import { theme } from './theme'
import type { BranchView, BranchYear, IngestResult, Insets, ResearchStep, TicketPatch, LifeEvent, LivesResponse, Question, Scenario, Session, TrunkResponse, Which, Zone } from './types'
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
  rare: BranchYear[] | null
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
  const [ownTrunk, setTrunk] = useState<TrunkResponse | null>(null)
  const [ownViews, setViews] = useState<BranchView[]>([])
  const [ownScenarios, setScenarios] = useState<Scenario[]>([])
  const [focusedId, setFocusedId] = useState<string | null | undefined>(undefined) // undefined: not chosen yet; null: nothing in focus
  const [done, setDone] = useState<Record<string, number>>(() => JSON.parse(localStorage.getItem('hereafter.hints') ?? '{}') as Record<string, number>)
  const [advances, setAdvances] = useState(0)
  const [justMerged, setJustMerged] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [activeId, setActiveId] = useState<string | null>(params.get('branch'))
  const [which, setWhich] = useState<Which>('typical')
  const [rare, setRare] = useState<LivesResponse | null>(null)
  const [hereStep, setHereStep] = useState<number | null>(null)
  const [seek, setSeek] = useState<{ step: number; nonce: number } | null>(null)
  const [drawer, setDrawer] = useState<{ ids: string[]; step: BranchYear | null; collected?: boolean } | null>(null)
  const [sheet, setSheet] = useState<Sheet>(params.get('sheet') === 'decision' ? null : ((params.get('sheet') as Sheet) ?? null))
  const [deciding, setDeciding] = useState(params.get('sheet') === 'decision')
  const [research, setResearch] = useState<ResearchStep | null>(null)
  const [reading, setReading] = useState(params.has('read'))
  const [satchel, setSatchel] = useState(false)
  const [committing, setCommitting] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [ingested, setIngested] = useState<IngestResult | 'silent' | null>(null)
  const [assuming, setAssuming] = useState<BranchView | null>(null)
  const [firmed, setFirmed] = useState(false)
  const [skipped, setSkipped] = useState<string[]>([])
  const [collected, setCollected] = useState<string[]>(() => JSON.parse(localStorage.getItem('hereafter.codex') ?? '[]') as string[])
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

  useEffect(() => void getApi().then(setApi), [])

  // Your own life is the demo: a stored session opens that person's own main and decisions.
  // The sample person is only ever at ?person=demo, or behind "see an example".
  const views = ownViews
  const scenarios = ownScenarios
  const trunk = ownTrunk
  useEffect(() => {
    if (api?.offline && !session) setSession({ person_id: 'demo', token: 'demo' })
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
  const goals = useMemo(() => (trunk?.events ?? []).filter((e) => e.event_type === 'goal'), [trunk])

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
    setWhich('typical')
    setRare(null)
    setHereStep(null)
    setDrawer(null)
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
  const onWalking = useCallback((moving: boolean) => {
    if (walkTimer.current) clearTimeout(walkTimer.current)
    setWalking(moving)
    if (moving) walkTimer.current = setTimeout(() => setWalking(false), 2600)
  }, [])

  const collect = useCallback((ids: string[]) => {
    setCollected((all) => {
      const next = [...new Set([...all, ...ids])]
      if (next.length === all.length) return all
      localStorage.setItem('hereafter.codex', JSON.stringify(next))
      return next
    })
  }, [])

  /** an example can be walked and read, never changed */
  const real = (fn: () => void) => fn

  const replaceView = (v: BranchView) => setViews((all) => all.map((x) => (x.branch.id === v.branch.id ? v : x)))
  const fail = (err: unknown, fallback: string) => setError(err instanceof Error ? err.message : fallback)

  const jump = useCallback(async (w: Which) => {
    if (!api || !active) return
    if (w === 'typical') return (setWhich('typical'), setRare(null))
    setBusy('rare')
    setError(null)
    try {
      setRare(await api.lives(active.branch.id, 'rare'))
      setWhich('rare')
    } catch (err) {
      fail(err, 'No rarer life could be found here.')
    } finally {
      setBusy(null)
    }
  }, [api, active])

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

  const commit = async (at: string, message: string, eventKey?: string) => {
    if (!api || !active) return
    setBusy('commit')
    setError(null)
    try {
      replaceView(await api.commit(active.branch.id, at, message, eventKey))
      did('commit')
      setCommitting(false)
    } catch (err) {
      fail(err, 'The commit did not take.')
    } finally {
      setBusy(null)
    }
  }

  const undo = useCallback(async () => {
    if (!api || !active || !active.branch.commits.length || active.branch.example) return
    setBusy('undo')
    setError(null)
    try {
      replaceView(await api.undo(active.branch.id))
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

  const pick = async (eventId: string) => {
    if (!api || !active) return
    setError(null)
    try {
      await api.carry(active.branch.id, eventId)
      await refresh()
      setSatchel(true)
    } catch (err) {
      fail(err, 'That moment could not be picked.')
    }
  }

  const offer = async (draft: OfferingDraft) => {
    if (!api) return
    setBusy('offer')
    try {
      let s = session
      if (!s) {
        s = await api.createPerson({ display_name: draft.display_name || undefined, birth_year: draft.birth_year, income: draft.income, net_worth: draft.net_worth, currency: draft.currency })
        saveSession(s)
        setToken(s.token || null)
        setSession(s)
      }
      setIngested(await api.ingest({
        person_id: s.person_id, display_name: draft.display_name || undefined, birth_year: draft.birth_year, text: draft.text || undefined,
        handles: draft.handles, files: draft.files, income: draft.income, net_worth: draft.net_worth, currency: draft.currency, live_source: draft.handles.github ? 'github' : draft.handles.site ? 'site' : undefined,
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
      if (typing() || e.metaKey || e.ctrlKey || e.altKey) return
      const k = e.key.toLowerCase()
      if (k === 'escape') {
        if (deciding) setDeciding(false)
        else if (drawer) setDrawer(null)
        else if (satchel) setSatchel(false)
        else if (reading) setReading(false)
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
      else if (k === 'k' && active.branch.status === 'open' && which === 'typical') (e.preventDefault(), real(() => setCommitting(true))())
      else if (k === 'u') void undo()
      else if (k === 'r') void jump(which === 'typical' ? 'rare' : 'typical')
      else if (k === 'b' && active.branch.status === 'open') real(() => (setAssuming(active), setDeciding(true)))()
    }
    // N opens the decision box on key-up, so the letter itself never lands in the field
    const onUp = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === 'n' && !typing() && !sheet && !e.metaKey && !e.ctrlKey && !e.altKey) (setAssuming(null), setDeciding(true))
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener('keyup', onUp)
    return () => (window.removeEventListener('keydown', onKey), window.removeEventListener('keyup', onUp))
  }, [active, siblings, sheet, drawer, satchel, reading, committing, deciding, which, switchTo, toggleMode, undo, jump, shown])

  const drawn = useMemo(() => (trunk ? withGuides(views, scenarios, trunk.now, trunk.state) : views), [views, scenarios, trunk])
  // Never everything at once. Stale paths, picked moments and other decisions' paths are there when the person goes looking.
  const sceneViews = useMemo(
    () => drawn
      .filter((v) => v.branch.scenario_id === shown?.id && (v.branch.status !== 'stale' || v.branch.id === activeId))
      .map((v) => ({ ...v, years: v.years.map((y) => ({ ...y, label: y.label === '' ? '' : stepDate(y.at, isByYear(v.years)) })) })),
    [drawn, shown, activeId],
  )
  const sceneScenarios = useMemo(() => scenarios.map((x) => ({ ...x, collapsed: x.id !== shown?.id })), [scenarios, shown])
  const sceneEvents = useMemo(() => (trunk?.events ?? []).filter((e) => (satchel || e.event_type !== 'goal') && (e.branch_id !== 'main' || belongsOnLine(e))), [trunk, satchel])

  // exactly one plain next-step line, gone once the person has done that thing twice
  const hint = justMerged ? 'Recorded on main. The other paths are closed.'
    : scenarios.length === 0 ? ((done.add ?? 0) < 2 ? 'Press N to add a decision' : null)
    : !shown ? ((done.pick ?? 0) < 2 ? 'Click a decision on main to open it' : null)
    : !active ? ((done.pick ?? 0) < 2 ? 'Pick a path to live it' : null)
    : advances < 3 ? ((done.walk ?? 0) < 6 ? 'Space to live it forward' : null)
    : active.branch.status === 'open' && (done.commit ?? 0) + (done.add ?? 0) < 2 && advances < 7 ? 'Commit adds a step here. Branch splits the path. Both can be undone — only Merge is permanent.'
    : active.branch.status === 'open' && (done.merge ?? 0) < 2 ? 'Merge makes this choice real. Or pick another path.' : null

  const rails = useRails()
  const { zones, free } = useZones([rails.key, hint, deciding, shown?.id, !!active, reading, !!drawer, satchel, view, mapOpen, asking0(scenario, active, skipped), scenarios.length, !!trunk])
  const onArrive = useCallback((eventId: string) => {
    const e = views.flatMap((v) => v.years).flatMap((y) => y.events).find((x) => x.id === eventId)
    if (typeof e?.payload.evidence_id === 'string') collect([e.payload.evidence_id])
  }, [views, collect])

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

  if (!api) return <div className="boot" />

  const firstRun = !session
  const showOffering = firstRun || sheet === 'offering' || ingested !== null
  const accent = active ? accentOf(active, scenarios) : theme.color.coralDeep
  const asking = active?.branch.status === 'open' ? (scenario?.questions ?? []).filter((q) => !q.answer && !skipped.includes(q.id) && (q.applies_to.length === 0 || q.applies_to.includes(active.branch.option_id ?? ''))) : []

  const viewProps: ViewProps | null = trunk && {
    now: trunk.now,
    events: sceneEvents,
    views: sceneViews,
    scenarios: sceneScenarios,
    activeId: active?.branch.id ?? null,
    hereStep,
    rare: which === 'rare' && rare ? rare.years : null,
    onSwitch: switchTo,
    onSeek: (id, step) => (id !== active?.branch.id && switchTo(id), setSeek({ step, nonce: Date.now() })),
    onOpenLog: () => setSheet('log'),
  }

  return (
    <div className={`app app--${view}`}>
      {/* two views of the same place; the HUD sits over whichever is on */}
      <div className="stage">
        {viewProps && World && islandAvailable && (view === 'island' || fading) && (
          <div className={`stage__layer ${view === 'island' ? 'is-on' : ''}`}>
            <Boundary onFail={() => setWorldFailed(true)}>
              <Suspense fallback={null}>
                <World {...viewProps} safeInsets={free} onArrive={onArrive} onWalking={onWalking} onFocusScenario={focusOn} />
              </Suspense>
            </Boundary>
          </div>
        )}
        {viewProps && (view === 'line' || fading) && (
          <div className={`stage__layer ${view === 'line' ? 'is-on' : ''}`}>
            <Line {...viewProps} zones={zones as Zone[]} free={free} onFocusDecision={focusOn} />
          </div>
        )}
      </div>

      <div className="hud" style={rails.style}>
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
            <p>{trunk?.person.display_name || ''}{trunk?.person.personality?.mbti ? ` · ${trunk.person.personality.mbti}` : ''}{api.offline ? ' · sample' : ''}</p>
          </header>
          <Decisions
            scenarios={scenarios}
            views={drawn}
            activeId={active?.branch.id ?? null}
            focusId={shown?.id ?? null}
            onFocus={(id) => focusOn(id)}
            onOpen={(id) => (switchTo(id), setRail(false))}
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
              <button type="button" className="h-link" onClick={() => setDrawer({ ids: collected, step: null, collected: true })}>Evidence</button>
              <button type="button" className="h-link" onClick={() => setSatchel((v) => !v)}>Picked</button>
              <button type="button" className="h-link" onClick={() => setSheet('log')}>Log</button>
              <button type="button" className="h-link" onClick={() => setSheet('inventory')}>Your data</button>
            </nav>
          </footer>
        </aside>

        <div className="hud__bottom">
          {hint && !deciding && !reading && <p className="h-hint" key={hint}>{hint}</p>}
          {!deciding && scenarios.length === 0 && session && session.person_id !== 'demo' && <a className="h-link h-hint__example" href="?person=demo">See an example</a>}
          {deciding && session ? (
            <NewDecision inside={assuming ? `${assuming.branch.label}, ${stepDate((assuming.years[hereStep ?? 0] ?? assuming.years[0])?.at ?? trunk?.now ?? '')}` : null} busy={busy === 'decide'} error={error} onCreate={(d, ps) => void createDecision(d, ps)} onClose={() => setDeciding(false)} />
          ) : active && !reading ? (
            <Narration
              api={api}
              view={active}
              which={which}
              rare={rare}
              seek={seek}
              committing={committing}
              walking={view === 'island' && walking}
              followsFigure={view === 'island'}
              busy={busy}
              onStep={setHereStep}
              onEvidence={(ids, step) => setDrawer({ ids, step })}
              onCollect={collect}
              onCommit={commit}
              onCancelCommit={() => setCommitting(false)}
              onReadAll={() => setReading(true)}
              onAdvance={() => (setAdvances((n) => n + 1), did('walk'))}
            />
          ) : null}
        </div>

        <div className={`hud__right ${rails.collapsed('right') ? 'is-collapsed' : ''}`}>
          {!rails.narrow && !rails.collapsed('right') && shown && <div {...rails.grip('right')} />}
          {shown && !reading && !rails.narrow && (
            <button type="button" className={rails.collapsed('right') ? 'h-tab h-tab--right' : 'h-fold h-fold--right'} onClick={() => rails.toggle('right')} title={rails.collapsed('right') ? 'Open this panel' : 'Fold this panel away'}>
              {rails.collapsed('right') ? `‹ ${shown.situation}` : '›'}
            </button>
          )}
          {shown && !reading && (
            <MergePanel
              scenario={shown}
              paths={shown.branch_ids.flatMap((id) => drawn.filter((v) => v.branch.id === id))}
              head={active && active.branch.scenario_id === shown.id ? active : null}
              which={which}
              busy={busy}
              error={error}
              notice={firmed ? 'Added to main. The paths it speaks to have firmed up.' : notice}
              research={research}
              question={asking[0] ?? null}
              onHead={switchTo}
              onMerge={(confirm) => void merge(confirm)}
              onEvidence={(ids) => setDrawer({ ids, step: null })}
              onCommit={real(() => setCommitting(true))}
              onUndo={() => void undo()}
              onCompare={() => setSheet('compare')}
              onWhich={(w) => void jump(w)}
              onInside={real(() => (setAssuming(active), setDeciding(true)))}
              onAnswer={(q, a2) => void answer(q, a2)}
              onSkip={(q) => setSkipped((all) => [...all, q.id])}
              onModel={() => setSheet('model')}
              onAssume={(ev) => { const at = (active?.years[hereStep ?? 0] ?? active?.years[0])?.at; if (at) void commit(at, `${ev.label} happens`, ev.key) }}
              step={hereStep}
              person={trunk?.person ?? null}
            />
          )}
        </div>
      </div>

      {satchel && <Satchel goals={goals} views={views} onClose={() => setSatchel(false)} />}

      {reading && active && (
        <div className="reader">
          <Page
            api={api}
            view={active}
            scenario={scenario}
            accent={accent}
            which={which}
            rare={rare}
            seek={seek}
            busy={busy}
            error={error}
            onHere={setHereStep}
            onEvidence={(ids, step) => setDrawer({ ids, step })}
            onCommit={commit}
            onPick={pick}
            onClose={() => setReading(false)}
          />
        </div>
      )}
      {drawer && (active || drawer.collected) && (
        <EvidenceDrawer api={api} branch={active?.branch ?? views[0]?.branch} ids={drawer.ids} step={drawer.step} collected={drawer.collected} onClose={() => setDrawer(null)} />
      )}

      {sheet === 'compare' && active && <Compare api={api} views={[active, ...siblings.filter((s) => s.branch.id !== active.branch.id)]} scenario={scenario} onSwitch={(id) => (switchTo(id), setSheet(null))} onClose={() => setSheet(null)} />}
      {sheet === 'model' && <ModelSheet api={api} onClose={() => setSheet(null)} />}
      {sheet === 'log' && trunk && <LogView events={trunk.events} reconciliation={trunk.reconciliation ?? []} onTell={() => setSheet('tell')} onClose={() => setSheet(null)} />}
      {sheet === 'inventory' && session && (
        <InventoryView api={api} personId={session.person_id} onChanged={() => void refresh()} onOffer={() => (setIngested(null), setSheet('offering'))} onErased={() => (clearSession(), setSession(null), setTrunk(null), setViews([]), setScenarios([]), setSheet(null), switchTo(null))} onClose={() => setSheet(null)} />
      )}
      {sheet === 'tell' && <Tell busy={busy === 'tell'} error={error} onSubmit={tell} onClose={() => setSheet(null)} />}
      {showOffering && (
        <Offering
          busy={busy === 'offer'}
          firstRun={firstRun}
          result={ingested}
          onSubmit={offer}
          onEnter={() => (setIngested(null), setSheet(null), void refresh())}
          onDemo={() => setSession({ person_id: 'demo', token: 'demo' })}
          onClose={() => setSheet(null)}
        />
      )}
    </div>
  )
}
