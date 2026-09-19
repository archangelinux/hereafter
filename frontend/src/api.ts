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
  Offering,
  OptionDraft,
  Person,
  ResearchResponse,
  Scenario,
  ScenarioResponse,
  Session,
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
  createPerson(p: Pick<Person, 'display_name' | 'birth_year' | 'sex'>): Promise<Session>
  trunk(personId: string): Promise<TrunkResponse>
  branches(personId: string): Promise<BranchesResponse>
  scenarios(personId: string): Promise<Scenario[]>
  createScenario(personId: string, situation: string, options: OptionDraft[], extra?: { horizon?: Horizon; assuming_branch_id?: string }): Promise<ScenarioResponse>
  /** answers are appended to main, so nothing is asked twice; the affected branches firm up */
  answer(scenarioId: string, answers: Record<string, string>): Promise<ScenarioResponse>
  research(branchId: string): Promise<ResearchResponse>
  /** `at` is the date of the step the change is made at */
  commit(branchId: string, at: string, message: string): Promise<BranchView>
  undo(branchId: string, commitId?: string): Promise<BranchView>
  compare(ids: string[]): Promise<CompareResponse>
  chapter(branchId: string, at: string, which?: Which): Promise<Chapter>
  /** the most typical life is what a BranchView already shows; `rare` is the rarest coherent one */
  lives(branchId: string, which: Which): Promise<LivesResponse>
  evidence(query: { branchId?: string; ids?: string[] }): Promise<Evidence[]>
  ingest(offering: Offering): Promise<IngestResult>
  merge(branchId: string, confirm: string): Promise<MergeResponse>
  carry(branchId: string, eventId: string): Promise<CarryResponse>
  inventory(personId: string): Promise<Inventory>
  erase(personId: string): Promise<EraseResult>
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
    commit: (id, at, message) =>
      orLocally('POST /branches/commits', async () => normaliseView(await post<BranchView>(`/branches/${q(id)}/commits`, { year: +at.slice(0, 4), at, message }, 180_000)), notYet('A commit')),
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
    erase: (person_id) => orLocally('POST /erase', () => post('/erase', { person_id, confirm: 'erase' }, 180_000), notYet('Erasing')),
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
