// The offline sample: ONE simple, coherent story.
//
//   Sam Rivera, 24, a designer in Toronto.
//   main      — seven past events that lead plausibly to today
//   decided   — a small decision from three weeks ago, already merged ("Sign up for the half marathon")
//   open, big — "The Vancouver offer": take it / stay and ask for a raise / go freelance  (3 years, dated steps)
//   open, small — "Friday night": Dana's birthday dinner / stay and finish the pitch deck   (a week)
//
// Every path starts with step zero, the choice itself (`head: true`) — that is what a merge records —
// and then its direct consequences in causal, dated order. Researched figures are illustrative and
// marked as samples; the Statistics Canada figure is the one in /data.

import type { Basis, BranchView, Marks, Measure, BranchYear, Chapter, Domain, Evidence, LifeEvent, Outlook, Person, PossibleEvent, ResearchStep, Scenario, StateVector } from '../types'

const PERSON_ID = 'demo'
const BIRTH_YEAR = 2002
export const THIS_YEAR = new Date().getFullYear()

const DAY = 86_400_000
const MONTHS_LONG = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
const iso = (daysFromNow: number) => new Date(Date.now() + daysFromNow * DAY).toISOString().slice(0, 10)
/** a date some days from now, in words: "12 October" */
const on = (n: number) => {
  const d = new Date(Date.now() + n * DAY)
  return `${d.getDate()} ${MONTHS_LONG[d.getMonth()]}`
}
const today = iso(0)

export const demoPerson: Person = { id: PERSON_ID, display_name: 'Sam Rivera', birth_year: BIRTH_YEAR, sex: null, personality: { O: 0.6, C: 0.3, E: -0.4, A: 0.5, N: 0.1, confidence: 0.3, mbti: 'INFP' } }

export const demoState: StateVector = {
  year: THIS_YEAR, age: THIS_YEAR - BIRTH_YEAR, city: 'Toronto', education: 'design diploma', field: 'arts', employment: 'employed',
  income_band: 'middle', relationship_status: 'single', housing: 'renting', activity_proxy: 0.6, children: 0, alive: true,
}

function mainEvent(n: number, date: string, domain: Domain, event_type: string, text: string, origin: string, payload: Record<string, unknown> = {}): LifeEvent {
  const source = origin === 'your words' ? 'told' : 'scraped'
  return { id: `main-${n}`, person_id: PERSON_ID, source, branch_id: 'main', date, domain, event_type, payload, confidence: source === 'told' ? 1 : 0.8, text, origin }
}

export const demoTrunkEvents: LifeEvent[] = [
  mainEvent(1, `${THIS_YEAR - 6}-09-08`, 'learning', 'education', 'Starts a graphic design diploma at George Brown, Toronto', 'resume.pdf'),
  mainEvent(2, `${THIS_YEAR - 4}-06-17`, 'learning', 'graduation', 'Graduates', 'resume.pdf'),
  mainEvent(3, `${THIS_YEAR - 4}-09-12`, 'work', 'job_start', 'First job: junior designer at Fieldnote, a small agency', 'resume.pdf'),
  mainEvent(4, `${THIS_YEAR - 3}-05-01`, 'home', 'city_move', 'Moves into a shared flat on Dovercourt Road', 'your words'),
  mainEvent(5, `${THIS_YEAR - 2}-11-02`, 'body', 'habit', 'Joins a Saturday running club', 'your words'),
  mainEvent(6, `${THIS_YEAR - 1}-10-06`, 'work', 'promotion', 'Promoted to designer at Fieldnote', 'resume.pdf'),
  mainEvent(7, iso(-21), 'body', 'decision', 'Chose: Sign up', 'your words', { from_branch: 'br-signup' }),
  mainEvent(8, iso(-9), 'work', 'decision_pending', 'A studio in Vancouver offers a senior designer role', 'your words'),
]

// ---------------------------------------------------------------- paths

type Beat = [step: number, domain: Domain, key: string, text: string, basis?: Basis, evidence?: string]
type Steps = number[] // days after the fork

interface PathScript {
  id: string
  label: string
  scenario: string
  option: string
  forkedDaysAgo?: number
  steps: Steps
  status?: BranchView['branch']['status']
  solid: [from: number, floor: number, halfLife: number]
  model: PossibleEvent[]
  beats: Beat[] // the first beat is always the choice itself
  suffix?: string
}

function path(o: PathScript): BranchView {
  const fork = -(o.forkedDaysAgo ?? 0)
  const happened = new Set<string>()
  // each possibility's own moment, as the backend sends it: from the step it could first fall in to
  // the end of the path. The panel reads this to say what could happen WHERE THE READER IS STANDING.
  const first = new Map<string, number>()
  for (const b of o.beats) if (!first.has(b[2])) first.set(b[2], b[0])
  const model: PossibleEvent[] = o.model.map((e) => {
    const from = first.get(e.key) ?? 1
    return { ...e, window: [from, Math.min(o.steps.length - 1, from + 4)] as [number, number] }
  })
  const years: BranchYear[] = o.steps.map((days, i) => {
    const at = iso(fork + days)
    const events: LifeEvent[] = o.beats.filter((b) => b[0] === i).map(([, domain, key, text, basis, evidence], n) => {
      happened.add(key)
      const head = i === 0 && n === 0
      return {
        id: `${o.id}${o.suffix ?? ''}-${i}-${key}`, person_id: PERSON_ID, source: 'simulated' as const, branch_id: o.id, date: at, domain, event_type: key,
        payload: { basis: head ? 'background' : (basis ?? 'estimated'), ...(evidence ? { evidence_id: evidence } : {}), ...(head ? { head: true } : {}) },
        confidence: 0.8, text, ...(head ? { head: true } : {}),
      }
    })
    const solidity = Math.round((o.solid[1] + (o.solid[0] - o.solid[1]) * Math.pow(0.5, i / o.solid[2])) * 1000) / 1000
    const outlook: Outlook = {}
    for (const e of model) outlook[e.key] = { value: happened.has(e.key) ? 'yes' : 'not yet', share: solidity, words: e.words }
    return { year: +at.slice(0, 4), at, label: on(fork + days), solidity, state: demoState, events, outlook }
  })
  return {
    branch: {
      id: o.id, person_id: PERSON_ID, label: o.label, forked_at: iso(fork), assumption: {}, precondition: null, status: o.status ?? 'open', carried_event_id: null,
      scenario_id: o.scenario, option_id: o.option, commits: [], research: 'done', revision: 1, model: { events: model }, forming: false,
    },
    years,
  }
}

const ev = (key: string, label: string, domain: string, words: string, basis: Basis = 'estimated', evidence_id: string | null = null): PossibleEvent => ({ key, label, domain, basis, evidence_id, words })

// three years: weekly, then monthly, then quarterly
const THREE_YEARS: Steps = [0, 7, 14, 30, 60, 90, 180, 270, 365, 545, 730, 1095]
const A_WEEK: Steps = [0, 1, 3, 7]
const RACE: Steps = [0, 7, 21, 60]

const vancouver: PathScript = {
  id: 'br-vancouver', label: 'Take the Vancouver job', scenario: 'sc-job', option: 'op-vancouver', forkedDaysAgo: 9, steps: THREE_YEARS, solid: [0.97, 0.62, 4],
  model: [
    ev('rent_up', 'your rent goes up by a third or more', 'money', 'usually', 'sourced', 'ev-van-rent'),
    ev('raise', 'you earn more than you do now', 'money', 'almost always', 'sourced', 'ev-van-pay'),
    ev('lonely', 'the first winter is lonely', 'mind', 'as often as not'),
    ev('stay_3y', 'you are still in Vancouver after three years', 'home', 'as often as not', 'sourced', 'ev-stat-tenure'),
    ev('move_back', 'you move back to Toronto', 'home', 'sometimes'),
  ],
  beats: [
    [0, 'work', 'choice', 'You accept the Vancouver offer'],
    [1, 'work', 'notice', 'You give notice at Fieldnote; they take it well'],
    [3, 'home', 'move', 'You move into a one-bedroom in Mount Pleasant', 'sourced', 'ev-van-rent'],
    [3, 'money', 'rent_up', 'The rent is a third more than Dovercourt was', 'sourced', 'ev-van-rent'],
    [4, 'work', 'raise', 'First pay at the new salary', 'sourced', 'ev-van-pay'],
    [5, 'body', 'seawall', 'You find a running club on the seawall'],
    [6, 'mind', 'lonely', 'The first winter is grey, and lonelier than you expected'],
    [8, 'work', 'lead', 'You lead your first client project'],
    [10, 'friends', 'settled', 'Most of your weekends are with people you met here'],
    [11, 'home', 'stay_3y', 'Three years on, you renew the lease', 'sourced', 'ev-stat-tenure'],
  ],
}

const raise: PathScript = {
  id: 'br-raise', label: 'Stay and ask for a raise', scenario: 'sc-job', option: 'op-raise', forkedDaysAgo: 9, steps: THREE_YEARS, solid: [0.97, 0.68, 5],
  model: [
    ev('raise_yes', 'you get at least part of the raise', 'money', 'usually'),
    ev('same_flat', 'you are still in the Dovercourt flat in a year', 'home', 'usually'),
    ev('restless', 'you look at job listings again within a year', 'work', 'as often as not', 'sourced', 'ev-stat-tenure'),
    ev('leave', 'you leave Fieldnote within three years', 'work', 'as often as not', 'sourced', 'ev-stat-tenure'),
  ],
  beats: [
    [0, 'work', 'choice', 'You turn Vancouver down and book a meeting with your director'],
    [1, 'work', 'ask', 'You ask for the raise, with the offer letter in your bag'],
    [2, 'money', 'raise_yes', 'They meet you halfway, and add a title: senior designer'],
    [5, 'home', 'same_flat', 'Nothing moves: same flat, same Saturday run'],
    [7, 'work', 'restless', 'You catch yourself reading job listings on the streetcar', 'sourced', 'ev-stat-tenure'],
    [9, 'work', 'mentor', 'You start mentoring the new junior'],
    [11, 'work', 'leave', 'Three years on, you leave for a larger studio across town', 'sourced', 'ev-stat-tenure'],
  ],
}

const freelance: PathScript = {
  id: 'br-freelance', label: 'Go freelance', scenario: 'sc-job', option: 'op-freelance', forkedDaysAgo: 9, steps: THREE_YEARS, solid: [0.94, 0.58, 2.6],
  model: [
    ev('lean_months', 'you have at least one month with almost no income', 'money', 'usually', 'sourced', 'ev-freelance'),
    ev('first_client', 'Fieldnote becomes your first client', 'work', 'usually'),
    ev('earn_more', 'you out-earn your old salary by year two', 'money', 'sometimes', 'sourced', 'ev-freelance'),
    ev('back_to_job', 'you take a full-time job again within three years', 'work', 'as often as not'),
  ],
  beats: [
    [0, 'work', 'choice', 'You turn Vancouver down, and resign to work for yourself'],
    [1, 'work', 'first_client', 'Fieldnote keeps you on for two days a week'],
    [3, 'work', 'site', 'You put up a portfolio site and tell everyone you know'],
    [4, 'money', 'lean_months', 'A month with one small invoice; you borrow from savings', 'sourced', 'ev-freelance'],
    [6, 'work', 'retainer', 'A bakery chain signs you on a retainer'],
    [8, 'money', 'even', 'A year in, you have earned about what you did before'],
    [10, 'work', 'studio', 'You rent a desk in a shared studio on Geary'],
    [11, 'work', 'back_to_job', 'Three years on, a client offers you a full-time role, and you take it'],
  ],
}

const dinner: PathScript = {
  id: 'br-dinner', label: 'Go to Dana’s dinner', scenario: 'sc-friday', option: 'op-dinner', steps: A_WEEK, solid: [0.95, 0.66, 1.6],
  model: [
    ev('late_night', 'you are home after midnight', 'body', 'usually'),
    ev('deck_weekend', 'you finish the deck over the weekend', 'work', 'usually'),
    ev('pitch_ok', 'the pitch goes fine on Monday', 'work', 'usually'),
  ],
  beats: [
    [0, 'friends', 'choice', 'You close the laptop and go to Dana’s birthday dinner'],
    [0, 'body', 'late_night', 'Home after midnight, happy'],
    [1, 'work', 'deck_weekend', 'Saturday afternoon goes to the deck instead of the run'],
    [2, 'work', 'pitch_ok', 'The pitch goes fine. Nobody can tell which slides were Saturday’s'],
    [3, 'friends', 'thanks', 'Dana sends the photographs, and a thank-you'],
  ],
}

const deck: PathScript = {
  id: 'br-deck', label: 'Stay and finish the deck', scenario: 'sc-friday', option: 'op-deck', steps: A_WEEK, solid: [0.96, 0.72, 2.2],
  model: [
    ev('deck_done', 'the deck is done by Friday night', 'work', 'almost always'),
    ev('pitch_ok', 'the pitch goes fine on Monday', 'work', 'usually'),
    ev('dana_hurt', 'Dana is a little hurt', 'friends', 'as often as not'),
  ],
  beats: [
    [0, 'work', 'choice', 'You text Dana an apology and stay at your desk'],
    [0, 'work', 'deck_done', 'The deck is done by eleven'],
    [1, 'body', 'run', 'You make the Saturday run, rested'],
    [2, 'work', 'pitch_ok', 'The pitch goes well; the client asks for the file'],
    [3, 'friends', 'dana_hurt', 'Dana is friendly, and a little cool. You book a lunch to make it up'],
  ],
}

const signup: PathScript = {
  id: 'br-signup', label: 'Sign up', scenario: 'sc-race', option: 'op-signup', forkedDaysAgo: 21, steps: RACE, status: 'merged', solid: [0.96, 0.7, 2],
  model: [ev('train', 'you keep to the training plan most weeks', 'body', 'usually'), ev('finish', 'you finish the race', 'body', 'usually')],
  beats: [[0, 'body', 'choice', 'You sign up for the October half marathon'], [1, 'body', 'train', 'First long run of the plan'], [3, 'body', 'finish', 'You finish, slower than you hoped, and sign up for the next one']],
}
const skip: PathScript = {
  id: 'br-skip', label: 'Skip it this year', scenario: 'sc-race', option: 'op-skip', forkedDaysAgo: 21, steps: RACE, status: 'faded', solid: [0.95, 0.72, 2],
  model: [ev('regret', 'you wish you had signed up', 'mind', 'as often as not')],
  beats: [[0, 'body', 'choice', 'You let the sign-up deadline pass'], [3, 'mind', 'regret', 'You watch the club finish from the side of the road']],
}

export const demoBranches: BranchView[] = [signup, skip, vancouver, raise, freelance, dinner, deck].map(path)

export const demoScenarios: Scenario[] = [
  {
    id: 'sc-race', person_id: PERSON_ID, situation: 'Half marathon in October', created_at: iso(-21), status: 'decided', decided_branch_id: 'br-signup', horizon: { unit: 'months', count: 2 }, scale: 'small', questions: [], assuming_branch_id: null,
    options: [{ id: 'op-signup', title: 'Sign up', details: '', deadline: null }, { id: 'op-skip', title: 'Skip it this year', details: '', deadline: null }],
    branch_ids: ['br-signup', 'br-skip'],
  },
  {
    id: 'sc-job', person_id: PERSON_ID, situation: 'The Vancouver offer', created_at: iso(-9), status: 'open', decided_branch_id: null, horizon: { unit: 'years', count: 3 }, scale: 'big', assuming_branch_id: null,
    options: [
      { id: 'op-vancouver', title: 'Take the Vancouver job', details: '', deadline: iso(5) },
      { id: 'op-raise', title: 'Stay and ask for a raise', details: '', deadline: iso(5) },
      { id: 'op-freelance', title: 'Go freelance', details: '', deadline: null },
    ],
    branch_ids: ['br-vancouver', 'br-raise', 'br-freelance'],
    questions: [{ id: 'q-savings', scenario_id: 'sc-job', text: 'How many months of rent do you have saved?', why: 'It decides how long a lean stretch you can ride out', choices: ['under two', 'two to five', 'six or more'], applies_to: ['op-freelance', 'op-vancouver'], answer: null }],
  },
  {
    id: 'sc-friday', person_id: PERSON_ID, situation: 'Friday night', created_at: today, status: 'open', decided_branch_id: null, horizon: { unit: 'days', count: 7 }, scale: 'small', questions: [], assuming_branch_id: null,
    options: [{ id: 'op-dinner', title: 'Go to Dana’s dinner', details: '', deadline: null }, { id: 'op-deck', title: 'Stay and finish the deck', details: '', deadline: null }],
    branch_ids: ['br-dinner', 'br-deck'],
  },
]

// the one-in-a-thousand life, for the path that has one written
export const demoRare: Record<string, { rarity_words: string; years: BranchYear[] }> = {
  'br-dinner': {
    rarity_words: 'Fewer than one in a hundred of the simulated lives go this way.',
    years: path({
      ...dinner, suffix: '-rare', solid: [0.62, 0.6, 2],
      beats: [
        [0, 'friends', 'choice', 'You close the laptop and go to Dana’s birthday dinner'],
        [0, 'work', 'stranger', 'The person beside you turns out to run the company you are pitching on Monday'],
        [2, 'work', 'pitch_ok', 'The pitch is over in ten minutes. They had already decided at dinner'],
        [3, 'work', 'offer', 'They ask whether you would ever consider coming in-house'],
      ],
    }).years,
  },
}

// ---------------------------------------------------------------- evidence

const e = (id: string, branch_id: string | null, kind: Evidence['kind'], claim: string, rest: Partial<Evidence>): Evidence => ({
  id, branch_id, kind, claim, value: null, unit: null, source_title: '', source_url: null, retrieved_at: today, snippet: null, used_for: null, ...rest,
})

export const demoEvidence: Evidence[] = [
  e('ev-van-rent', 'br-vancouver', 'researched', 'A one-bedroom in Vancouver rents for noticeably more than a room in a shared Toronto flat.', {
    value: '2,650', unit: 'Canadian dollars a month, average one-bedroom (sample figure)', source_title: 'rentals.ca — national rent report', source_url: 'https://rentals.ca/',
    snippet: 'Vancouver remained the most expensive city for one-bedroom rentals…', used_for: 'Set how often the move raises your rent by a third or more.',
  }),
  e('ev-van-pay', 'br-vancouver', 'researched', 'Senior designers in Vancouver earn more than designers in Toronto at your level.', {
    value: '82,000', unit: 'Canadian dollars a year, median (sample figure)', source_title: 'Job Bank — wages, graphic designers, Lower Mainland', source_url: 'https://www.jobbank.gc.ca/',
    snippet: 'Median wage, Lower Mainland–Southwest region.', used_for: 'Set how often the new job pays more than the old one.',
  }),
  e('ev-freelance', 'br-freelance', 'researched', 'Most new freelancers report at least one month with little or no income in their first year.', {
    value: '6 in 10', unit: 'first-year freelancers reporting a month without income (sample figure)', source_title: 'Freelancers survey — income stability in the first year', source_url: 'https://www.freelancersunion.org/',
    snippet: 'Six in ten respondents reported at least one month without income…', used_for: 'Set how often a lean month arrives, and how often year two out-earns the old salary.',
  }),
  e('ev-stat-tenure', null, 'statistic', 'About one in six employed people aged 25 to 34 started their current job within the last year.', {
    value: '0.1697', unit: 'yearly chance of starting a new job, ages 25 to 34', source_title: 'Statistics Canada, table 14-10-0051-01 — job tenure, Labour Force Survey (2025)',
    source_url: 'https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1410005101', used_for: 'Sets how often a simulated life changes jobs, and so how often you are still in the same place after three years.',
  }),
  e('ev-me-club', null, 'personal', 'You joined a Saturday running club two years ago.', { source_title: 'Your log — told by you', snippet: 'Joins a Saturday running club' }),
  e('ev-me-promo', null, 'personal', 'You were promoted to designer at Fieldnote last year.', { source_title: 'Your log — from resume.pdf', snippet: 'Promoted to designer at Fieldnote' }),
]

// ---------------------------------------------------------------- chapters

type Para = [text: string, ...evidence: string[]]
const chapter = (p: PathScript, a: number, b: number, title: string, paras: Para[]): Chapter => {
  const fork = -(p.forkedDaysAgo ?? 0)
  const from = iso(fork + p.steps[a]); const to = iso(fork + p.steps[b])
  return { branch_id: p.id, revision: 1, from_year: +from.slice(0, 4), to_year: +to.slice(0, 4), from_at: from, to_at: to, title, status: 'ready', paragraphs: paras.map(([text, ...evidence_ids]) => ({ text, evidence_ids })) }
}

export const demoChapters: Chapter[] = [
  chapter(vancouver, 0, 3, 'Two suitcases', [
    ['You say yes on the phone, standing in the stairwell at Fieldnote so that nobody hears. It is the first time anyone has called you senior. You give notice the following week; your director says she saw it coming, and means it kindly.', 'ev-me-promo'],
    [`By ${on(21)} you are in a one-bedroom in Mount Pleasant with two suitcases and a borrowed air mattress. The rent is a third more than the Dovercourt flat was, for a place half the size, which is simply what Vancouver costs.`, 'ev-van-rent'],
  ]),
  chapter(vancouver, 4, 7, 'The grey months', [
    ['The first pay arrives and it is, as promised, more than you have earned before. You find a running club on the seawall within a month, because that is how you have always found people.', 'ev-van-pay', 'ev-me-club'],
    ['The first winter is grey, and lonelier than you expected. About half of the simulated versions of you feel this; the rain does not help. You call home on Sundays and do not mention it.'],
  ]),
  chapter(vancouver, 8, 11, 'Renewing the lease', [
    ['A year in, you lead your first client project, and discover you like it. By the second year most of your weekends belong to people you met here.'],
    ['Three years on, you renew the lease. It is close to a coin toss whether a life like this one is still in the same city by now: people your age change jobs often, and a job is usually what moves them.', 'ev-stat-tenure'],
  ]),
  chapter(raise, 0, 3, 'The offer letter in your bag', [
    ['You write to Vancouver first, so that you cannot change your mind, and then book half an hour with your director. You bring the offer letter and do not take it out.'],
    ['They meet you halfway on the money and add a title: senior designer. It is less than Vancouver offered and more than you had. You walk home down Dovercourt, past the same fruit stand, slightly taller.'],
  ]),
  chapter(raise, 4, 7, 'Same flat, same run', [
    ['Nothing moves, which is what you chose: the same flat, the same Saturday run, the same streetcar.', 'ev-me-club'],
    ['Around nine months in you catch yourself reading job listings on the way to work. That is ordinary. About one in six people your age start a new job in any given year, and most of them were reading listings first.', 'ev-stat-tenure'],
  ]),
  chapter(raise, 8, 11, 'Across town', [
    ['You start mentoring the new junior, who asks the questions you asked three years ago. Three years on, you leave for a larger studio across town. Staying bought you time; it did not change where this was heading.', 'ev-stat-tenure'],
  ]),
  chapter(freelance, 0, 3, 'Two days a week', [
    ['You turn Vancouver down and resign in the same week, which your sister calls brave and your mother calls something else. Fieldnote keeps you on for two days a week, so the first month looks almost like the old one.'],
    ['You put up a portfolio site and tell everyone you know. Two of them answer.'],
  ]),
  chapter(freelance, 4, 7, 'One small invoice', [
    ['Then comes a month with one small invoice. Most first-year freelancers have one; you borrow from savings and learn to chase payments without apologising.', 'ev-freelance'],
    ['In the spring a bakery chain signs you on a retainer: menus, bags, a van. It is not glamorous and it pays the rent.'],
  ]),
  chapter(freelance, 8, 11, 'A desk on Geary', [
    ['A year in, you have earned about what you did before, with more of it arriving late. You rent a desk in a shared studio on Geary so that work has a door.', 'ev-freelance'],
    ['Three years on, the bakery chain offers you a full-time role, and you take it. Roughly half of the simulated versions of this path end up employed again by now, most of them by choice.'],
  ]),
  chapter(dinner, 0, 1, 'Laptop closed', [
    ['You close the laptop at six with the deck two-thirds done, and go to Dana’s. It is a long table in a loud room and you are home after midnight, happy. The cost arrives on Saturday: the afternoon goes to slides instead of the run.'],
  ]),
  chapter(dinner, 2, 3, 'Monday', [
    ['The pitch goes fine. Nobody can tell which slides were Saturday’s. Dana sends the photographs later in the week, and a thank-you for coming.'],
  ]),
  chapter(deck, 0, 1, 'By eleven', [
    ['You text Dana an apology with too many exclamation marks and stay at your desk. The deck is done by eleven, properly done, and you make the Saturday run rested.', 'ev-me-club'],
  ]),
  chapter(deck, 2, 3, 'The lunch you owe', [
    ['The pitch goes well; the client asks for the file. Dana is friendly about Friday, and a little cool, which happens about as often as not. You book a lunch to make it up.'],
  ]),
  chapter(signup, 0, 3, 'October', [['You signed up. The plan is four runs a week, and you keep to most of it.', 'ev-me-club']]),
]

export const demoRareChapters: Chapter[] = [
  chapter(dinner, 0, 3, 'The person beside you', [
    ['This is the rarest coherent life among the thousand. You go to the dinner, and the person in the next chair turns out to run the company you are pitching on Monday. You talk about running, mostly.'],
    ['The pitch takes ten minutes. They had already decided at dinner. Later that week they ask whether you would ever consider coming in-house.'],
  ]),
]

// ---------------------------------------------------------------- research feed (played back offline)

export function demoResearch(branchLabel: string): ResearchStep[] {
  const at = new Date().toISOString()
  const step = (state: ResearchStep['state'], message: string, url: string | null = null): ResearchStep => ({ at, state, message, url, session_url: null })
  return [
    step('searching', `Working out what to look up for “${branchLabel}”`),
    step('reading', 'Reading: what it costs', 'https://rentals.ca/'),
    step('found', 'Found a figure, with the sentence it came from'),
    step('skipped', 'Skipped a page that wanted a sign-in'),
    step('done', 'Done. Simulated again with what was found.'),
  ]
}

export const demoInventory = {
  handles: [{ source: 'site', handle: 'https://samrivera.example' }],
  cached_pages: 1,
  sent_to_llm: ['The text of pages you pointed to', 'Your own words', 'Simulated event logs, to be written up'],
  stored_nowhere: ['Raw chat exports', 'Uploaded files', "Other people's names or messages", 'Passwords, cookies or logins of any kind'],
}

// ---------------------------------------------------------------- probabilities, and how each was made (sample values)

const WORD_P: Record<string, number> = { 'almost always': 0.93, usually: 0.74, 'as often as not': 0.49, sometimes: 0.27, rarely: 0.08 }
const logit = (x: number) => Math.log(x / (1 - x))
const expit = (x: number) => 1 / (1 + Math.exp(-x))

for (const view of demoBranches) {
  view.branch.model.events.forEach((m, n) => {
    const base = Math.min(0.97, Math.max(0.03, (WORD_P[m.words] ?? 0.5) + ((n % 3) - 1) * 0.04))
    const social = m.domain === 'friends' || m.domain === 'mind'
    const shift = social ? -0.12 : 0
    const adjusted = expit(logit(base) + shift)
    const simulated = Math.round(adjusted * 1000 - (n % 2 ? 7 : -5)) / 1000
    m.probability = simulated
    m.breakdown = {
      base: {
        kind: m.basis === 'sourced' ? 'sourced' : 'estimated', value: base, range: m.basis === 'estimated' ? [Math.max(0.02, base - 0.13), Math.min(0.98, base + 0.13)] : null,
        evidence_id: m.evidence_id, reference_class: m.basis === 'sourced' ? 'the group the source describes' : null,
        note: m.basis === 'sourced' ? 'Read from a published figure (a sample, offline).' : 'No published rate was found; drawn from this range.',
      },
      personality: shift === 0 ? [] : [{ trait: 'E', trait_name: 'extraversion', z: -0.4, confidence: 0.3, direction: -1, beta: 0.8, shift_logodds: shift, basis: 'assumed' }],
      dependencies: [], adjusted, simulated,
    }
  })
  view.branch.model.events.sort((a, b) => (b.probability ?? 0) - (a.probability ?? 0))
  for (const step of view.years) for (const m of view.branch.model.events) if (step.outlook[m.key]) step.outlook[m.key].probability = m.probability
}

// ---------------------------------------------------------------- the four measures, as change from now (sample values)

const EFFECTS: Record<string, Partial<Record<Measure, number>>> = {
  rent_up: { money: -1 }, raise: { money: 2 }, lonely: { joy: -2, health: -1 }, stay_3y: { fulfilment: 1 }, move_back: { joy: 1, money: -1 },
  raise_yes: { money: 1, joy: 1 }, same_flat: {}, restless: { fulfilment: -1 }, leave: { fulfilment: 1, money: 1 },
  lean_months: { money: -2, joy: -1 }, first_client: { money: 1 }, earn_more: { money: 2 }, back_to_job: { money: 1, fulfilment: -1 },
  late_night: { joy: 2, health: -1 }, deck_weekend: { joy: -1 }, pitch_ok: { fulfilment: 1 }, deck_done: { fulfilment: 1 }, dana_hurt: { joy: -1 },
  train: { health: 2 }, finish: { health: 1, fulfilment: 2 }, regret: { joy: -1 },
}
const MEASURE_LIST: Measure[] = ['health', 'joy', 'fulfilment', 'money']
const marksFor = (d: number): Marks => (d >= 2.2 ? '+++' : d >= 1.1 ? '++' : d >= 0.35 ? '+' : d <= -2.2 ? '−−−' : d <= -1.1 ? '−−' : d <= -0.35 ? '−' : '=')

for (const view of demoBranches) {
  for (const m of view.branch.model.events) {
    m.effects = { health: 0, joy: 0, fulfilment: 0, money: 0, ...(EFFECTS[m.key] ?? {}) }
    m.effects_basis = m.evidence_id && m.effects.money ? 'sourced' : 'judgement'
  }
  const running: Record<Measure, number> = { health: 0, joy: 0, fulfilment: 0, money: 0 }
  const series = Object.fromEntries(MEASURE_LIST.map((k) => [k, [] as { at: string; mean: number; low: number; high: number }[]])) as Record<Measure, { at: string; mean: number; low: number; high: number }[]>
  view.years.forEach((step, i) => {
    running.joy *= 0.55 // joy fades; the others accumulate
    for (const ev of step.events) {
      const fx = EFFECTS[ev.event_type] ?? {}
      const p = view.branch.model.events.find((x) => x.key === ev.event_type)?.probability ?? 1
      for (const k of MEASURE_LIST) running[k] += (fx[k] ?? 0) * p
    }
    const spread = 0.25 + i * 0.12
    for (const k of MEASURE_LIST) series[k].push({ at: step.at, mean: Math.round(running[k] * 100) / 100, low: Math.round((running[k] - spread) * 100) / 100, high: Math.round((running[k] + spread) * 100) / 100 })
  })
  const end = Object.fromEntries(MEASURE_LIST.map((k) => {
    const last = series[k][series[k].length - 1]
    return [k, { delta: last.mean, low: last.low, high: last.high, marks: marksFor(last.mean) }]
  })) as Record<Measure, { delta: number; low: number; high: number; marks: Marks }>
  const yearly: Record<string, number> = { 'br-vancouver': 17000, 'br-raise': 6000, 'br-freelance': -4000 }
  view.branch.measures = { series, end, money_end: yearly[view.branch.id] !== undefined ? { value: yearly[view.branch.id], low: yearly[view.branch.id] - 9000, high: yearly[view.branch.id] + 9000, currency: 'CAD' } : null }
}
demoPerson.money = { income: 62000, net_worth: 9000, currency: 'CAD' }
