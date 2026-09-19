// Offline sample data: one person, one decided scenario from 2024 (a merge, a road not taken
// with a pick, a stale branch) and one open scenario with three options. Shapes match
// docs/API.md v2. "now" is the real clock. Figures in the sample evidence that cite Statistics
// Canada are the ones in /data; the "researched" items are illustrative and marked as samples.

import { outlookFor } from '../derive'
import type { Basis, BranchView, BranchYear, Chapter, Domain, Evidence, LifeEvent, Outlook, Person, PossibleEvent, ResearchStep, Scenario, StateVector } from '../types'

const PERSON_ID = 'demo'
const BIRTH_YEAR = 2003
export const THIS_YEAR = new Date().getFullYear()

export const demoPerson: Person = {
  id: PERSON_ID,
  display_name: 'Mara Lindqvist',
  birth_year: BIRTH_YEAR,
  sex: 'F',
  personality: { O: 0.72, C: 0.49, E: -0.74, A: 0.44, N: 0, confidence: 0.3, mbti: 'INFJ' },
}

function mainEvent(n: number, date: string, domain: Domain, event_type: string, text: string, source: LifeEvent['source'] = 'scraped', payload: Record<string, unknown> = {}): LifeEvent {
  return { id: `main-${String(n).padStart(3, '0')}`, person_id: PERSON_ID, source, branch_id: 'main', date, domain, event_type, payload, confidence: source === 'told' ? 1 : 0.8, text }
}

export const demoTrunkEvents: LifeEvent[] = [
  mainEvent(1, '2019-06-14', 'work', 'job_start', 'First job: shelving at the Brodie Street library, Thunder Bay'),
  mainEvent(2, '2020-11-02', 'work', 'project', 'First public repository: a tide-table parser'),
  mainEvent(3, '2021-09-07', 'home', 'city_move', 'Moves to Waterloo for university'),
  mainEvent(4, '2021-09-08', 'work', 'education', 'Begins a degree in computer science'),
  mainEvent(5, '2022-05-02', 'work', 'job_start', 'Co-op term: a payments firm in Toronto'),
  mainEvent(6, '2023-01-09', 'home', 'city_move', 'Back to Waterloo; shares a house on Lester Street'),
  mainEvent(7, '2023-09-11', 'love', 'relationship_start', 'Begins seeing someone from the climbing gym', 'told'),
  mainEvent(8, '2024-03-18', 'work', 'decision', 'Chose: the robotics lab in Montréal', 'told', { from_branch: 'br-lab' }),
  mainEvent(9, '2024-03-20', 'home', 'goal', 'A narrow house of your own, with a plum tree', 'told', { from_branch: 'br-payments', carried_event_id: 'br-payments-2031-home_purchase', target_date: '2031-05-14' }),
  mainEvent(10, '2024-05-06', 'work', 'job_start', 'Co-op term: the robotics lab in Montréal'),
  mainEvent(11, '2025-04-28', 'work', 'job_start', 'Co-op term: an infrastructure team in San Francisco'),
  mainEvent(12, '2026-06-12', 'work', 'graduation', 'Graduates'),
  mainEvent(13, '2026-03-21', 'love', 'relationship_end', 'It ends with Noor, in March, on the steps of the climbing gym', 'told'),
  mainEvent(14, '2026-09-04', 'work', 'decision_pending', 'A written offer arrives from the San Francisco team', 'told'),
]

export const demoState: StateVector = {
  year: THIS_YEAR,
  age: THIS_YEAR - BIRTH_YEAR,
  city: 'Waterloo',
  education: "bachelor's, computer science",
  field: 'math_cs',
  employment: 'unemployed',
  income_band: 'lower_middle',
  relationship_status: 'single',
  housing: 'renting',
  activity_proxy: 0.6,
  children: 0,
  alive: true,
}

// ---------------------------------------------------------------- branches

type Beat = [year: number, domain: Domain, type: string, text: string, patch?: Partial<StateVector>, basis?: Basis, evidence?: string]

interface Script {
  id: string
  label: string
  scenario: string
  option: string
  forkedAt: string
  startYear: number
  start: Partial<StateVector>
  assumption: Record<string, unknown>
  precondition?: string
  status: BranchView['branch']['status']
  carried?: string
  solid: [from: number, floor: number, halfLife: number]
  beats: Beat[]
  horizon?: number
  model?: PossibleEvent[]
}

function build(s: Script): BranchView {
  let state: StateVector = { ...demoState, ...s.start }
  const years: BranchYear[] = []
  const [from, floor, halfLife] = s.solid
  for (let i = 0; i < (s.horizon ?? 40); i++) {
    const year = s.startYear + i
    const events: LifeEvent[] = []
    for (const [y, domain, type, text, patch, basis, evidence] of s.beats) {
      if (y !== year) continue
      state = { ...state, ...patch }
      events.push({
        id: `${s.id}-${year}-${type}`,
        person_id: PERSON_ID,
        source: 'simulated',
        branch_id: s.id,
        date: `${year}-${String(((year * 7 + type.length) % 12) + 1).padStart(2, '0')}-14`,
        domain,
        event_type: type,
        payload: { basis: basis ?? 'background', ...(evidence ? { evidence_id: evidence } : {}) },
        confidence: 0.8,
        text,
      })
    }
    state = { ...state, year, age: year - BIRTH_YEAR }
    const solidity = floor + (from - floor) * Math.pow(0.5, i / halfLife)
    const base = { year, solidity: Math.round(solidity * 1000) / 1000, state, events }
    years.push({ ...base, outlook: outlookFor(base), at: `${year}-12-31`, label: String(year) })
  }
  return {
    branch: {
      id: s.id,
      person_id: PERSON_ID,
      label: s.label,
      forked_at: s.forkedAt,
      assumption: s.assumption,
      precondition: s.precondition ?? null,
      status: s.status,
      carried_event_id: s.carried ?? null,
      scenario_id: s.scenario,
      option_id: s.option,
      commits: [],
      research: 'done',
      revision: 1,
      model: { events: s.model ?? [] },
      forming: false,
    },
    years,
  }
}

const today = new Date().toISOString().slice(0, 10)
const daysFromNow = (n: number) => new Date(Date.now() + n * 86_400_000).toISOString().slice(0, 10)
const offerDay = daysFromNow(-12)
const Y = THIS_YEAR + 1 // first simulated year of the open scenario

export const demoBranches: BranchView[] = [
  // --- the 2024 decision, long settled
  build({
    id: 'br-lab', label: 'The robotics lab in Montréal', scenario: 'sc-coop', option: 'op-lab', forkedAt: '2024-02-10', startYear: 2024,
    start: { employment: 'student', city: 'Montréal' }, assumption: { city: 'Montréal' }, status: 'merged', solid: [0.97, 0.6, 9], horizon: 12,
    beats: [[2024, 'work', 'job_start', 'A term at the robotics lab; the arm learns to fold towels, badly'], [2026, 'work', 'graduation', 'Graduates']],
  }),
  build({
    id: 'br-payments', label: 'Back to the payments firm', scenario: 'sc-coop', option: 'op-payments', forkedAt: '2024-02-10', startYear: 2024,
    start: { employment: 'student', city: 'Toronto' }, assumption: { city: 'Toronto' }, status: 'faded', carried: 'br-payments-2031-home_purchase', solid: [0.95, 0.58, 8], horizon: 14,
    beats: [
      [2024, 'work', 'job_start', 'A second term at the payments firm; the same desk, a better monitor'],
      [2026, 'work', 'job_start', 'A full-time offer from the payments firm, accepted in the spring', { employment: 'employed', income_band: 'upper_middle' }],
      [2029, 'love', 'marriage', 'Marries at the Islands, in a borrowed hall', { relationship_status: 'married' }],
      [2031, 'home', 'home_purchase', 'A narrow house off Dovercourt, with a plum tree', { housing: 'owning' }],
      [2034, 'family', 'birth', 'A son', { children: 1 }],
    ],
  }),
  build({
    id: 'br-lund', label: 'The exchange term in Lund', scenario: 'sc-coop', option: 'op-lund', forkedAt: '2024-02-10', startYear: 2024,
    start: { employment: 'student', city: 'Lund' }, assumption: { city: 'Lund' }, precondition: 'application_deadline: 2024-03-01', status: 'stale', solid: [0.9, 0.55, 6], horizon: 10,
    beats: [[2024, 'home', 'city_move', 'A term in Lund; a bicycle bought from a departing student'], [2027, 'home', 'emigration', 'Stays on in Sweden after graduating']],
  }),

  // --- the decision on the table now
  build({
    id: 'br-sf', label: 'Take the offer in San Francisco', scenario: 'sc-offer', option: 'op-sf', forkedAt: offerDay, startYear: Y,
    start: { city: 'San Francisco', employment: 'employed', income_band: 'high' }, assumption: { city: 'San Francisco', employment: 'employed' },
    precondition: `offer_deadline: ${THIS_YEAR}-09-26`, status: 'open', solid: [0.98, 0.6, 10],
    model: [
      { key: 'visa', label: 'the visa comes through', domain: 'work', basis: 'estimated', evidence_id: null, words: 'usually' },
      { key: 'leave_first_job', label: 'you leave the first job within three years', domain: 'work', basis: 'sourced', evidence_id: 'ev-stat-tenure', words: 'as often as not' },
      { key: 'own_by_35', label: 'you own a home by thirty-five', domain: 'home', basis: 'sourced', evidence_id: 'ev-sf-rent', words: 'sometimes' },
      { key: 'move_back', label: 'you move back to Canada', domain: 'home', basis: 'estimated', evidence_id: null, words: 'sometimes' },
    ],
    beats: [
      [Y, 'home', 'city_move', 'Moves to San Francisco; a room in the Inner Sunset'],
      [Y, 'work', 'job_start', 'Starts on the infrastructure team'],
      [Y + 2, 'work', 'job_change', 'Leaves for a smaller company; second engineer on its platform team', undefined, 'sourced', 'ev-stat-tenure'],
      [Y + 3, 'friends', 'peer_wedding', 'A university friend marries in Guelph; you fly back for it'],
      [Y + 5, 'love', 'marriage', 'Marries at City Hall on a Thursday', { relationship_status: 'married' }, 'sourced', 'ev-stat-marriage'],
      [Y + 7, 'family', 'birth', 'A daughter', { children: 1 }],
      [Y + 8, 'home', 'city_move', 'Moves across the bay to Oakland', { city: 'Oakland' }],
      [Y + 10, 'home', 'home_purchase', 'A two-bedroom in Oakland, with a lemon tree that came with it', { housing: 'owning' }],
      [Y + 12, 'work', 'job_change', 'Changes jobs again; a longer commute, a calmer team'],
      [Y + 19, 'family', 'parent_death', 'Your father dies in Thunder Bay, in March'],
      [Y + 38, 'work', 'retirement', 'Retires', { employment: 'retired' }],
    ],
  }),
  build({
    id: 'br-masters', label: "Stay for the master's", scenario: 'sc-offer', option: 'op-masters', forkedAt: offerDay, startYear: Y,
    start: { city: 'Waterloo', employment: 'student', income_band: 'low' }, assumption: { city: 'Waterloo', employment: 'student', graduates_in: 2 },
    status: 'open', solid: [0.97, 0.63, 12],
    model: [
      { key: 'finish_on_time', label: 'you defend within two years', domain: 'learning', basis: 'sourced', evidence_id: 'ev-uw-length', words: 'usually' },
      { key: 'own_by_35', label: 'you own a home by thirty-five', domain: 'home', basis: 'sourced', evidence_id: 'ev-stat-home', words: 'usually' },
      { key: 'phd', label: 'you stay on for a doctorate', domain: 'learning', basis: 'estimated', evidence_id: null, words: 'sometimes' },
    ],
    beats: [
      [Y, 'work', 'education', "Begins the master's; a desk by the window in the Davis Centre"],
      [Y + 1, 'work', 'graduation', 'Defends the thesis in December', { employment: 'employed', income_band: 'middle' }],
      [Y + 2, 'work', 'job_start', 'Joins a research group at a Toronto hospital network', { income_band: 'upper_middle' }],
      [Y + 2, 'home', 'city_move', 'Moves to Kitchener; the train to Toronto three days a week', { city: 'Kitchener' }],
      [Y + 4, 'home', 'home_purchase', 'A brick semi in Kitchener with a pear tree that came with it', { housing: 'owning' }, 'sourced', 'ev-stat-home'],
      [Y + 5, 'love', 'marriage', 'Marries in the back garden, under the pear tree', { relationship_status: 'married' }],
      [Y + 6, 'family', 'birth', 'A son', { children: 1 }],
      [Y + 6, 'friends', 'peer_wedding', 'You attend a wedding in Elora. Table nine, near the band', undefined, 'estimated'],
      [Y + 9, 'family', 'birth', 'A daughter', { children: 2 }],
      [Y + 11, 'work', 'job_change', 'Leaves the hospital network for the university'],
      [Y + 21, 'family', 'parent_death', 'Your father dies in Thunder Bay, in March'],
      [Y + 38, 'work', 'retirement', 'Retires', { employment: 'retired' }],
    ],
  }),
  build({
    id: 'br-bank', label: 'The bank job in Toronto', scenario: 'sc-offer', option: 'op-bank', forkedAt: offerDay, startYear: Y,
    start: { city: 'Toronto', employment: 'employed', income_band: 'upper_middle' }, assumption: { city: 'Toronto', employment: 'employed' },
    status: 'open', solid: [0.98, 0.68, 14],
    model: [
      { key: 'raise_on_schedule', label: 'the raises arrive on schedule', domain: 'money', basis: 'sourced', evidence_id: 'ev-bank-pay', words: 'almost always' },
      { key: 'own_by_35', label: 'you own a home by thirty-five', domain: 'home', basis: 'sourced', evidence_id: 'ev-stat-home', words: 'usually' },
      { key: 'bored', label: 'you look for something else within five years', domain: 'mind', basis: 'estimated', evidence_id: null, words: 'as often as not' },
    ],
    beats: [
      [Y, 'work', 'job_start', 'Starts in risk analytics on Bay Street'],
      [Y, 'home', 'city_move', 'A one-bedroom near Christie Pits', { city: 'Toronto' }],
      [Y + 2, 'money', 'income_up', 'Income rises into the high band', { income_band: 'high' }],
      [Y + 3, 'love', 'marriage', 'Marries in September, at the Brick Works', { relationship_status: 'married' }],
      [Y + 4, 'home', 'home_purchase', 'A condominium on St. Clair West', { housing: 'owning' }],
      [Y + 6, 'family', 'birth', 'A daughter', { children: 1 }],
      [Y + 8, 'work', 'job_change', 'Moves to another bank, two towers over'],
      [Y + 10, 'family', 'birth', 'A son', { children: 2 }],
      [Y + 16, 'love', 'divorce', 'Divorces; the condominium is sold', { relationship_status: 'divorced', housing: 'renting' }],
      [Y + 20, 'family', 'parent_death', 'Your father dies in Thunder Bay, in March'],
      [Y + 38, 'work', 'retirement', 'Retires', { employment: 'retired' }],
    ],
  }),
]

type LooseScenario = Omit<Scenario, 'questions' | 'assuming_branch_id'> & Partial<Pick<Scenario, 'questions' | 'assuming_branch_id'>>

const rawScenarios: LooseScenario[] = [
  {
    id: 'sc-coop', person_id: PERSON_ID, created_at: '2024-02-10', status: 'decided', decided_branch_id: 'br-lab', horizon: { unit: 'years', count: 12 },
    situation: 'Third co-op term. The payments firm wants me back, the robotics lab in Montréal said yes, and there is the exchange term in Lund if I apply in time.',
    options: [
      { id: 'op-lab', title: 'The robotics lab in Montréal', details: 'Four months, a small stipend, French I do not have yet.', deadline: null },
      { id: 'op-payments', title: 'Back to the payments firm', details: 'Same team as my first term. They hinted at a full-time offer.', deadline: null },
      { id: 'op-lund', title: 'The exchange term in Lund', details: 'Applications close on the first of March.', deadline: '2024-03-01' },
    ],
    branch_ids: ['br-lab', 'br-payments', 'br-lund'],
  },
  {
    id: 'sc-offer', person_id: PERSON_ID, created_at: offerDay, status: 'open', decided_branch_id: null, horizon: { unit: 'years', count: 40 },
    situation: "The San Francisco team sent a written offer and wants an answer by the twenty-sixth. I could also stay in Waterloo for the master's — Professor Okafor has funding for me — or take the bank job in Toronto that my first co-op manager keeps mentioning.",
    options: [
      { id: 'op-sf', title: 'Take the offer in San Francisco', details: 'Infrastructure team, the one I interned with. New-graduate package, relocation paid. I would need the visa to come through.', deadline: `${THIS_YEAR}-09-26` },
      { id: 'op-masters', title: "Stay for the master's", details: 'Two years, thesis-based, funded. Distributed systems with Okafor. I keep the house on Lester Street.', deadline: null },
      { id: 'op-bank', title: 'The bank job in Toronto', details: 'Risk analytics on Bay Street. Less interesting, very steady, close to my sister.', deadline: null },
    ],
    branch_ids: ['br-sf', 'br-masters', 'br-bank'],
  },
]

// ---------------------------------------------------------------- evidence

const retrieved = today
const ev = (id: string, branch_id: string | null, kind: Evidence['kind'], claim: string, rest: Partial<Evidence>): Evidence => ({
  id, branch_id, kind, claim, value: null, unit: null, source_title: '', source_url: null, retrieved_at: retrieved, snippet: null, used_for: null, ...rest,
})

export const demoEvidence: Evidence[] = [
  ev('ev-sf-pay', 'br-sf', 'researched', 'A new-graduate software engineer in the Bay Area is offered a package far above the Canadian equivalent.', {
    value: '198,000', unit: 'US dollars a year, total compensation (sample figure)', source_title: 'levels.fyi — Software Engineer, San Francisco Bay Area, entry level',
    source_url: 'https://www.levels.fyi/', snippet: 'Median total compensation, entry level.', used_for: 'Started this branch in the high income band.',
  }),
  ev('ev-sf-rent', 'br-sf', 'researched', 'A one-bedroom in San Francisco rents for roughly twice what one does in Kitchener-Waterloo.', {
    value: '3,150', unit: 'US dollars a month, median one-bedroom (sample figure)', source_title: 'Zumper — San Francisco rent report',
    source_url: 'https://www.zumper.com/', snippet: 'The median one-bedroom rent in San Francisco…', used_for: 'Lowered the yearly chance of buying a home while in San Francisco.',
  }),
  ev('ev-uw-length', 'br-masters', 'researched', "The thesis-based master's in computer science at Waterloo normally takes two years.", {
    value: '6', unit: 'terms', source_title: 'University of Waterloo — MMath in Computer Science, program information',
    source_url: 'https://uwaterloo.ca/', snippet: 'The normal program length is six terms.', used_for: 'Set graduation two years out on this branch.',
  }),
  ev('ev-uw-funding', 'br-masters', 'researched', 'Funded research students receive a guaranteed minimum; it places a student in the lowest income band.', {
    value: '27,000', unit: 'Canadian dollars a year (sample figure)', source_title: 'University of Waterloo — graduate funding', source_url: 'https://uwaterloo.ca/',
    snippet: 'Minimum funding for full-time research students…', used_for: 'Held income in the low band until graduation.',
  }),
  ev('ev-to-rent', 'br-bank', 'researched', 'A one-bedroom near Christie Pits rents for a little over two thousand dollars.', {
    value: '2,250', unit: 'Canadian dollars a month (sample figure)', source_title: 'rentals.ca — Toronto rent report', source_url: 'https://rentals.ca/',
    snippet: 'Average asking rent, one-bedroom, Toronto.', used_for: 'Cost of the first years in Toronto.',
  }),
  ev('ev-bank-pay', 'br-bank', 'researched', 'Analyst roles in risk at the large banks start in the upper-middle band and rise steadily.', {
    value: '82,000', unit: 'Canadian dollars a year (sample figure)', source_title: 'Job Bank — wages, financial analysts, Toronto region', source_url: 'https://www.jobbank.gc.ca/',
    snippet: 'Median wage, Toronto region.', used_for: 'Started this branch in the upper-middle income band.',
  }),
  ev('ev-stat-marriage', null, 'statistic', 'Of unmarried people in their late twenties, about four in a hundred marry in a given year.', {
    value: '0.0406', unit: 'yearly chance of a first marriage at 28', source_title: 'Statistics Canada, table 39-10-0057-01 — nuptiality indicators (2019)',
    source_url: 'https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3910005701', used_for: 'Decides, year by year, whether a simulated life marries.',
  }),
  ev('ev-stat-tenure', null, 'statistic', 'About one in six employed people aged 25 to 34 started their current job within the last year.', {
    value: '0.1697', unit: 'yearly chance of starting a new job, ages 25 to 34', source_title: 'Statistics Canada, table 14-10-0051-01 — job tenure, Labour Force Survey (2025)',
    source_url: 'https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1410005101', used_for: 'Decides when a simulated life changes jobs.',
  }),
  ev('ev-stat-home', null, 'statistic', 'Home ownership climbs fastest between thirty and forty, and faster the higher the income.', {
    value: '0.07', unit: 'yearly chance a middle-income renter aged 30 buys', source_title: 'Statistics Canada, Census 2021, table 98-10-0231-01, with income distribution table 36-10-0101-01',
    source_url: 'https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=9810023101', used_for: 'Decides when a simulated life buys a home.',
  }),
  ev('ev-stat-fertility', null, 'statistic', 'At thirty, about nine women in a hundred have a child in a given year.', {
    value: '0.0928', unit: 'births per woman per year at age 30', source_title: 'Statistics Canada, table 13-10-0418-01 — age-specific fertility rates (2024)',
    source_url: 'https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1310041801', used_for: 'Decides when a child arrives.',
  }),
  ev('ev-stat-mortality', null, 'statistic', "A parent's remaining years are drawn from the same life tables as your own.", {
    value: null, unit: null, source_title: 'Statistics Canada, table 13-10-0114-01 — life tables (2022 to 2024)',
    source_url: 'https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1310011401', used_for: 'Decides the year a parent dies.',
  }),
  ev('ev-me-sf', null, 'personal', 'You have already worked with this team: a co-op term in San Francisco in 2025.', {
    source_title: 'Your log — april 2025, read from your pages', snippet: 'Co-op term: an infrastructure team in San Francisco',
  }),
  ev('ev-me-library', null, 'personal', 'Your first job was shelving books at the Brodie Street library.', {
    source_title: 'Your log — june 2019, read from your pages', snippet: 'First job: shelving at the Brodie Street library, Thunder Bay',
  }),
  ev('ev-me-lester', null, 'personal', 'You have shared the house on Lester Street since 2023.', {
    source_title: 'Your log — january 2023, read from your pages', snippet: 'Back to Waterloo; shares a house on Lester Street',
  }),
  ev('ev-me-payments', null, 'personal', 'Your first co-op term was at a payments firm in Toronto.', {
    source_title: 'Your log — may 2022, read from your pages', snippet: 'Co-op term: a payments firm in Toronto',
  }),
]

// ---------------------------------------------------------------- chapters (the first two eras of each open branch)

type Para = [text: string, ...evidence: string[]]
const chapter = (branch_id: string, from: number, to: number, title: string, paras: Para[]): Chapter => ({
  branch_id, revision: 1, from_year: from, to_year: to, from_at: `${from}-12-31`, to_at: `${to}-12-31`, title, status: 'ready',
  paragraphs: paras.map(([text, ...evidence_ids]) => ({ text, evidence_ids })),
})

export const demoChapters: Chapter[] = [
  chapter('br-sf', Y, Y + 1, 'The Inner Sunset', [
    ['You land in January with two suitcases and the tide-table parser still pinned to your profile. The room is in the Inner Sunset, in a flat shared with a nurse and a man who restores pianos. The fog comes in at four and you learn to keep a sweater at the office.', 'ev-sf-rent'],
    ['The team is the one you interned with, so the first week is mostly people saying they remember your pull requests. The pay is more than anyone in your family has earned, and you check the first deposit twice before believing it. Half of it leaves again on the first of the month.', 'ev-me-sf', 'ev-sf-pay', 'ev-sf-rent'],
    ['You call your sister on Sundays, which is late evening for her. You tell her it is temporary. At this distance from the decision, almost every version of this life looks the same; they have not had time to come apart yet.'],
  ]),
  chapter('br-sf', Y + 2, Y + 6, 'A smaller company', [
    ['In the third year you leave for a company of eleven people above a dim sum restaurant on Clement Street. It is an ordinary thing to do at your age; about one in six people like you start a new job in any given year. You are the second engineer on the platform team, which means you are also the on-call rotation.', 'ev-stat-tenure'],
    ['A university friend marries in Guelph and you fly back for it, a red-eye through Denver. You stand in a rented suit in a field you used to cycle past and realise you have started saying "back home" about two different places.'],
    ['You marry at City Hall on a Thursday, with the piano restorer as a witness. Most of the simulated lives on this branch have married by now, though far from all of them, and the ones that have not are no less ordinary. You are still renting. Here, almost everyone your age is.', 'ev-stat-marriage', 'ev-sf-rent', 'ev-stat-home'],
  ]),
  chapter('br-masters', Y, Y + 1, 'The desk by the window', [
    ['Nothing moves. The house on Lester Street keeps its broken porch light, and in January you are given a desk by the window on the third floor of the Davis Centre, under a vent that ticks. Professor Okafor hands you three papers and says to come back when you disagree with one of them.', 'ev-me-lester'],
    ['The funding covers rent and groceries and not much else; on paper you are in the lowest income band, and you feel it each time the San Francisco team posts photographs. The program is six terms. You count them on the whiteboard and then wipe the count off, embarrassed.', 'ev-uw-funding', 'ev-uw-length'],
    ['You defend in December of the second year, in a room with eleven chairs and four people. Afterwards your committee takes you to the Grad House and Okafor, who never says such things, says the third chapter was good.', 'ev-uw-length'],
  ]),
  chapter('br-masters', Y + 2, Y + 6, 'The pear tree', [
    ['A hospital network in Toronto hires you into a research group that schedules operating rooms. You move to Kitchener rather than the city, and take the train three days a week, reading on the way in and sleeping on the way back.'],
    ['In the fifth year you buy a brick semi with a pear tree that came with it. On this branch that is early but not strange: incomes like yours, in a city like this one, cross into ownership faster than they would have by the bay. The first autumn, the pears are hard and sour, and you make them into something anyway.', 'ev-stat-home'],
    ['You marry in the back garden, under the tree. A son arrives the year after. That same summer you attend a wedding in Elora — table nine, near the band — and spend most of it outside with the pram, which you find you do not mind.', 'ev-stat-marriage', 'ev-stat-fertility'],
  ]),
  chapter('br-bank', Y, Y + 1, 'Bay Street', [
    ['Your first co-op manager meets you in the lobby and walks you up himself. Risk analytics is on the nineteenth floor; your desk faces another tower, in which someone at an identical desk faces you. The work is careful and slow and nobody is ever paged at night.', 'ev-me-payments'],
    ['You take a one-bedroom near Christie Pits, fifteen minutes from your sister by bicycle. The pay is steady and already above what most people your age earn, and the raises are printed on a schedule you are shown on your first day.', 'ev-to-rent', 'ev-bank-pay'],
    ['Of the three lives on the table, this is the one the simulation is surest about. The thousand versions of it stay close together for a long time, the way they do when very little is left to chance.'],
  ]),
  chapter('br-bank', Y + 2, Y + 6, 'St. Clair West', [
    ['The income moves up a band in the third year, exactly when the schedule said it would. You marry in September at the Brick Works; your sister reads something and gets through it.', 'ev-bank-pay', 'ev-stat-marriage'],
    ['You buy a condominium on St. Clair West, on the streetcar line. With two steady incomes in the upper bands, buying before thirty is what this branch usually does.', 'ev-stat-home'],
    ['A daughter arrives in the seventh year. You are asked, around then, whether you would like to manage people, and you say you will think about it, and then you think about it for a long time.', 'ev-stat-fertility'],
  ]),
]

// ---------------------------------------------------------------- research feed (played back over a few seconds offline)

export function demoResearch(branchLabel: string): ResearchStep[] {
  const at = new Date().toISOString()
  const step = (state: ResearchStep['state'], message: string, url: string | null = null): ResearchStep => ({ at, state, message, url, session_url: null })
  return [
    step('searching', `Working out what to look up for “${branchLabel}”`),
    step('reading', 'reading: what this kind of work pays there', 'https://www.levels.fyi/'),
    step('found', 'found: a pay figure, with the sentence it came from'),
    step('reading', 'reading: what a one-bedroom rents for', 'https://www.zumper.com/'),
    step('found', 'found: a median rent'),
    step('skipped', 'skipped: a page that would not open without signing in'),
    step('done', 'Done. The branch has been simulated again with what was found.'),
  ]
}

export const demoInventory = {
  handles: [{ source: 'github', handle: 'maralindqvist' }, { source: 'site', handle: 'https://lindqvist.example' }],
  cached_pages: 3,
  sent_to_llm: ['The text of pages you pointed to', 'Your own words', 'Chat excerpts with every other name replaced', 'Simulated event logs, to be written up'],
  stored_nowhere: ['Raw chat exports', 'Uploaded files', "Other people's names or messages", 'Passwords, cookies or logins of any kind'],
}

// ---------------------------------------------------------------- a small decision: tonight

const STEPS: [days: number, label: string][] = [
  [0, 'tonight'], [1, 'tomorrow'], [3, 'day three'], [7, 'week one'], [14, 'week two'],
  [21, 'week three'], [28, 'week four'], [42, 'week six'], [56, 'week eight'], [84, 'week twelve'],
]

type SmallBeat = [step: number, domain: Domain, key: string, text: string, basis?: Basis, evidence?: string]

function buildSmall(o: { id: string; label: string; option: string; solid: [number, number, number]; model: PossibleEvent[]; beats: SmallBeat[]; suffix?: string; scenario?: string; steps?: typeof STEPS }): BranchView {
  const happened = new Set<string>()
  const years: BranchYear[] = (o.steps ?? STEPS).map(([days, label], i) => {
    const at = daysFromNow(days)
    const events: LifeEvent[] = o.beats.filter((b) => b[0] === i).map(([, domain, key, text, basis, evidence]) => {
      happened.add(key)
      return {
        id: `${o.id}${o.suffix ?? ''}-${i}-${key}`, person_id: PERSON_ID, source: 'simulated' as const, branch_id: o.id, date: at, domain, event_type: key,
        payload: { basis: basis ?? 'estimated', ...(evidence ? { evidence_id: evidence } : {}) }, confidence: 0.7, text,
      }
    })
    const solidity = Math.round((o.solid[1] + (o.solid[0] - o.solid[1]) * Math.pow(0.5, i / o.solid[2])) * 1000) / 1000
    const outlook: Outlook = {}
    for (const e of o.model) outlook[e.key] = { value: happened.has(e.key) ? 'yes' : 'not yet', share: solidity, words: e.words }
    return { year: +at.slice(0, 4), at, label, solidity, state: demoState, events, outlook }
  })
  return {
    branch: {
      id: o.id, person_id: PERSON_ID, label: o.label, forked_at: today, assumption: {}, precondition: null, status: 'open', carried_event_id: null,
      scenario_id: o.scenario ?? 'sc-noor', option_id: o.option, commits: [], research: 'done', revision: 1, model: { events: o.model }, forming: false,
    },
    years,
  }
}

const M = {
  short_sleep: { key: 'short_sleep', label: 'you sleep under five hours tonight', domain: 'body', basis: 'sourced', evidence_id: 'ev-sleep', words: 'usually' },
  reply: { key: 'reply', label: 'she replies within a day', domain: 'love', basis: 'estimated', evidence_id: null, words: 'usually' },
  meet: { key: 'meet', label: 'you meet in person', domain: 'love', basis: 'estimated', evidence_id: null, words: 'as often as not' },
  together: { key: 'together', label: 'you are seeing each other again by week twelve', domain: 'love', basis: 'sourced', evidence_id: 'ev-onoff', words: 'sometimes' },
  second_message: { key: 'second_message', label: 'a second message arrives unanswered', domain: 'love', basis: 'estimated', evidence_id: null, words: 'sometimes' },
  think_less: { key: 'think_less', label: 'you think about it less by week four', domain: 'mind', basis: 'estimated', evidence_id: null, words: 'usually' },
  tell_friend: { key: 'tell_friend', label: 'you tell a friend about it', domain: 'friends', basis: 'estimated', evidence_id: null, words: 'usually' },
} satisfies Record<string, PossibleEvent>

const smallTonight = {
  id: 'br-tonight', label: 'Answer tonight', option: 'op-tonight', solid: [0.95, 0.6, 2.2] as [number, number, number],
  model: [M.short_sleep, M.reply, M.meet, M.together],
}
const smallMorning = { id: 'br-morning', label: 'Answer in the morning', option: 'op-morning', solid: [0.96, 0.66, 3.4] as [number, number, number], model: [M.reply, M.meet, M.together, M.think_less] }
const smallLeave = { id: 'br-leave', label: 'Leave it unanswered', option: 'op-leave', solid: [0.97, 0.78, 5] as [number, number, number], model: [M.second_message, M.tell_friend, M.think_less] }

demoBranches.push(
  buildSmall({
    ...smallTonight,
    beats: [
      [0, 'love', 'answer', 'You answer at eleven-forty. Three lines, rewritten four times', 'background'],
      [0, 'body', 'short_sleep', 'You sleep under five hours', 'sourced', 'ev-sleep'],
      [1, 'love', 'reply', 'A reply arrives before noon'],
      [3, 'love', 'meet', 'Coffee on Tuesday, at the place with the bad chairs'],
      [5, 'love', 'write_first', 'You write first again'],
      [7, 'mind', 'long_walk', 'A long walk along the Iron Horse Trail where most of it gets said'],
      [9, 'love', 'together', 'You are seeing each other again, carefully', 'sourced', 'ev-onoff'],
    ],
  }),
  buildSmall({
    ...smallMorning,
    beats: [
      [0, 'body', 'sleep', 'You put the phone face down and sleep, more or less', 'background'],
      [1, 'love', 'answer', 'You answer at a quarter past eight, over coffee', 'background'],
      [1, 'love', 'reply', 'A reply by evening'],
      [4, 'love', 'meet', 'You meet at the gym, by accident on purpose'],
      [6, 'mind', 'think_less', 'You notice you have stopped checking'],
      [8, 'love', 'occasional', 'It settles into an occasional message, mostly about climbing'],
    ],
  }),
  buildSmall({
    ...smallLeave,
    beats: [
      [0, 'mind', 'other_room', 'You put the phone in the other room', 'background'],
      [2, 'love', 'second_message', 'A second message: only a question mark'],
      [3, 'friends', 'tell_friend', 'You tell Inès about it, halfway up the wall'],
      [6, 'mind', 'think_less', 'You think about it less'],
      [9, 'love', 'nothing', 'Nothing further. The thread stays where it is'],
    ],
  }),
)

rawScenarios.push({
  id: 'sc-noor', person_id: PERSON_ID, created_at: today, status: 'open', decided_branch_id: null, horizon: { unit: 'weeks', count: 12 },
  situation: 'It is eleven at night and Noor has texted for the first time since March. “Saw your name on the route board. Hope you are well.” I could answer now, answer in the morning, or leave it.',
  options: [
    { id: 'op-tonight', title: 'Answer tonight', details: 'Something short and warm. I have been drafting it in my head for six months anyway.', deadline: null },
    { id: 'op-morning', title: 'Answer in the morning', details: 'Sleep on it, reply over coffee, keep it light.', deadline: null },
    { id: 'op-leave', title: 'Leave it unanswered', details: 'Say nothing. See whether that holds.', deadline: null },
  ],
  branch_ids: ['br-tonight', 'br-morning', 'br-leave'],
})

// the one-in-a-thousand lives
export const demoRare: Record<string, { rarity_words: string; years: BranchYear[] }> = {
  'br-tonight': {
    rarity_words: 'Fewer than one in a hundred of the simulated lives go this way.',
    years: buildSmall({
      ...smallTonight, suffix: '-rare', solid: [0.62, 0.6, 2],
      beats: [
        [0, 'love', 'answer', 'You answer at eleven-forty', 'background'],
        [0, 'love', 'call', 'The phone rings ninety seconds later. You talk until the birds start'],
        [2, 'home', 'keys', 'She still has your spare key, and uses it'],
        [4, 'play', 'trip', 'A week in the Bruce Peninsula that neither of you planned'],
        [7, 'home', 'lease', 'You sign a lease together on Dupont Street, in Toronto'],
        [9, 'work', 'offer', 'You turn down San Francisco without being asked to'],
      ],
    }).years,
  },
  'br-morning': {
    rarity_words: 'About one in a hundred of the simulated lives go this way.',
    years: buildSmall({
      ...smallMorning, suffix: '-rare', solid: [0.62, 0.6, 2],
      beats: [[1, 'love', 'answer', 'You answer over coffee', 'background'], [1, 'love', 'wrong_thread', 'Your reply goes to the climbing-gym group chat instead'], [3, 'friends', 'legend', 'It becomes a story the whole gym tells, kindly'], [8, 'love', 'someone_new', 'You are seeing someone who heard the story first']],
    }).years,
  },
  'br-leave': {
    rarity_words: 'Fewer than one in a hundred of the simulated lives go this way.',
    years: buildSmall({
      ...smallLeave, suffix: '-rare', solid: [0.62, 0.6, 2],
      beats: [[0, 'mind', 'other_room', 'You put the phone in the other room', 'background'], [6, 'love', 'door', 'She is at your door with your tide-table book'], [9, 'love', 'letter', 'You write to each other on paper now, for reasons neither can explain']],
    }).years,
  },
}

demoEvidence.push(
  ev('ev-sleep', 'br-tonight', 'researched', 'People who use their phone in bed late at night sleep measurably less and worse that night.', {
    value: '48', unit: 'minutes less sleep on nights with phone use after lights-out (sample figure)', source_title: 'Sleep Health — bedtime phone use and sleep duration in young adults',
    source_url: 'https://www.sleephealthjournal.org/', snippet: 'Participants slept on average 48 fewer minutes on nights with in-bed phone use…', used_for: 'Set how often tonight ends with under five hours of sleep.',
  }),
  ev('ev-onoff', 'br-tonight', 'researched', 'Getting back together is common: a large share of young adults have reconciled with a former partner at least once.', {
    value: '44', unit: 'per cent of young adults report having reconciled with an ex (sample figure)', source_title: 'Journal of Adolescent Research — relationship churning in emerging adulthood',
    source_url: 'https://journals.sagepub.com/home/jar', snippet: 'Nearly half of respondents reported a reconciliation…', used_for: 'Set how often contact leads to seeing each other again within twelve weeks.',
  }),
  ev('ev-me-noor', null, 'personal', 'It ended with Noor in March, on the steps of the climbing gym.', {
    source_title: 'Your log — march 2026, told by you', snippet: 'It ends with Noor, in March, on the steps of the climbing gym',
  }),
)

const smallChapter = (branch_id: string, a: number, b: number, title: string, paras: Para[], steps = STEPS): Chapter => ({
  branch_id, revision: 1, from_year: THIS_YEAR, to_year: THIS_YEAR, from_at: daysFromNow(steps[a][0]), to_at: daysFromNow(steps[b][0]), title, status: 'ready',
  paragraphs: paras.map(([text, ...evidence_ids]) => ({ text, evidence_ids })),
})

demoChapters.push(
  smallChapter('br-tonight', 0, 1, 'Eleven-forty', [
    ['You type it sitting on the stairs, because the bedroom felt like too much of a decision. Three lines. You take out “honestly”, put it back, take it out. It has been six months since the steps of the climbing gym, and you have been drafting this, on and off, for most of them.', 'ev-me-noor'],
    ['You send it at eleven-forty and then do the thing everyone does, which is lie in the dark holding a lit rectangle. On nights like this people sleep less, and you are not an exception: it is past three when you stop checking, and the alarm is at seven.', 'ev-sleep'],
    ['The reply is there before noon. There is no published figure for how quickly an ex writes back, so Hereafter can only call this likely, not measured. It is four words and a photograph of the route board with your name on it.'],
  ]),
  smallChapter('br-tonight', 2, 6, 'The place with the bad chairs', [
    ['Coffee on Tuesday, at the place with the bad chairs, because neither of you wanted to suggest anywhere that meant something. She has cut her hair. You talk about the new setter at the gym for twenty minutes before either of you says anything true.'],
    ['In week three you write first again, which you notice, and decide not to mind. From here the thousand simulated versions of this start to pull apart: in some it is already over again, in some it never quite starts. The line gets thinner because less is known, not because less is happening.'],
  ]),
  smallChapter('br-tonight', 7, 9, 'Carefully', [
    ['There is a long walk along the Iron Horse Trail in week six where most of it gets said: what March was, what San Francisco might be. By week twelve you are seeing each other again, carefully. That happens more often than people admit — a large share of people your age have gone back at least once — but it is still the less common ending here, and Hereafter draws it that way.', 'ev-onoff'],
  ]),
  smallChapter('br-morning', 0, 1, 'Over coffee', [
    ['You put the phone face down on the bookshelf, across the room, which is its own kind of answer. You sleep, more or less. In the morning the message is still there and still says the same eleven words.'],
    ['You reply at a quarter past eight with the mug in your other hand: glad she wrote, the route was a gift, hope the new job is good. It reads like someone who slept. She answers by evening, and the evening is ordinary.'],
  ]),
  smallChapter('br-leave', 0, 1, 'The other room', [
    ['You put the phone in the other room and wash the dishes that did not need washing. It is not a refusal, you tell yourself; it is only not tonight. Of the three branches this is the one the simulation is surest about in the short run, because almost nothing is left to chance when nothing is sent.'],
    ['You sleep badly anyway, but for a different reason.'],
  ]),
)

export const demoRareChapters: Chapter[] = [
  smallChapter('br-tonight', 0, 1, 'Ninety seconds', [
    ['This is the rarest coherent life among the thousand: nothing in it is impossible, it is only that almost none of them go this way. You send the message at eleven-forty. The phone rings ninety seconds later, and it is her voice, slightly out of breath, saying she was hoping you were awake.'],
    ['You talk until the birds start. Nobody sleeps under five hours tonight, because nobody sleeps.'],
  ]),
  smallChapter('br-tonight', 2, 6, 'The spare key', [
    ['She still has your spare key, it turns out, and on day three she uses it, with groceries. There is a week on the Bruce Peninsula that neither of you planned, in a borrowed car with a broken heater. In this universe things simply keep saying yes.'],
  ]),
]

// ---------------------------------------------------------------- a decision inside a branch, with a question still open

const uni = (id: string, option: string, label: string, city: string, beats: Beat[], model: PossibleEvent[]): BranchView =>
  build({
    id, label, scenario: 'sc-where', option, forkedAt: daysFromNow(-3), startYear: Y, horizon: 6,
    start: { city, employment: 'student', income_band: 'low' }, assumption: { city, employment: 'student' }, status: 'open',
    // wide and faint on purpose: what she would study has not been said yet
    solid: [0.8, 0.6, 1.6], beats, model,
  })

demoBranches.push(
  uni('br-mac', 'op-mac', 'McMaster', 'Hamilton', [
    [Y, 'home', 'city_move', 'Moves to Hamilton; a basement flat in Westdale'],
    [Y + 1, 'learning', 'thesis', 'A thesis topic, eventually, after two false starts', undefined, 'estimated'],
    [Y + 2, 'learning', 'graduation', 'Defends in the spring', { employment: 'employed', income_band: 'middle' }],
  ], [
    { key: 'funded', label: 'the funding covers rent', domain: 'money', basis: 'sourced', evidence_id: 'ev-uw-funding', words: 'usually' },
    { key: 'switch_topic', label: 'you change topic in the first year', domain: 'learning', basis: 'estimated', evidence_id: null, words: 'as often as not' },
  ]),
  uni('br-uw', 'op-uw', 'Waterloo', 'Waterloo', [
    [Y, 'learning', 'education', 'Stays; the desk by the window in the Davis Centre'],
    [Y + 1, 'learning', 'graduation', 'Defends the thesis in December', { employment: 'employed', income_band: 'middle' }, 'sourced', 'ev-uw-length'],
  ], [
    { key: 'finish_on_time', label: 'you defend within two years', domain: 'learning', basis: 'sourced', evidence_id: 'ev-uw-length', words: 'usually' },
    { key: 'same_house', label: 'you keep the house on Lester Street', domain: 'home', basis: 'estimated', evidence_id: null, words: 'usually' },
  ]),
  uni('br-uoft', 'op-uoft', 'U of T', 'Toronto', [
    [Y, 'home', 'city_move', 'Moves to Toronto; a room in the Annex, fifteen minutes from your sister'],
    [Y + 1, 'money', 'ta', 'Takes on a second teaching assistantship to cover the rent', undefined, 'sourced', 'ev-to-rent'],
    [Y + 2, 'learning', 'graduation', 'Defends in August', { employment: 'employed', income_band: 'upper_middle' }],
  ], [
    { key: 'rent_strain', label: 'the rent outruns the funding', domain: 'money', basis: 'sourced', evidence_id: 'ev-to-rent', words: 'usually' },
    { key: 'near_sister', label: 'you see your sister weekly', domain: 'family', basis: 'estimated', evidence_id: null, words: 'usually' },
  ]),
)


rawScenarios.push({
  id: 'sc-where', person_id: PERSON_ID, created_at: daysFromNow(-3), status: 'open', decided_branch_id: null, horizon: { unit: 'years', count: 6 },
  assuming_branch_id: 'br-masters',
  situation: "If I do stay for a master's: McMaster, Waterloo or U of T?",
  options: [
    { id: 'op-mac', title: 'McMaster', details: '', deadline: `${Y}-01-15` },
    { id: 'op-uw', title: 'Waterloo', details: '', deadline: `${Y}-02-01` },
    { id: 'op-uoft', title: 'U of T', details: '', deadline: `${THIS_YEAR}-12-01` },
  ],
  branch_ids: ['br-mac', 'br-uw', 'br-uoft'],
  questions: [
    {
      id: 'q-study', scenario_id: 'sc-where', text: 'What would you study?', why: 'the field decides which labs would take you, and what the degree pays afterwards',
      choices: ['distributed systems', 'machine learning', 'human–computer interaction', 'not sure yet'], applies_to: [], answer: null,
    },
  ],
})

// ---------------------------------------------------------------- a medium decision: about a month

const MONTH: typeof STEPS = [[1, 'day one'], [4, 'day four'], [7, 'week one'], [14, 'week two'], [21, 'week three'], [30, 'day thirty'], [37, 'the week after']]

const D = {
  lapse: { key: 'lapse', label: 'you have a drink before day thirty', domain: 'body', basis: 'sourced', evidence_id: 'ev-dry', words: 'as often as not' },
  sleep_better: { key: 'sleep_better', label: 'you sleep better by week two', domain: 'body', basis: 'sourced', evidence_id: 'ev-dry', words: 'usually' },
  skip_night: { key: 'skip_night', label: 'you skip a night out rather than explain', domain: 'friends', basis: 'estimated', evidence_id: null, words: 'usually' },
  drink_less_after: { key: 'drink_less_after', label: 'you are still drinking less the week after', domain: 'growth', basis: 'sourced', evidence_id: 'ev-dry', words: 'usually' },
  drift_back: { key: 'drift_back', label: 'the rule quietly stops being a rule', domain: 'mind', basis: 'estimated', evidence_id: null, words: 'usually' },
} satisfies Record<string, PossibleEvent>

demoBranches.push(
  buildSmall({
    id: 'br-dry', label: 'A dry month', option: 'op-dry', scenario: 'sc-dry', steps: MONTH, solid: [0.95, 0.63, 2.4], model: [D.sleep_better, D.skip_night, D.lapse, D.drink_less_after],
    beats: [
      [0, 'body', 'start', 'You pour the last of the bottle down the sink, a little theatrically', 'background'],
      [1, 'friends', 'skip_night', 'You skip trivia night rather than explain yourself'],
      [3, 'body', 'sleep_better', 'You are asleep before midnight four nights running', 'sourced', 'ev-dry'],
      [4, 'friends', 'soda', 'Inès orders you a soda water without asking, and that is that'],
      [5, 'growth', 'finish', 'Day thirty. You finish, and do not feel the need to mark it', 'sourced', 'ev-dry'],
      [6, 'growth', 'drink_less_after', 'One glass at the wedding in Elora, and then water', 'sourced', 'ev-dry'],
    ],
  }),
  buildSmall({
    id: 'br-cutback', label: 'Just cut back', option: 'op-cutback', scenario: 'sc-dry', steps: MONTH, solid: [0.94, 0.6, 1.8], model: [D.drift_back, D.sleep_better],
    beats: [
      [0, 'mind', 'rule', 'You decide on weekends only, and write it nowhere', 'background'],
      [2, 'friends', 'thursday', 'Thursday is nearly the weekend'],
      [4, 'mind', 'drift_back', 'The rule quietly stops being a rule'],
      [6, 'mind', 'again', 'You think about trying the full month after all'],
    ],
  }),
)

rawScenarios.push({
  id: 'sc-dry', person_id: PERSON_ID, created_at: daysFromNow(-1), status: 'open', decided_branch_id: null, horizon: { unit: 'weeks', count: 5 },
  situation: 'A month without drinking, starting Monday — or do I just cut back and see?',
  options: [
    { id: 'op-dry', title: 'A dry month', details: 'Thirty days, no exceptions, tell people up front.', deadline: null },
    { id: 'op-cutback', title: 'Just cut back', details: 'Weekends only. No announcement.', deadline: null },
  ],
  branch_ids: ['br-dry', 'br-cutback'],
})

demoEvidence.push(
  ev('ev-dry', 'br-dry', 'researched', 'Most people who attempt a dry month report better sleep, and many are still drinking less months later, whether or not they finished.', {
    value: '7 in 10', unit: 'participants reporting better sleep (sample figure)', source_title: 'University of Sussex — follow-up study of Dry January participants',
    source_url: 'https://www.sussex.ac.uk/', snippet: 'Seven in ten slept better… reductions in drinking were still seen in August.', used_for: 'Set how often sleep improves, how often the month is finished, and what the week after looks like.',
  }),
)

demoChapters.push(
  smallChapter('br-dry', 0, 2, 'The sink', [
    ['You pour the last of the bottle down the sink on Sunday night, a little theatrically, and tell the house group chat so that there are witnesses. Day one is easy because it is a Monday.'],
    ['Thursday is trivia night, and you stay home rather than explain yourself over a soda water. That is what most people do in the first week; there is no published figure for it, so Hereafter marks it as an estimate.'],
  ], MONTH),
  smallChapter('br-dry', 3, 6, 'Before midnight', [
    ['By the second week you are asleep before midnight four nights running, and waking before the alarm, faintly annoyed at how well it works. This part is not a guess: most people who try a dry month report sleeping better.', 'ev-dry'],
    ['Day thirty arrives without ceremony. About as many of the thousand simulated versions of you slipped once along the way as did not; this one did not. The week after, there is one glass at the wedding in Elora, and then water.', 'ev-dry'],
  ], MONTH),
  smallChapter('br-cutback', 0, 6, 'Weekends only', [
    ['You decide on weekends only, and write it down nowhere. It holds for nine days. Then Thursday is nearly the weekend, and by week three the rule has quietly stopped being a rule, which is how this branch usually goes.'],
    ['In the week after the month would have ended, you catch yourself thinking about trying the full thing after all.'],
  ], MONTH),
)

export const demoScenarios: Scenario[] = rawScenarios.map((s) => ({ ...s, questions: s.questions ?? [], assuming_branch_id: s.assuming_branch_id ?? null }))
