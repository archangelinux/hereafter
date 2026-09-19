// A newcomer must not land in an empty world. Until someone has a decision of their own, the scene is
// filled with a few examples from a borrowed life: one small decision (tonight), one of about a month,
// one of years, plus some past on main so "now" sits mid-life. They come from the offline sample, are
// flagged `example`, can be walked and read like anything else, cannot be changed, and are never sent
// to the backend: every call about them is answered here.

import type { Api } from './api'
import { createFixture } from './fixtures/fixtureApi'
import type { BranchView, LifeEvent, Scenario, StateVector } from './types'

export const EXAMPLE_COPY = 'This one is only an example. Tell Hereafter what you are deciding.'
const EXAMPLE_SCENARIOS = ['sc-noor', 'sc-dry', 'sc-offer'] // small, medium, large

export interface Examples {
  scenarios: Scenario[]
  views: BranchView[]
  events: LifeEvent[]
  state: StateVector
}

export async function loadExamples(api: Api): Promise<{ examples: Examples; api: Api }> {
  const sample = createFixture()
  const [trunk, branches, scenarios] = await Promise.all([sample.trunk('demo'), sample.branches('demo'), sample.scenarios('demo')])
  const chosen = EXAMPLE_SCENARIOS.flatMap((id) => scenarios.filter((s) => s.id === id)).map((s) => ({ ...s, example: true }))
  const branchIds = new Set(chosen.flatMap((s) => s.branch_ids))
  const scenarioIds = new Set(chosen.map((s) => s.id))
  const examples: Examples = {
    scenarios: chosen,
    views: branches.branches.filter((v) => branchIds.has(v.branch.id)).map((v) => ({ ...v, branch: { ...v.branch, example: true } })),
    // the borrowed past: ordinary entries only, nothing that points at a branch not shown
    state: trunk.state,
    events: trunk.events.filter((e) => !['decision', 'goal'].includes(e.event_type)).map((e) => ({ ...e, example: true })),
  }
  const mine = (id: string) => branchIds.has(id)
  const refuse = () => Promise.reject(new Error(EXAMPLE_COPY))

  const wrapped: Api = {
    ...api,
    createScenario: (person, situation, options, extra) => (extra?.assuming_branch_id && mine(extra.assuming_branch_id) ? refuse() : api.createScenario(person, situation, options, extra)),
    answer: (scenarioId, answers) => (scenarioIds.has(scenarioId) ? refuse() : api.answer(scenarioId, answers)),
    research: (id) => (mine(id) ? sample.research(id) : api.research(id)),
    commit: (id, at, message) => (mine(id) ? refuse() : api.commit(id, at, message)),
    undo: (id, commitId) => (mine(id) ? refuse() : api.undo(id, commitId)),
    compare: (ids) => (ids.every(mine) ? sample.compare(ids) : api.compare(ids.filter((id) => !mine(id)))),
    chapter: (id, at, which) => (mine(id) ? sample.chapter(id, at, which) : api.chapter(id, at, which)),
    lives: (id, which) => (mine(id) ? sample.lives(id, which) : api.lives(id, which)),
    merge: (id, confirm) => (mine(id) ? refuse() : api.merge(id, confirm)),
    carry: (id, eventId) => (mine(id) ? refuse() : api.carry(id, eventId)),
    async evidence(query) {
      if (query.branchId) return mine(query.branchId) ? sample.evidence(query) : api.evidence(query)
      const borrowed = await sample.evidence({ ids: query.ids })
      const rest = (query.ids ?? []).filter((id) => !borrowed.some((e) => e.id === id))
      return rest.length ? [...borrowed, ...(await api.evidence({ ids: rest }).catch(() => []))] : borrowed
    },
  }
  return { examples, api: wrapped }
}
