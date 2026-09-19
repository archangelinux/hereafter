// Mirrors docs/API.md exactly.

export type Source = 'scraped' | 'passive' | 'told' | 'simulated'
/** A free-form lowercase life-area tag (work, money, health, body, mind, love, family, friends, …). */
export type Domain = string
export type BranchStatus = 'open' | 'merged' | 'faded' | 'expired' | 'stale'
export type ResearchState = 'none' | 'pending' | 'running' | 'done' | 'failed'

export interface LifeEvent {
  id: string
  person_id: string
  source: Source
  branch_id: string
  date: string
  domain: Domain
  event_type: string
  payload: Record<string, unknown>
  confidence: number
  text: string
  /** from the borrowed life shown to a newcomer; never sent to the backend */
  example?: boolean
}

export interface StateVector {
  year: number
  age: number
  city: string
  education: string
  field: string
  employment: 'employed' | 'unemployed' | 'student' | 'retired'
  income_band: 'low' | 'lower_middle' | 'middle' | 'upper_middle' | 'high'
  relationship_status: 'single' | 'married' | 'divorced' | 'widowed'
  housing: 'renting' | 'owning' | 'with_family'
  activity_proxy: number
  children: number
  alive: boolean
}

export interface Assumption {
  city?: string
  field?: string
  employment?: string
  relationship_status?: string
  housing?: string
  education?: string
}

export interface Branch {
  id: string
  person_id: string
  label: string
  forked_at: string
  assumption: Assumption
  precondition: string | null
  status: BranchStatus
  carried_event_id: string | null
  // v2 — always present after api.ts normalises a response
  scenario_id: string | null
  option_id: string | null
  commits: Commit[]
  research: ResearchState
  revision: number
  model: { events: PossibleEvent[] }
  /** still being drawn: no steps yet, only a guide line. Fills in as revisions land. */
  forming: boolean
  /** part of the borrowed life shown to a newcomer: readable and walkable, never mutable, never sent to the backend */
  example?: boolean
}

export interface Commit {
  id: string
  branch_id: string
  year: number
  at: string
  message: string
  patch: Record<string, unknown>
  created_at: string
}

/** Background aspects (alive, city, employment, income_band, relationship, housing, children) or a PossibleEvent key. */
export type Aspect = string
export type Basis = 'sourced' | 'estimated' | 'background'

export interface PossibleEvent {
  key: string
  label: string
  domain: string
  basis: Basis
  evidence_id: string | null
  words: string
}

export interface Horizon {
  unit: 'days' | 'weeks' | 'months' | 'years'
  count: number
}
export type LikelihoodWords = 'almost always' | 'usually' | 'as often as not' | 'sometimes' | 'rarely'

export interface OutlookEntry {
  share: number
  words: LikelihoodWords | string
  value: string
}
export type Outlook = Record<Aspect, OutlookEntry>

export interface BranchYear {
  year: number
  solidity: number
  state: StateVector
  events: LifeEvent[]
  outlook: Outlook
  at: string // the date of this step; steps may be days, weeks, months or years apart
  label: string // "tonight", "week 3", "2031"
}

export interface BranchView {
  branch: Branch
  years: BranchYear[]
}

export interface Personality {
  O: number
  C: number
  E: number
  A: number
  N: number
  confidence: number
  mbti: string | null
}

export interface Person {
  id: string
  display_name?: string | null
  birth_year?: number | null
  sex?: 'M' | 'F' | null
  personality?: Personality | null
  [key: string]: unknown
}

export interface Reconciliation {
  slot: string
  chosen: string
  over: string[]
  reason: string
}

export interface AgentStep {
  step: number
  tool: string
  args: Record<string, unknown>
  reason: string
  hits: number
  planner: 'llm' | 'rules'
}

export interface Health {
  ok: boolean
  llm_enabled: boolean
  store: 'elastic' | 'local'
  now: string
}

export interface TrunkResponse {
  person: Person
  now: string
  events: LifeEvent[]
  state: StateVector
  agent_log: AgentStep[]
  reconciliation?: Reconciliation[]
}

export interface BranchesResponse {
  now: string
  branches: BranchView[]
}

export interface Handles {
  github?: string
  linkedin?: string
  site?: string
  instagram?: string
}

/** The Offering: sent to /ingest as multipart/form-data. Everything but person_id is optional. */
export interface Offering {
  person_id: string
  display_name?: string
  birth_year?: number
  sex?: 'M' | 'F'
  text?: string
  handles?: Handles
  links?: string[]
  live_source?: 'github' | 'site'
  files?: File[]
}

export type InputKind = 'handles' | 'link' | 'freeform' | 'chat_export' | 'resume' | 'personality' | 'unknown'

export interface IngestResult {
  person_id: string
  events_added: LifeEvent[]
  inputs: { name: string; kind: InputKind; outcome: string }[]
  personality: Personality | null
  reconciliation: Reconciliation[]
}

export interface SimulateRequest {
  person_id: string
  label: string
  assumption: Assumption
  precondition?: string
  horizon_years?: number
}

export interface MergeResponse {
  merged: Branch
  faded: Branch[]
  told_event: LifeEvent
}

export interface CarryResponse {
  goal_event: LifeEvent
  branch: Branch
}

export interface NarrationResponse {
  branch_id: string
  complete: boolean
  lines: Record<string, string>
}

// ---------------------------------------------------------------- v2

export interface Option {
  id: string
  title: string
  details: string
  deadline: string | null
}

export interface Scenario {
  id: string
  person_id: string
  situation: string
  created_at: string
  options: Option[]
  branch_ids: string[]
  status: 'open' | 'decided'
  decided_branch_id: string | null
  horizon: Horizon
  questions: Question[]
  /** set when this decision is being made inside another branch's life rather than from now */
  assuming_branch_id: string | null
  example?: boolean
}

export interface Question {
  id: string
  scenario_id: string
  text: string
  why: string
  choices: string[]
  applies_to: string[] // option ids; empty means every option
  answer: string | null
}

export type Which = 'typical' | 'rare'

export interface OptionDraft {
  title: string
  details: string
  deadline?: string
}

export interface ScenarioResponse {
  scenario: Scenario
  branches: BranchView[]
}

export interface Evidence {
  id: string
  branch_id: string | null
  kind: 'researched' | 'statistic' | 'personal'
  claim: string
  value: string | null
  unit: string | null
  source_title: string
  source_url: string | null
  retrieved_at: string
  snippet: string | null
  used_for: string | null
}

export interface Chapter {
  branch_id: string
  revision: number
  from_year: number
  to_year: number
  from_at: string
  to_at: string
  title: string
  status: 'writing' | 'ready'
  paragraphs: { text: string; evidence_ids: string[] }[]
}

export interface ResearchStep {
  at: string
  state: 'searching' | 'reading' | 'found' | 'skipped' | 'done'
  message: string
  url: string | null
  session_url: string | null
}

export interface ResearchResponse {
  branch_id: string
  research: ResearchState
  steps: ResearchStep[]
}

export interface CompareValue {
  branch_id: string
  value: string
  words: string
  share: number
}

export interface CompareResponse {
  branches: Branch[]
  checkpoints: { year: number; age: number; label?: string; rows: { aspect: Aspect; differs: boolean; values: CompareValue[] }[] }[]
  /** what is unusually common in each branch against its siblings */
  distinctive?: { branch_id: string; label: string; words: string; basis: Basis }[]
}

export interface LivesResponse {
  which: 'typical' | 'rare'
  rarity_words: string
  years: BranchYear[]
}

export interface Inventory {
  sources: { source: string; count: number; newest: string; examples: LifeEvent[] }[]
  handles: { source: string; handle: string }[] | string[]
  cached_pages: number
  sent_to_llm: string[]
  stored_nowhere: string[]
}

export interface EraseResult {
  erased: { events: number; evidence: number; branches: number; cached_pages: number }
}

export interface Session {
  person_id: string
  token: string
}

/** A region of the screen the HUD occupies, in viewport pixels. Views keep labels out of these. */
export interface Zone {
  x: number
  y: number
  w: number
  h: number
}

export interface Insets {
  top: number
  right: number
  bottom: number
  left: number
}
