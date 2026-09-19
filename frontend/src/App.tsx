import { Component, lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState, type ComponentType, type ReactNode } from 'react'
import { clearSession, getApi, loadSession, saveSession, setToken, type Api } from './api'
import { ActionBar, Asking, BranchCard, Satchel } from './hud/Hud'
import { ModeSwitch, type Mode } from './hud/ModeSwitch'
import { Narration } from './hud/Narration'
import { QuestLog } from './hud/QuestLog'
import { useZones } from './hud/useZones'
import { withGuides } from './derive'
import { EXAMPLE_COPY, loadExamples, type Examples } from './examples'
import { accentOf, Line } from './line/Line'
import { EvidenceDrawer } from './page/EvidenceDrawer'
import { Page } from './page/Page'
import { theme } from './theme'
import type { BranchView, BranchYear, IngestResult, Insets, LifeEvent, LivesResponse, Question, Scenario, Session, TrunkResponse, Which, Zone } from './types'
import { Compare } from './views/Compare'
import { Composer } from './views/Composer'
import { InventoryView } from './views/InventoryView'
import { LogView } from './views/LogView'
import { MergeCeremony } from './views/MergeCeremony'
import { Offering, type OfferingDraft } from './views/Offering'
import { Tell } from './views/Tell'

type Sheet = 'offering' | 'composer' | 'compare' | 'merge' | 'log' | 'inventory' | 'tell' | null

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
const asking0 = (s: Scenario | null, a: BranchView | null, skipped: string[]) => (a?.branch.status === 'open' ? (s?.questions ?? []).filter((q) => !q.answer && !skipped.includes(q.id)).length : 0)
const typing = () => ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName ?? '')

export default function App() {
  const [api, setApi] = useState<Api | null>(null)
  const [session, setSession] = useState<Session | null>(loadSession)
  const [ownTrunk, setTrunk] = useState<TrunkResponse | null>(null)
  const [ownViews, setViews] = useState<BranchView[]>([])
  const [ownScenarios, setScenarios] = useState<Scenario[]>([])
  const [examples, setExamples] = useState<Examples | null>(null)
  const [examplesOpen, setExamplesOpen] = useState(false)
  const [examplesDismissed, setExamplesDismissed] = useState(() => localStorage.getItem('hereafter.examples') === 'dismissed')
  const [leaving, setLeaving] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const showedAlone = useRef(false)
  const [activeId, setActiveId] = useState<string | null>(params.get('branch'))
  const [which, setWhich] = useState<Which>('typical')
  const [rare, setRare] = useState<LivesResponse | null>(null)
  const [hereStep, setHereStep] = useState<number | null>(null)
  const [seek, setSeek] = useState<{ step: number; nonce: number } | null>(null)
  const [drawer, setDrawer] = useState<{ ids: string[]; step: BranchYear | null; collected?: boolean } | null>(null)
  const [sheet, setSheet] = useState<Sheet>((params.get('sheet') as Sheet) ?? null)
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
  const [mapOpen, setMapOpen] = useState(true)
  const [walking, setWalking] = useState(false)
  const walkTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const loaded = useRef(false)

  const islandAvailable = !!World && hasWebGL && !worldFailed
  const view: Mode = islandAvailable ? mode : 'line'

  useEffect(() => {
    void getApi().then(async (a) => {
      if (a.offline) return setApi(a)
      const made = await loadExamples(a)
      setExamples(made.examples)
      setApi(made.api)
    })
  }, [])

  // a borrowed life fills the scene until the person has a decision of their own; then it steps aside
  const ready = !session || ownTrunk !== null
  const alone = !!examples && ready && ownScenarios.length === 0
  const showExamples = !!examples && ready && (alone || leaving || examplesOpen)
  useEffect(() => {
    if (alone) showedAlone.current = true
    else if (showedAlone.current && ownScenarios.length > 0) {
      showedAlone.current = false
      setLeaving(true)
      const timer = setTimeout(() => setLeaving(false), 1800)
      return () => clearTimeout(timer)
    }
  }, [alone, ownScenarios.length])
  const views = useMemo(() => (showExamples ? [...ownViews, ...examples!.views] : ownViews), [showExamples, ownViews, examples])
  const scenarios = useMemo(() => (showExamples ? [...ownScenarios, ...examples!.scenarios] : ownScenarios), [showExamples, ownScenarios, examples])
  const trunk = useMemo<TrunkResponse | null>(() => {
    if (!examples || !showExamples) return ownTrunk
    if (!ownTrunk) return session ? null : { person: { id: 'example' }, now: new Date().toISOString(), events: examples.events, state: examples.state, agent_log: [] }
    // borrow a past too, unless the person's own main already reaches back a year or more
    const yearAgo = new Date(Date.now() - 365 * 86_400_000).toISOString().slice(0, 10)
    const reachesBack = ownTrunk.events.some((e) => e.branch_id === 'main' && e.date < yearAgo)
    return reachesBack ? ownTrunk : { ...ownTrunk, events: [...examples.events, ...ownTrunk.events].sort((a, b) => a.date.localeCompare(b.date)) }
  }, [ownTrunk, examples, showExamples, session])
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
  const goals = useMemo(() => (trunk?.events ?? []).filter((e) => e.event_type === 'goal'), [trunk])

  const switchTo = useCallback((id: string | null) => {
    setActiveId(id)
    setWhich('typical')
    setRare(null)
    setHereStep(null)
    setDrawer(null)
    setError(null)
    setFirmed(false)
    setCommitting(false)
    setNotice(null)
  }, [])

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
  const real = (fn: () => void) => () => (active?.branch.example ? setNotice(EXAMPLE_COPY) : fn())

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

  const commit = async (at: string, message: string) => {
    if (!api || !active) return
    setBusy('commit')
    setError(null)
    try {
      replaceView(await api.commit(active.branch.id, at, message))
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
    if (active?.branch.example) return setNotice(EXAMPLE_COPY)
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
      setSheet(null) // the ceremony lifts, and the view behind it shows the branch firming into main
      await refresh()
    } catch (err) {
      fail(err, 'The merge did not go through. Nothing was changed.')
    } finally {
      setBusy(null)
    }
  }

  const pick = async (eventId: string) => {
    if (!api || !active) return
    if (active.branch.example) return setNotice(EXAMPLE_COPY)
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
        s = await api.createPerson({ display_name: draft.display_name || undefined, birth_year: draft.birth_year })
        saveSession(s)
        setToken(s.token || null)
        setSession(s)
      }
      setIngested(await api.ingest({
        person_id: s.person_id, display_name: draft.display_name || undefined, birth_year: draft.birth_year, text: draft.text || undefined,
        handles: draft.handles, files: draft.files, live_source: draft.handles.github ? 'github' : draft.handles.site ? 'site' : undefined,
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
        if (drawer) setDrawer(null)
        else if (satchel) setSatchel(false)
        else if (reading) setReading(false)
        else if (committing) setCommitting(false)
        else if (!sheet && active) switchTo(null)
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
      else if (k === 'd' && active.branch.status === 'open') real(() => (setAssuming(active), setSheet('composer')))()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [active, siblings, sheet, drawer, satchel, reading, committing, which, switchTo, toggleMode, undo, jump])

  const { zones, free } = useZones([!!active, reading, !!drawer, satchel, view, mapOpen, asking0(scenario, active, skipped), scenarios.length, !!trunk])
  const drawn = useMemo(() => (trunk ? withGuides(views, scenarios, trunk.now, trunk.state) : views), [views, scenarios, trunk])
  const onArrive = useCallback((eventId: string) => {
    const e = views.flatMap((v) => v.years).flatMap((y) => y.events).find((x) => x.id === eventId)
    if (typeof e?.payload.evidence_id === 'string') collect([e.payload.evidence_id])
  }, [views, collect])

  if (!api) return <div className="boot" />

  const firstRun = !session
  const showOffering = firstRun || sheet === 'offering' || ingested !== null
  const empty = loaded.current && views.length === 0
  const accent = active ? accentOf(active, scenarios) : theme.color.coralDeep
  const asking = active?.branch.status === 'open' ? (scenario?.questions ?? []).filter((q) => !q.answer && !skipped.includes(q.id) && (q.applies_to.length === 0 || q.applies_to.includes(active.branch.option_id ?? ''))) : []

  const viewProps: ViewProps | null = trunk && {
    now: trunk.now,
    events: trunk.events,
    views: drawn,
    scenarios,
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
                <World {...viewProps} safeInsets={free} onArrive={onArrive} onWalking={onWalking} />
              </Suspense>
            </Boundary>
          </div>
        )}
        {viewProps && (view === 'line' || fading) && (
          <div className={`stage__layer ${view === 'line' ? 'is-on' : ''}`}>
            <Line {...viewProps} zones={zones as Zone[]} free={free} leavingExamples={leaving} />
          </div>
        )}
      </div>

      <header className="masthead">
        <h1>Hereafter</h1>
        <p className="caps">
          {trunk?.person.display_name || (session ? 'your life' : '')}
          {trunk?.person.personality?.mbti ? ` · ${trunk.person.personality.mbti}` : ''}
          {api.offline ? ' · offline sample' : ''}
        </p>
        <QuestLog scenarios={scenarios} views={views} activeScenarioId={scenario?.id ?? null} onOpen={switchTo} onNew={() => (setAssuming(null), setSheet('composer'))}
          examples={examples && ownScenarios.length > 0 && !examplesDismissed ? { open: examplesOpen, onToggle: () => (examplesOpen && active?.branch.example && switchTo(null), setExamplesOpen((v) => !v)), onDismiss: () => (localStorage.setItem('hereafter.examples', 'dismissed'), setExamplesDismissed(true), setExamplesOpen(false), active?.branch.example && switchTo(null)) } : null}
        />
      </header>

      {active && !reading && (
        <div className="hud-right">
          <BranchCard view={active} scenario={scenario} accent={accent} onEvidence={(ids) => setDrawer({ ids, step: null })} />
          {asking.slice(0, 1).map((q) => (
            <Asking key={q.id} question={q} busy={busy === `answer:${q.id}`} onAnswer={(a) => void answer(q, a)} onSkip={() => setSkipped((all) => [...all, q.id])} />
          ))}
          {firmed && <p className="hud-note">Heard, and added to main. The lines it speaks to have firmed up.</p>}
          {notice && <p className="hud-note hud-note--card">{notice} <button type="button" className="quiet" onClick={() => (setAssuming(null), setSheet('composer'))}>what are you deciding?</button></p>}
          {error && <p className="hud-note hud-note--error">{error}</p>}
        </div>
      )}

      <div className="hud-bottom">
        <div className="corner">
          {view === 'island' && viewProps && (
            <div className={`minimap ${mapOpen ? '' : 'minimap--folded'}`}>
              <button type="button" className="caps minimap__toggle" onClick={() => setMapOpen((v) => !v)}>the line {mapOpen ? '−' : '+'}</button>
              {mapOpen && <div className="minimap__frame"><Line {...viewProps} compact /></div>}
            </div>
          )}
          <div className="corner__row">
            {islandAvailable && <ModeSwitch mode={view} onToggle={toggleMode} />}
            <nav className="utility" aria-label="Hereafter">
              <button type="button" className="quiet" onClick={() => setDrawer({ ids: collected, step: active && hereStep !== null ? ((which === 'rare' && rare ? rare.years : active.years)[hereStep] ?? null) : null, collected: true })}>codex</button>
              <button type="button" className="quiet" onClick={() => setSatchel((v) => !v)}>satchel</button>
              <button type="button" className="quiet" onClick={() => setSheet('log')}>the log</button>
              <button type="button" className="quiet" onClick={() => setSheet('inventory')}>what Hereafter knows</button>
            </nav>
          </div>
        </div>

        {active && reading ? (
          <span />
        ) : active ? (
          <Narration
            api={api}
            view={active}
            which={which}
            rare={rare}
            seek={seek}
            committing={committing}
            walking={view === 'island' && walking}
            busy={busy}
            onStep={setHereStep}
            onEvidence={(ids, step) => setDrawer({ ids, step })}
            onCollect={collect}
            onCommit={commit}
            onCancelCommit={() => setCommitting(false)}
            onReadAll={() => setReading(true)}
          />
        ) : (
          <div className="narrate">
            <div className="narrate__box narrate__box--overview">
              {alone && examples ? (
                <>
                  <p className="narrate__when"><span className="caps">examples · a borrowed life</span></p>
                  <p className="narrate__text"><span>Nothing here is yours yet. These are three decisions from someone else’s life, small to large, to show how a branch is lived. Walk one, or bring your own.</span></p>
                  <p className="narrate__lives">
                    {examples.scenarios.map((sc) => {
                      const v = examples.views.find((x) => x.branch.id === sc.branch_ids[0])
                      return v ? <button key={sc.id} type="button" className="chip" style={{ ['--accent' as string]: theme.color.hairline }} onClick={() => switchTo(v.branch.id)}>{v.branch.label}</button> : null
                    })}
                    <button type="button" className="verb verb--primary" onClick={() => (setAssuming(null), setSheet('composer'))}>what are you deciding?</button>
                  </p>
                </>
              ) : empty || !newest ? (
                <>
                  <p className="narrate__text"><span>Nothing has branched yet. Bring Hereafter a decision of any size, and each thing you could do becomes a branch you can live through.</span></p>
                  <p className="narrate__hint"><button type="button" className="verb verb--primary" onClick={() => setSheet('composer')}>what are you deciding?</button></p>
                </>
              ) : (
                <>
                  <p className="narrate__when"><span className="caps">still turning over</span></p>
                  <p className="narrate__text narrate__text--quote"><span>“{newest.situation}”</span></p>
                  <p className="narrate__lives">
                    <span className="caps">live one</span>
                    {newest.branch_ids.flatMap((id) => views.filter((v) => v.branch.id === id)).map((v) => (
                      <button key={v.branch.id} type="button" className="chip" style={{ ['--accent' as string]: v.branch.status === 'open' ? accentOf(v, scenarios) : theme.color.ruin }} onClick={() => switchTo(v.branch.id)}>{v.branch.label}</button>
                    ))}
                  </p>
                </>
              )}
            </div>
          </div>
        )}

        <div className="corner corner--right">
          {active && !reading && (
            <ActionBar
              view={active}
              siblings={siblings}
              which={which}
              busy={busy}
              scenarios={scenarios}
              onSwitch={switchTo}
              onCompare={() => setSheet('compare')}
              onCommit={real(() => setCommitting(true))}
              onUndo={() => void undo()}
              onWhich={(w) => void jump(w)}
              onInside={real(() => (setAssuming(active), setSheet('composer')))}
              onMerge={real(() => (setError(null), setSheet('merge')))}
              onOverview={() => switchTo(null)}
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

      {sheet === 'composer' && session && (
        <Composer
          api={api}
          personId={session.person_id}
          assuming={assuming}
          views={views}
          onWatch={() => (switchTo(null), setSheet(null))}
          onMade={(s, made) => {
            setScenarios((all) => [...all.filter((x) => x.id !== s.id), s])
            setViews((all) => [...all.filter((v) => !made.some((m) => m.branch.id === v.branch.id)), ...made])
          }}
          onEnter={(id) => (switchTo(id), setSheet(null))}
          onClose={() => setSheet(null)}
        />
      )}
      {sheet === 'compare' && active && <Compare api={api} views={[active, ...siblings.filter((s) => s.branch.id !== active.branch.id)]} scenario={scenario} onSwitch={(id) => (switchTo(id), setSheet(null))} onClose={() => setSheet(null)} />}
      {sheet === 'merge' && active && <MergeCeremony view={active} siblings={siblings} busy={busy === 'merge'} error={error} onConfirm={merge} onClose={() => setSheet(null)} />}
      {sheet === 'log' && trunk && <LogView events={trunk.events} reconciliation={trunk.reconciliation ?? []} onTell={() => setSheet('tell')} onClose={() => setSheet(null)} />}
      {sheet === 'inventory' && session && (
        <InventoryView api={api} personId={session.person_id} onOffer={() => (setIngested(null), setSheet('offering'))} onErased={() => (clearSession(), setSession(null), setTrunk(null), setViews([]), setScenarios([]), setSheet(null), switchTo(null))} onClose={() => setSheet(null)} />
      )}
      {sheet === 'tell' && <Tell busy={busy === 'tell'} error={error} onSubmit={tell} onClose={() => setSheet(null)} />}
      {showOffering && (
        <Offering
          busy={busy === 'offer'}
          firstRun={firstRun}
          result={ingested}
          onSubmit={offer}
          onEnter={() => (setIngested(null), setSheet(views.length ? null : 'composer'), void refresh())}
          onDemo={() => setSession({ person_id: 'demo', token: 'demo' })}
          onClose={() => setSheet(null)}
        />
      )}
    </div>
  )
}
