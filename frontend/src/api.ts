// Client for docs/API.md (v1 + v2). Two safety nets, both silent apart from a console.info:
//  * if /api/health cannot be reached at boot (or ?offline is set), every call is served from
//    the in-memory fixture;
//  * if the live backend does not have a v2 route yet (404/405), that one call is answered
//    from what the client can derive locally, and the route is remembered in `api.missing`.

import { compareViews, normaliseChapter, normaliseScenario, normaliseView, normaliseYears, plainChapter } from './derive'
import { createFixture } from './fixtures/fixtureApi'
import type {
  BranchView,
  BranchesResponse,
  CarryResponse,
  Chapter,
  CompareResponse,
  EraseResult,
  Evidence,
  Health,
  Horizon,
  IngestResult,
  Inventory,
  LivesResponse,
  MergeResponse,
  ModelCard,
  Offering,
  OptionDraft,
  Person,
  ResearchResponse,
  Scenario,
  ScenarioResponse,
  Session,
  TicketPatch,
  TrunkResponse,
  Which,
} from './types'

const BASE = '/api'
const SESSION_KEY = 'hereafter.session'

export function loadSession(): Session | null {
  const asked = new URLSearchParams(location.search).get('person')
  if (asked === 'demo') return { person_id: 'demo', token: 'demo' }
  try {
    const raw = localStorage.getItem(SESSION_KEY)
    const s = raw ? (JSON.parse(raw) as Session) : null
    return s && (!asked || asked === s.person_id) ? s : null
  } catch {
    return null
  }
}
export const saveSession = (s: Session) => localStorage.setItem(SESSION_KEY, JSON.stringify(s))
export const clearSession = () => localStorage.removeItem(SESSION_KEY)

class HttpError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

let token: string | null = null
export const setToken = (t: string | null) => (token = t)

async function http<T>(path: string, init?: RequestInit & { timeoutMs?: number }): Promise<T> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), init?.timeoutMs ?? 30_000)
  const auth: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {}
  try {
    const res = await fetch(BASE + path, {
      ...init,
      signal: ctrl.signal,
      // multipart bodies must set their own boundary
      headers: init?.body instanceof FormData ? auth : { 'Content-Type': 'application/json', ...auth },
    })
    if (!res.ok) {
      let detail = res.statusText
      try {
        const body = await res.json()
        if (typeof body?.detail === 'string') detail = body.detail
      } catch {
        /* not json */
      }
      // The stored person no longer exists (erased, or a fresh database): start over quietly
      // at the Offering instead of leaving the world in a half-loaded state.
      if ((res.status === 401 || res.status === 403) && token && token !== 'demo' && localStorage.getItem(SESSION_KEY)) {
        clearSession()
        location.replace(location.pathname)
      }
      throw new HttpError(res.status, detail)
    }
    return (await res.json()) as T
  } finally {
    clearTimeout(timer)
  }
}

function offeringForm(o: Offering): FormData {
  const form = new FormData()
  form.set('person_id', o.person_id)
  if (o.display_name) form.set('display_name', o.display_name)
  if (o.birth_year) form.set('birth_year', String(o.birth_year))
  if (o.sex) form.set('sex', o.sex)
  if (o.text) form.set('text', o.text)
  if (o.handles && Object.keys(o.handles).length) form.set('handles', JSON.stringify(o.handles))
  if (o.links?.length) form.set('links', JSON.stringify(o.links))
  if (o.live_source) form.set('live_source', o.live_source)
  if (o.income !== undefined) form.set('income', String(o.income))
  if (o.net_worth !== undefined) form.set('net_worth', String(o.net_worth))
  if (o.currency) form.set('currency', o.currency)
  for (const file of o.files ?? []) form.append('files', file, file.name)
  return form
}

/** Reads are idempotent, so a passing server error is simply asked again, quietly. */
async function read<T>(path: string, tries = 3): Promise<T> {
  for (let attempt = 1; ; attempt++) {
    try {
      return await http<T>(path)
    } catch (err) {
      if (attempt >= tries || (err instanceof HttpError && err.status < 500)) throw err
      await new Promise((r) => setTimeout(r, 250 * attempt))
    }
  }
}

const post = <T>(path: string, body: unknown, timeoutMs?: number) => http<T>(path, { method: 'POST', body: JSON.stringify(body), timeoutMs })
const q = (v: string) => encodeURIComponent(v)

export interface Api {
  readonly offline: boolean
  /** v2 routes the live backend did not have; answered locally instead. */
  readonly missing: Set<string>
  createPerson(p: Pick<Person, 'display_name' | 'birth_year' | 'sex'> & { income?: number; net_worth?: number; currency?: string }): Promise<Session>
  trunk(personId: string): Promise<TrunkResponse>
  branches(personId: string): Promise<BranchesResponse>
  scenarios(personId: string): Promise<Scenario[]>
  createScenario(personId: string, situation: string, options: OptionDraft[], extra?: { horizon?: Horizon; assuming_branch_id?: string; scale?: 'big' | 'small' }): Promise<ScenarioResponse>
  /** an inline edit to a ticket */
  editTicket(scenario: Scenario, patch: TicketPatch): Promise<ScenarioResponse>
  /** answers are appended to main, so nothing is asked twice; the affected branches firm up */
  answer(scenarioId: string, answers: Record<string, string>): Promise<ScenarioResponse>
  research(branchId: string): Promise<ResearchResponse>
  /** `at` is the date of the step the change is made at */
  commit(branchId: string, at: string, message: string, eventKeys?: string[]): Promise<BranchView>
  undo(branchId: string, commitId?: string): Promise<BranchView>
  compare(ids: string[]): Promise<CompareResponse>
  chapter(branchId: string, at: string, which?: Which): Promise<Chapter>
  /** the most typical life is what a BranchView already shows; `rare` is the rarest coherent one */
  lives(branchId: string, which: Which): Promise<LivesResponse>
  evidence(query: { branchId?: string; ids?: string[] }): Promise<Evidence[]>
  ingest(offering: Offering): Promise<IngestResult>
  merge(branchId: string, confirm: string): Promise<MergeResponse>
  carry(branchId: string, eventId: string): Promise<CarryResponse>
  /** how the numbers are made, in plain words */
  model(): Promise<ModelCard>
  inventory(personId: string): Promise<Inventory>
  erase(personId: string): Promise<EraseResult>
  /** forget one offering: everything on main that came from it goes */
  forget(personId: string, origin: string): Promise<{ origin: string; removed: number }>
}

function liveApi(): Api {
  const missing = new Set<string>()
  let lastViews: BranchView[] = []
  let lastTrunk: TrunkResponse | null = null

  /** Try the route; if the backend has no such route, note it and answer locally. */
  async function orLocally<T>(route: string, call: () => Promise<T>, local: () => T | Promise<T>): Promise<T> {
    if (missing.has(route)) return local()
    try {
      return await call()
    } catch (err) {
      if (err instanceof HttpError && (err.status === 404 || err.status === 405)) {
        const known = lastViews.length > 0 || route === '/people'
        if (known) {
          missing.add(route)
          console.info(`[hereafter] the backend has no ${route} yet; answering locally`)
          return local()
        }
      }
      throw err
    }
  }

  const view = (id: string) => {
    const v = lastViews.find((b) => b.branch.id === id)
    if (!v) throw new Error('No such branch.')
    return v
  }
  const notYet = (what: string) => () => {
    throw new Error(`${what} needs the newer backend, which is not running yet.`)
  }

  return {
    offline: false,
    missing,
    createPerson: (p) =>
      orLocally('/people', () => post<Session>('/people', p), () => ({ person_id: `p-${crypto.randomUUID().slice(0, 12)}`, token: '' })),
    async trunk(id) {
      lastTrunk = await read<TrunkResponse>(`/trunk?person_id=${q(id)}`)
      return lastTrunk
    },
    async branches(id) {
      const res = await read<BranchesResponse>(`/branches?person_id=${q(id)}`)
      lastViews = res.branches.map(normaliseView)
      return { ...res, branches: lastViews }
    },
    scenarios: (id) =>
      orLocally(
        '/scenarios',
        async () => (await read<{ scenarios: Scenario[] }>(`/scenarios?person_id=${q(id)}`)).scenarios.map(normaliseScenario),
        () => impliedScenarios(id, lastViews),
      ),
    createScenario: (person_id, situation, options, extra) =>
      orLocally(
        'POST /scenarios',
        async () => {
          const res = await post<ScenarioResponse>('/scenarios', { person_id, situation, options, ...extra }, 240_000)
          const branches = res.branches.map(normaliseView)
          lastViews = [...lastViews.filter((v) => !branches.some((b) => b.branch.id === v.branch.id)), ...branches]
          return { scenario: normaliseScenario(res.scenario), branches }
        },
        async () => {
          // the older backend can still simulate one ad-hoc branch per option
          const branches: BranchView[] = []
          for (const o of options) {
            const made = await post<BranchView>('/simulate', { person_id, label: o.title, assumption: {}, precondition: o.deadline ? `deadline: ${o.deadline}` : undefined }, 120_000)
            branches.push(normaliseView(made))
          }
          lastViews = [...lastViews, ...branches]
          return { scenario: impliedScenarios(person_id, branches, situation)[0], branches }
        },
      ),
    async editTicket(scenario, patch) {
      // POST /scenarios/{id}/edit: renames, decide-by dates, big/small and added paths all live on the backend
      const ids = scenario.options.map((o) => o.id)
      const body = {
        ...(patch.situation ? { situation: patch.situation } : {}),
        ...(patch.scale ? { scale: patch.scale } : {}),
        ...(patch.rename ? { rename: { [patch.rename.option_id]: patch.rename.title } } : {}),
        ...(patch.decide_by !== undefined ? { deadline: Object.fromEntries(ids.map((id) => [id, patch.decide_by])) } : {}),
        ...(patch.add_option ? { add: [{ title: patch.add_option }] } : {}),
      }
      const res = await post<ScenarioResponse>(`/scenarios/${q(scenario.id)}/edit`, body, 240_000)
      const branches = res.branches.map(normaliseView)
      lastViews = [...lastViews.filter((v) => !branches.some((x) => x.branch.id === v.branch.id)), ...branches]
      return { scenario: normaliseScenario(res.scenario), branches }
    },
    answer: (scenarioId, answers) =>
      orLocally(
        'POST /scenarios/answers',
        async () => {
          const res = await post<ScenarioResponse>(`/scenarios/${q(scenarioId)}/answers`, { answers }, 240_000)
          return { scenario: normaliseScenario(res.scenario), branches: res.branches.map(normaliseView) }
        },
        notYet('Answering'),
      ),
    research: (id) => orLocally('/research', () => read(`/research?branch_id=${q(id)}`), () => ({ branch_id: id, research: 'none' as const, steps: [] })),
    commit: (id, at, message, event_keys) =>
      post<BranchView>(`/branches/${q(id)}/commits`, { year: +at.slice(0, 4), at, message, ...(event_keys?.length ? { event_keys } : {}) }, 180_000).then(normaliseView),
    undo: (id, commit_id) =>
      orLocally('POST /branches/undo', async () => normaliseView(await post<BranchView>(`/branches/${q(id)}/undo`, commit_id ? { commit_id } : {}, 120_000)), notYet('Undo')),
    compare: (ids) =>
      orLocally(
        '/compare',
        () => read(`/compare?${ids.map((id, i) => `${'abc'[i]}=${q(id)}`).join('&')}`),
        () => compareViews(ids.map(view)),
      ),
    chapter: (id, at, which = 'typical') =>
      orLocally(
        '/chapters',
        async () => normaliseChapter(await read<Chapter>(`/chapters?branch_id=${q(id)}&at=${q(at)}&year=${at.slice(0, 4)}${which === 'rare' ? '&which=rare' : ''}`), view(id).years),
        () => plainChapter(view(id), at),
      ),
    lives: (id, which) =>
      orLocally(
        '/lives',
        async () => {
          const res = await read<LivesResponse>(`/lives?branch_id=${q(id)}&which=${which}`)
          return { ...res, years: normaliseYears(res.years) }
        },
        () => {
          if (which === 'rare') throw new Error('The rarest life needs the newer backend, which is not running yet.')
          return { which, rarity_words: '', years: view(id).years }
        },
      ),
    evidence: ({ branchId, ids }) =>
      orLocally(
        '/evidence',
        async () => (await read<{ evidence: Evidence[] }>(`/evidence?${ids ? `ids=${q(ids.join(','))}` : `branch_id=${q(branchId ?? '')}`}`)).evidence,
        () => [],
      ),
    ingest: (offering) => http('/ingest', { method: 'POST', body: offeringForm(offering), timeoutMs: 240_000 }),
    merge: (branch_id, confirm) => post('/merge', { branch_id, confirm }),
    carry: (branch_id, event_id) => post('/carry', { branch_id, event_id }),
    model: () => orLocally('/model', () => read<ModelCard>('/model'), () => LOCAL_MODEL),
    inventory: (id) =>
      orLocally('/inventory', () => read(`/inventory?person_id=${q(id)}`), () => {
        const bySource = new Map<string, TrunkResponse['events']>()
        for (const e of lastTrunk?.events ?? []) bySource.set(e.source, [...(bySource.get(e.source) ?? []), e])
        return {
          sources: [...bySource].map(([source, events]) => ({ source, count: events.length, newest: events[events.length - 1].date, examples: events.slice(-3) })),
          handles: [],
          cached_pages: 0,
          sent_to_llm: ['The text of pages you pointed to', 'Your own words', 'Chat excerpts with every other name replaced', 'Simulated event logs, to be written up'],
          stored_nowhere: ['Raw chat exports', 'Uploaded files', "Other people's names or messages"],
        }
      }),
    forget: (person_id, origin) => orLocally('POST /forget', () => post('/forget', { person_id, origin }, 60_000), notYet('Forgetting one offering')),
    erase: (person_id) => orLocally('POST /erase', () => post('/erase', { person_id, confirm: 'erase' }, 180_000), notYet('Erasing')),
  }
}

/** What an edit does to a ticket; used by the offline sample. */
/** Shown when the backend has no model card yet, and offline. It states only what the simulator does. */
export const LOCAL_MODEL: ModelCard = {
  version: 'described by the app',
  summary: 'Each path is lived a thousand times. A percentage is the share of those thousand simulated lives in which the event happened before the path’s horizon.',
  steps: [
    { title: 'A base rate', text: 'Each possible event starts from a base rate: a published figure found by reading the web (with its source and the group it describes), a figure from the life-course tables, or, when nothing is published, an estimate drawn from a stated range.' },
    { title: 'Your personality', text: 'If Hereafter has a personality estimate for you, each trait can shift the odds a little. Published effects are used where they exist; otherwise a small assumed effect, labelled as assumed. Low-confidence estimates shift less.' },
    { title: 'Dependencies', text: 'Some events make others more or less likely (you cannot be home by eleven if you stayed past one). These multiply the odds.' },
    { title: 'Commit and branch', text: 'While living a path you can commit (tick what you would have happen, or say what you would do; the path stays one line and everything after it is simulated again, with what you pinned held true) or branch (split the path into two or more paths). Both can be undone. Only a merge, which records a choice on main, is permanent.' },
    { title: 'A thousand lives', text: 'The path is simulated a thousand times with those odds. The percentage shown is how many of the thousand contain the event. The story you read follows the most typical of them.' },
  ],
  constants: [{ name: '1,000', value: '', meaning: 'simulated lives per path' }],
  limits: ['Estimates are estimates: an event with no published rate is only placed in a range.', 'Published rates describe groups, not you.', 'The model never sees the future; it cannot rule anything in or out.'],
}

export function applyPatch(s: Scenario, patch: TicketPatch): Scenario {
  return {
    ...s,
    situation: patch.situation ?? s.situation,
    scale: patch.scale ?? s.scale,
    options: s.options.map((o) => ({
      ...o,
      title: patch.rename?.option_id === o.id ? patch.rename.title : o.title,
      deadline: patch.decide_by !== undefined ? patch.decide_by : o.deadline,
    })),
  }
}

/** An older backend has branches but no scenarios: group the branches by the day they forked. */
function impliedScenarios(personId: string, views: BranchView[], situation?: string): Scenario[] {
  const groups = new Map<string, BranchView[]>()
  for (const v of views) groups.set(v.branch.forked_at, [...(groups.get(v.branch.forked_at) ?? []), v])
  return [...groups].map(([forked, vs]) => {
    const decided = vs.find((v) => v.branch.status === 'merged')
    return {
      id: `implied-${forked}`,
      person_id: personId,
      situation: situation ?? 'A decision you brought to Hereafter.',
      created_at: forked,
      options: vs.map((v) => ({ id: v.branch.id, title: v.branch.label, details: '', deadline: v.branch.precondition?.match(/\d{4}-\d{2}-\d{2}/)?.[0] ?? null })),
      branch_ids: vs.map((v) => v.branch.id),
      status: decided ? ('decided' as const) : ('open' as const),
      decided_branch_id: decided?.branch.id ?? null,
      horizon: { unit: 'years' as const, count: Math.max(...vs.map((v) => v.years.length), 1) },
      questions: [],
      assuming_branch_id: null,
    }
  })
}

// ---------------------------------------------------------------- boot

let chosen: Promise<Api> | null = null

export function getApi(): Promise<Api> {
  if (!chosen) {
    // ?offline forces the fixture: a stage fallback that needs no network at all
    const forced = new URLSearchParams(location.search).has('offline')
    chosen = (forced ? Promise.reject(new Error('offline')) : http<Health>('/health', { timeoutMs: 1500 }))
      .then((h) => {
        if (!h?.ok) throw new Error('unhealthy')
        return liveApi()
      })
      .catch(() => {
        console.info('[hereafter] backend unreachable; using the offline sample')
        return createFixture()
      })
  }
  return chosen
}
