// The offline sandbox, behaving like the backend: scenarios branch, commits re-draw and undo,
// merges are permanent, research plays back over a few seconds. It holds no sample data (see demo.ts).

import { applyPatch, LOCAL_MODEL, type Api } from '../api'
import { compareViews, plainChapter } from '../derive'
import type { BranchView, Commit, LifeEvent, Scenario } from '../types'
import { demoBranches, demoChapters, demoEvidence, demoInventory, demoPerson, demoRare, demoRareChapters, demoResearch, demoScenarios, demoState, demoTrunkEvents, THIS_YEAR } from './demo'

const RESEARCH_STEP_MS = 1400

export function createFixture(): Api {
  // ?offline&empty: the same person before any decision, to see the empty state
  const blank = new URLSearchParams(location.search).has('empty')
  const events: LifeEvent[] = structuredClone(demoTrunkEvents).filter((e) => !blank || e.event_type !== 'decision')
  const views: BranchView[] = blank ? [] : structuredClone(demoBranches)
  const scenarios: Scenario[] = blank ? [] : structuredClone(demoScenarios)
  const undoStack = new Map<string, BranchView[]>()
  const researchStarted = new Map<string, number>()
  const chapterAskedAt = new Map<string, number>()
  const formingYears = new Map<string, BranchView['years']>()
  const FORM_MS = 3200
  const today = () => new Date().toISOString().slice(0, 10)
  let counter = 0

  const find = (id: string) => {
    const v = views.find((b) => b.branch.id === id)
    if (!v) throw new Error('No such branch.')
    return v
  }

  const told = (text: string, event_type: string, payload: Record<string, unknown> = {}): LifeEvent => ({
    id: `main-told-${++counter}`, person_id: demoPerson.id, source: 'told', branch_id: 'main', date: today(), domain: 'career', event_type, payload, confidence: 1, text, origin: 'your words',
  })

  /** Research that finishes re-simulates the branch: the revision bumps once. */
  function settleResearch(v: BranchView) {
    const started = researchStarted.get(v.branch.id)
    if (started === undefined) return
    const held = formingYears.get(v.branch.id)
    if (held && Date.now() - started > FORM_MS) {
      v.years = held
      v.branch.forming = false
      v.branch.revision += 1
      formingYears.delete(v.branch.id)
    }
    const steps = demoResearch(v.branch.label)
    const shown = Math.floor((Date.now() - started) / RESEARCH_STEP_MS) + 1
    if (shown >= steps.length && v.branch.research !== 'done') {
      v.branch.research = 'done'
      v.branch.revision += 1
    } else if (shown < steps.length) v.branch.research = 'running'
  }

  return {
    offline: true,
    missing: new Set(),
    async createPerson() {
      return { person_id: demoPerson.id, token: 'offline' }
    },
    async trunk() {
      return { person: demoPerson, now: new Date().toISOString(), events: [...events], state: demoState, agent_log: [], reconciliation: [] }
    },
    async branches() {
      for (const v of views) {
        settleResearch(v)
        const deadline = v.branch.precondition?.match(/(\d{4}-\d{2}-\d{2})/)?.[1]
        if (v.branch.status === 'open' && deadline && today() > deadline) v.branch.status = 'stale'
      }
      return { now: new Date().toISOString(), branches: structuredClone(views) }
    },
    async scenarios() {
      return structuredClone(scenarios)
    },
    async createScenario(person_id, situation, options, extra) {
      const horizon = extra?.horizon
      const id = `sc-local-${++counter}`
      const made: BranchView[] = options.map((o, i) => {
        // a long horizon borrows the long sample lives; anything else borrows tonight's
        const pool = views.filter((v) => v.branch.scenario_id === (horizon?.unit === 'years' || extra?.scale === 'big' ? 'sc-job' : 'sc-friday'))
        const template = pool[i % pool.length]
        if (!template) throw new Error('The offline sandbox has no sample data to imagine a decision from. Start the backend.')
        const bid = `br-local-${++counter}`
        const copy: BranchView = structuredClone(template)
        copy.branch = {
          ...copy.branch, id: bid, label: o.title, scenario_id: id, option_id: `op-${bid}`, status: 'open', forked_at: today(), commits: [],
          precondition: o.deadline ? `deadline: ${o.deadline}` : null, carried_event_id: null, research: 'pending', revision: 1,
        }
        copy.years = copy.years.map((y) => ({ ...y, events: y.events.map((e) => ({ ...e, id: e.id.replace(template.branch.id, bid), branch_id: bid })) }))
        researchStarted.set(bid, Date.now() + i * 900)
        // returned at once as a placeholder; its steps land a few seconds later
        formingYears.set(bid, copy.years)
        copy.years = []
        copy.branch.forming = true
        return copy
      })
      // an earlier open scenario steps aside only in the sample, to keep the line readable
      views.push(...made)
      const scenario: Scenario = {
        id, person_id, situation, created_at: today(), status: 'open', decided_branch_id: null,
        horizon: horizon ?? { unit: 'weeks', count: 12 },
        questions: [],
        assuming_branch_id: extra?.assuming_branch_id ?? null,
        scale: extra?.scale ?? (horizon?.unit === 'years' ? 'big' : 'small'),
        options: options.map((o, i) => ({ id: made[i].branch.option_id!, title: o.title, details: o.details, deadline: o.deadline ?? null })),
        branch_ids: made.map((m) => m.branch.id),
      }
      scenarios.push(scenario)
      return structuredClone({ scenario, branches: made })
    },
    async editTicket(scenario, patch) {
      const i = scenarios.findIndex((x) => x.id === scenario.id)
      if (i < 0) throw new Error('No such ticket.')
      scenarios[i] = applyPatch(scenarios[i], patch)
      if (patch.rename) for (const v of views) if (v.branch.option_id === patch.rename.option_id) v.branch.label = patch.rename.title
      if (patch.add_option) {
        const more = await this.createScenario(scenario.person_id, scenarios[i].situation, [{ title: patch.add_option, details: '' }], { horizon: scenarios[i].horizon, scale: scenarios[i].scale })
        const added = more.branches[0]
        const stray = scenarios.findIndex((x) => x.id === more.scenario.id)
        scenarios.splice(stray, 1)
        const mine = views.find((v) => v.branch.id === added.branch.id)!
        mine.branch.scenario_id = scenario.id
        scenarios[i] = { ...scenarios[i], options: [...scenarios[i].options, more.scenario.options[0]], branch_ids: [...scenarios[i].branch_ids, added.branch.id] }
      }
      return structuredClone({ scenario: scenarios[i], branches: views.filter((v) => v.branch.scenario_id === scenario.id) })
    },
    async answer(scenarioId, answers) {
      const scenario = scenarios.find((x) => x.id === scenarioId)
      if (!scenario) throw new Error('No such decision.')
      const touched = new Set<string>()
      for (const question of scenario.questions) {
        const given = answers[question.id]?.trim()
        if (!given || question.answer) continue
        question.answer = given
        events.push(told(`${question.text} ${given}`, 'answer'))
        const optionIds = question.applies_to.length ? question.applies_to : scenario.options.map((o) => o.id)
        optionIds.forEach((id) => touched.add(id))
      }
      // more in, clearer futures: the branches an answer speaks to firm up
      const changed = views.filter((v) => v.branch.scenario_id === scenarioId && touched.has(v.branch.option_id ?? ''))
      for (const v of changed) {
        v.branch.revision += 1
        v.years = v.years.map((y) => ({ ...y, solidity: Math.min(0.98, 0.6 + (y.solidity - 0.6) * 2.4 + 0.12) }))
      }
      return structuredClone({ scenario, branches: views.filter((v) => v.branch.scenario_id === scenarioId) })
    },
    async research(branchId) {
      const v = find(branchId)
      const started = researchStarted.get(branchId)
      if (started === undefined) return { branch_id: branchId, research: v.branch.research, steps: v.branch.research === 'done' ? demoResearch(v.branch.label) : [] }
      settleResearch(v)
      const steps = demoResearch(v.branch.label)
      const shown = Math.max(0, Math.min(steps.length, Math.floor((Date.now() - started) / RESEARCH_STEP_MS) + 1))
      return { branch_id: branchId, research: v.branch.research, steps: steps.slice(0, shown) }
    },
    async commit(branchId, at, message, eventKeys) {
      const year = +at.slice(0, 4)
      const v = find(branchId)
      if (v.branch.status !== 'open') throw new Error('Only an open branch can take a commit.')
      undoStack.set(branchId, [...(undoStack.get(branchId) ?? []), structuredClone(v)])
      const pinned = eventKeys ?? []
      const said = pinned.map((k) => v.branch.model.events.find((e) => e.key === k)?.label ?? k)
      const words = said.length > 1 ? `${said.slice(0, -1).join(', ')} and ${said[said.length - 1]} happen` : said.length === 1 ? `${said[0]} happens` : message
      const commit: Commit = { id: `cm-${++counter}`, branch_id: branchId, year, at, message: words, patch: { event_keys: pinned }, created_at: new Date().toISOString() }
      v.branch.commits = [...v.branch.commits, commit]
      v.branch.revision += 1
      v.branch.model = { events: v.branch.model.events.map((e, n) => (pinned.includes(e.key) ? { ...e, probability: 1, words: 'certain: you committed it' } : { ...e, probability: e.probability === undefined ? undefined : Math.min(0.97, Math.max(0.03, e.probability + (n % 2 ? 0.08 : -0.06))) })).sort((a, b) => (b.probability ?? 0) - (a.probability ?? 0)) }
      // what follows a commit is redrawn: later events slip a step, and the thousand lives agree a little less
      const from = Math.max(0, v.years.findIndex((y) => y.at >= at))
      v.years = v.years.map((y, i) => (i <= from ? y : { ...y, solidity: Math.max(0.6, y.solidity * 0.94) }))
      for (let i = Math.min(v.years.length - 1, from + 6); i > from + 1; i--) {
        if (v.years[i - 1].events.length && !v.years[i].events.length) {
          v.years[i].events = v.years[i - 1].events.map((e) => ({ ...e, date: v.years[i].at }))
          v.years[i - 1].events = []
        }
      }
      return structuredClone(v)
    },
    async undo(branchId) {
      const stack = undoStack.get(branchId) ?? []
      const before = stack.pop()
      if (!before) throw new Error('There is nothing to undo on this branch.')
      const i = views.findIndex((b) => b.branch.id === branchId)
      before.branch.revision = views[i].branch.revision + 1
      views[i] = before
      return structuredClone(before)
    },
    async compare(ids) {
      return compareViews(ids.map(find))
    },
    async chapter(branchId, at, which = 'typical') {
      const v = find(branchId)
      const template = templateOf(v)
      const rare = which === 'rare'
      const years = rare ? (demoRare[template]?.years ?? v.years) : v.years
      const shelf = rare ? demoRareChapters : demoChapters
      // after a commit the sample prose no longer fits; the structured skeleton is shown instead
      const written = v.branch.commits.length === 0 ? shelf.find((c) => c.branch_id === template && at >= c.from_at.slice(0, 10) && at <= c.to_at) : undefined
      const plain = plainChapter(v, at, years)
      if (!written) return plain
      // prose arrives late on purpose, so the plain → written swap is visible offline too
      const key = `${branchId}:${which}:${written.from_at}:${v.branch.revision}`
      const first = chapterAskedAt.get(key) ?? Date.now()
      chapterAskedAt.set(key, first)
      const ready = Date.now() - first > 1600
      const base = { ...written, from_at: plain.from_at, to_at: plain.to_at, branch_id: branchId, revision: v.branch.revision }
      return ready ? base : { ...plain, title: written.title, status: 'writing' }
    },
    async lives(branchId, which) {
      const v = find(branchId)
      if (which === 'typical') return { which, rarity_words: 'The most typical of the thousand simulated lives.', years: v.years }
      const rare = demoRare[templateOf(v)]
      if (!rare) throw new Error('No rarer life was found on this branch.')
      return { which, rarity_words: rare.rarity_words, years: structuredClone(rare.years) }
    },
    async evidence({ branchId, ids }) {
      if (ids) return demoEvidence.filter((e) => ids.includes(e.id))
      const template = branchId ? templateOf(find(branchId)) : null
      return demoEvidence.filter((e) => e.branch_id === null || e.branch_id === template)
    },
    async ingest(o) {
      const added: LifeEvent[] = []
      const inputs: Awaited<ReturnType<Api['ingest']>>['inputs'] = []
      if (o.text) {
        const e = told(o.text, 'note')
        events.push(e)
        added.push(e)
        inputs.push({ name: 'your words', kind: 'freeform', outcome: 'Heard, and kept.' })
      }
      for (const source of Object.keys(o.handles ?? {})) inputs.push({ name: source, kind: 'handles', outcome: 'Set aside; nothing can be read while Hereafter is offline.' })
      for (const file of o.files ?? []) inputs.push({ name: file.name, kind: 'unknown', outcome: 'Set aside until Hereafter is online.' })
      return { person_id: o.person_id, events_added: added, inputs, personality: demoPerson.personality ?? null, reconciliation: [] }
    },
    async merge(branchId, confirm) {
      const v = find(branchId)
      if (v.branch.status !== 'open') throw new Error('Only an open branch can be merged.')
      if (confirm !== v.branch.label) throw new Error('The name does not match.')
      v.branch.status = 'merged'
      const siblings = views.filter((o) => o !== v && o.branch.status === 'open' && o.branch.scenario_id === v.branch.scenario_id)
      siblings.forEach((o) => (o.branch.status = 'faded'))
      const scenario = scenarios.find((s) => s.id === v.branch.scenario_id)
      if (scenario) Object.assign(scenario, { status: 'decided', decided_branch_id: branchId })
      const e = told(`Chose: ${v.branch.label}`, 'decision', { from_branch: branchId })
      events.push(e)
      return { merged: v.branch, faded: siblings.map((o) => o.branch), told_event: e }
    },
    async carry(branchId, eventId) {
      const v = find(branchId)
      if (v.branch.status === 'open' || v.branch.status === 'merged') throw new Error('Only a closed branch can give something up.')
      if (v.branch.carried_event_id) throw new Error('One moment has already been picked from this branch.')
      const src = v.years.flatMap((y) => y.events).find((e) => e.id === eventId)
      if (!src) throw new Error('No such moment on this branch.')
      v.branch.carried_event_id = eventId
      const goal: LifeEvent = { ...told(src.text, 'goal', { target_date: src.date, from_branch: branchId, carried_event_id: eventId }), domain: src.domain }
      events.push(goal)
      return { goal_event: goal, branch: v.branch }
    },
    async model() {
      return LOCAL_MODEL
    },
    async inventory() {
      const bySource = new Map<string, LifeEvent[]>()
      for (const e of events) bySource.set(e.source, [...(bySource.get(e.source) ?? []), e])
      return {
        sources: [...bySource].map(([source, es]) => ({ source, count: es.length, newest: es[es.length - 1].date, examples: es.slice(-3) })),
        ...demoInventory,
        offerings: [...new Set(events.map((e) => e.origin).filter((o): o is string => !!o))].map((origin) => {
          const from = events.filter((e) => e.origin === origin)
          return { origin, count: from.length, newest: from[from.length - 1].date, source: from[0].source }
        }),
      }
    },
    async forget(_person, origin) {
      const before = events.length
      for (let i = events.length - 1; i >= 0; i--) if (events[i].origin === origin) events.splice(i, 1)
      return { origin, removed: before - events.length }
    },
    async erase() {
      const erased = { events: events.length, evidence: demoEvidence.length, branches: views.length, cached_pages: demoInventory.cached_pages }
      events.length = 0
      views.length = 0
      scenarios.length = 0
      return { erased }
    },
  }

  /** Branches made offline are copies of a sample branch; their prose and evidence come from it. */
  function templateOf(v: BranchView): string {
    if (!v.branch.id.startsWith('br-local-')) return v.branch.id
    const first = v.years[0]?.events[0]?.text ?? ''
    return demoBranches.find((d) => d.years[0]?.events[0]?.text === first)?.branch.id ?? v.branch.id
  }
}

export { THIS_YEAR }
