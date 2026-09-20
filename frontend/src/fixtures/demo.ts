// The offline sandbox holds NO sample data.
//
// `?offline` opens it: an empty person and nothing to decide. Nothing here is ever loaded for a real
// person, and when the real backend cannot be reached the app says so instead of falling back to this.
// To build a sample again, fill these exports (types are in ../types); fixtureApi.ts plays them back.

import type { BranchView, BranchYear, Chapter, Evidence, LifeEvent, Person, ResearchStep, Scenario, StateVector } from '../types'

export const THIS_YEAR = new Date().getFullYear()

export const demoPerson: Person = { id: 'offline', display_name: 'Offline', birth_year: null, sex: null, personality: null }

export const demoState: StateVector = {
  year: THIS_YEAR, age: 0, city: '', education: '', field: '', employment: 'employed',
  income_band: 'middle', relationship_status: 'single', housing: 'renting', activity_proxy: 0, children: 0, alive: true,
}

export const demoTrunkEvents: LifeEvent[] = []
export const demoBranches: BranchView[] = []
export const demoScenarios: Scenario[] = []
export const demoRare: Record<string, { rarity_words: string; years: BranchYear[] }> = {}
export const demoEvidence: Evidence[] = []
export const demoChapters: Chapter[] = []
export const demoRareChapters: Chapter[] = []

export const demoResearch = (_branchLabel: string): ResearchStep[] => []

export const demoInventory = {
  handles: [] as { source: string; handle: string }[],
  cached_pages: 0,
  sent_to_llm: ['The text of pages you pointed to', 'Your own words', 'Simulated event logs, to be written up'],
  stored_nowhere: ['Raw chat exports', 'Uploaded files', "Other people's names or messages", 'Passwords, cookies or logins of any kind'],
}
