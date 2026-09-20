// The offline demo: one scripted story, played back by fixtureApi.ts. Nothing here is loaded for a real person.
//
//   Rohan, 22, computer science, 5'10" (177.8 cm), interned at a large software company, builds developer tools.
//   He is at a hackathon and likes a girl there. He asks what to do and gives three options:
//   talk to her, follow her around, bury it. Hereafter answers with probabilities and expected values.
//
// The maths is real (decision.ts). What is *published* below carries the source and the sentence as it was read;
// everything else is labelled "assumption". The profile ("background check") is sample data, and the loading
// animation that precedes it is scripted, not a scrape. It uses only Rohan's own accounts and knows nothing about her
// beyond what his answers say.

import type { AnalysisView, Basis, PathSummary, Reason, BranchView, Marks, Measure, BranchYear, Chapter, Domain, Evidence as EvidenceDoc, LifeEvent, Outlook, Person, PossibleEvent, Question, ResearchStep, Scenario, StateVector } from '../types'
import { ACTIONS, LABEL, PAYOFF, RESPONDS, analyse, type Action, type Analysis, type Evidence, type Source } from './decision'

const PERSON_ID = 'offline'
export const THIS_YEAR = new Date().getFullYear()

const DAY = 86_400_000
const MONTHS_LONG = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
const iso = (daysFromNow: number) => new Date(Date.now() + daysFromNow * DAY).toISOString().slice(0, 10)
const on = (n: number) => {
  const d = new Date(Date.now() + n * DAY)
  return `${d.getDate()} ${MONTHS_LONG[d.getMonth()]}`
}
const today = iso(0)

export const demoPerson: Person = { id: PERSON_ID, display_name: 'Rohan', birth_year: THIS_YEAR - 22, sex: null, personality: null }

export const demoState: StateVector = {
  year: THIS_YEAR, age: 22, city: 'Waterloo', education: 'in a computer science degree', field: 'software', employment: 'student',
  income_band: 'lower_middle', relationship_status: 'single', housing: 'renting', activity_proxy: 0.6, children: 0, alive: true,
}

/** What the composer types for the presenter when they press Enter on an empty box. */
export const DEMO_SCRIPT = {
  decision: 'I like this girl at hackathon. What should I do?',
  paths: ['Talk to her', 'Follow her around', 'Bury your feelings and forget about it'],
}

/** The "background check": each fact with the account it came from. Sample data. */
export const demoProfile: { from: 'linkedin' | 'github' | 'instagram' | null; text: string }[] = [
  { from: 'linkedin', text: 'Interned at a large software company for four months' },
  { from: 'github', text: 'Builds and open-sources developer tools; second place at a hackathon' },
  { from: 'instagram', text: 'Climbs twice a week and travels when he can' },
  { from: null, text: '5′10″ (177.8 cm), about average for a man his age' },
]

function mainEvent(n: number, date: string, domain: Domain, event_type: string, text: string, origin: string): LifeEvent {
  const source = origin === 'your words' ? 'told' : 'scraped'
  return { id: `main-${n}`, person_id: PERSON_ID, source, branch_id: 'main', date, domain, event_type, payload: {}, confidence: source === 'told' ? 1 : 0.8, text, origin }
}

export const demoTrunkEvents: LifeEvent[] = [
  mainEvent(1, `${THIS_YEAR - 4}-09-05`, 'learning', 'education', 'Starts computer science at university', 'resume.pdf'),
  mainEvent(2, `${THIS_YEAR - 2}-05-06`, 'work', 'job_start', 'Software engineering internship at a large software company', 'linkedin.com'),
  mainEvent(3, `${THIS_YEAR - 1}-06-20`, 'work', 'project', 'Open-sources a small developer tool; it reaches 200 stars', 'github.com'),
  mainEvent(4, `${THIS_YEAR - 1}-11-10`, 'friends', 'hackathon', 'Takes second place at a weekend hackathon with two friends', 'github.com'),
  mainEvent(5, iso(-40), 'body', 'habit', 'Starts climbing twice a week', 'instagram.com'),
  mainEvent(6, iso(-2), 'work', 'hackathon', 'Arrives at this weekend’s hackathon', 'your words'),
]

// ---------------------------------------------------------------- the three lives

type Beat = [step: number, domain: Domain, key: string, text: string, basis?: Basis, evidence?: string]
type Steps = number[] // days after the fork

interface PathScript {
  id: string
  label: string
  scenario: string
  option: string
  steps: Steps
  solid: [from: number, floor: number, halfLife: number]
  model: PossibleEvent[]
  beats: Beat[] // the first beat is always the choice itself
}

function path(o: PathScript): BranchView {
  const happened = new Set<string>()
  const years: BranchYear[] = o.steps.map((days, i) => {
    const at = iso(days)
    const events: LifeEvent[] = o.beats.filter((b) => b[0] === i).map(([, domain, key, text, basis, evidence], n) => {
      happened.add(key)
      const head = i === 0 && n === 0
      return {
        id: `${o.id}-${i}-${key}`, person_id: PERSON_ID, source: 'simulated' as const, branch_id: o.id, date: at, domain, event_type: key,
        payload: { basis: head ? 'background' : (basis ?? 'estimated'), ...(evidence ? { evidence_id: evidence } : {}), ...(head ? { head: true } : {}) },
        confidence: 0.8, text, ...(head ? { head: true } : {}),
      }
    })
    const solidity = Math.round((o.solid[1] + (o.solid[0] - o.solid[1]) * Math.pow(0.5, i / o.solid[2])) * 1000) / 1000
    const outlook: Outlook = {}
    for (const e of o.model) outlook[e.key] = { value: happened.has(e.key) ? 'yes' : 'not yet', share: solidity, words: e.words }
    return { year: +at.slice(0, 4), at, label: on(days), solidity, state: demoState, events, outlook }
  })
  return {
    branch: {
      id: o.id, person_id: PERSON_ID, label: o.label, forked_at: iso(0), assumption: {}, precondition: null, status: 'open', carried_event_id: null,
      scenario_id: o.scenario, option_id: o.option, commits: [], research: 'done', revision: 1, model: { events: o.model }, forming: false,
    },
    years,
  }
}

const ev = (key: string, label: string, domain: string, words: string, basis: Basis = 'estimated', evidence_id: string | null = null): PossibleEvent => ({ key, label, domain, basis, evidence_id, words })

/** a month, mostly the first days */
const A_MONTH: Steps = [0, 1, 2, 5, 14, 30]
export const HACK = 'sc-hack'

const talk: PathScript = {
  id: 'br-talk', label: 'Talk to her', scenario: HACK, option: 'op-talk', steps: A_MONTH, solid: [0.96, 0.7, 3],
  model: [
    ev('replies', 'she talks with you', 'friends', 'usually', 'sourced', 'ev-ask'),
    ev('coffee', 'she says yes to a coffee', 'friends', 'as often as not'),
    ev('declines', 'she politely says no', 'mind', 'sometimes'),
    ev('date', 'it turns into a real date', 'friends', 'sometimes'),
  ],
  beats: [
    [0, 'friends', 'choice', 'You walk over between sessions and say hi'],
    [0, 'friends', 'replies', 'She answers, and you talk about her project for ten minutes', 'sourced', 'ev-ask'],
    [1, 'friends', 'coffee', 'You ask if she wants a coffee before the demos, and she says yes'],
    [2, 'work', 'demo', 'You watch her team demo, and she finds you in the crowd afterwards'],
    [5, 'friends', 'message', 'You message her the next day about an idea for her project'],
    [14, 'friends', 'date', 'A second coffee turns into dinner'],
    [30, 'mind', 'known', 'Whatever comes of it, you know instead of wondering'],
  ],
}

const askOut: PathScript = {
  id: 'br-ask', label: 'Ask her out', scenario: HACK, option: 'op-ask', steps: A_MONTH, solid: [0.95, 0.66, 3],
  model: [
    ev('says_yes', 'she says yes', 'friends', 'as often as not', 'sourced', 'ev-ask-out'),
    ev('kind_no', 'she kindly says no', 'mind', 'as often as not'),
    ev('sting', 'it stays a little awkward for the weekend', 'mind', 'sometimes'),
    ev('dinner', 'you go out for food together', 'friends', 'as often as not'),
  ],
  beats: [
    [0, 'friends', 'choice', 'You ask if she would like to get food after the demos'],
    [0, 'friends', 'says_yes', 'She smiles, a little surprised, and says yes', 'sourced', 'ev-ask-out'],
    [1, 'friends', 'dinner', 'You end up talking until the venue closes'],
    [2, 'work', 'demo', 'You watch each other’s demos from the front'],
    [5, 'friends', 'message', 'She messages you first the next day'],
    [14, 'friends', 'seeing', 'You see each other again the following weekend'],
    [30, 'mind', 'known', 'Whatever comes of it, you asked, and you know'],
  ],
}

const follow: PathScript = {
  id: 'br-follow', label: 'Follow her around', scenario: HACK, option: 'op-follow', steps: A_MONTH, solid: [0.95, 0.72, 3],
  model: [
    ev('noticed', 'she notices and is uncomfortable', 'friends', 'almost always'),
    ev('steps_in', 'an organizer steps in', 'work', 'usually', 'sourced', 'ev-law'),
    ev('regret', 'you regret it for weeks', 'mind', 'usually'),
    ev('shut_out', 'her team shuts you out', 'friends', 'usually'),
  ],
  beats: [
    [0, 'work', 'choice', 'You start trailing her around the venue'],
    [1, 'friends', 'noticed', 'She notices you at the third session and moves to another table'],
    [2, 'work', 'steps_in', 'An organizer asks you to give her space', 'sourced', 'ev-law'],
    [5, 'mind', 'regret', 'You replay it for days and avoid the group photo'],
    [14, 'friends', 'shut_out', 'Her team blocks you in their chat'],
    [30, 'work', 'talk', 'The story goes around your program'],
  ],
}

const bury: PathScript = {
  id: 'br-bury', label: 'Bury your feelings and forget about it', scenario: HACK, option: 'op-bury', steps: A_MONTH, solid: [0.97, 0.8, 4],
  model: [
    ev('relief', 'you feel relieved not to have risked it', 'mind', 'usually'),
    ev('wonder', 'you keep wondering what would have happened', 'mind', 'as often as not', 'sourced', 'ev-regret'),
    ev('lingers', 'it still comes back a month later', 'mind', 'sometimes', 'sourced', 'ev-regret'),
  ],
  beats: [
    [0, 'mind', 'choice', 'You keep your head down and code'],
    [1, 'work', 'ship', 'You finish your project, and the team is happy with it'],
    [2, 'mind', 'relief', 'At the demos you see her across the room and look away'],
    [5, 'mind', 'wonder', 'On the walk home you wonder what would have happened', 'sourced', 'ev-regret'],
    [14, 'mind', 'tab', 'You keep her project page open in a tab'],
    [30, 'mind', 'lingers', 'A month on, it still comes back at odd moments', 'sourced', 'ev-regret'],
  ],
}

/** In the order of ACTIONS (talk, ask, follow, bury): the fixture picks a life by that index. */
export const demoBranches: BranchView[] = [talk, askOut, follow, bury].map(path)

// ---------------------------------------------------------------- sources: published (with the sentence read) or assumption

export const SOURCES: Source[] = [
  {
    id: 'speed', kind: 'published', claim: 'When people who chose to attend speed-dating events meet partners, each sex says yes to about half of them.',
    cite: 'Fisman, Iyengar, Kamenica & Simonson (2006), Quarterly Journal of Economics 121(2)', url: 'https://academic.oup.com/qje/article-abstract/121/2/673/1884033',
    quote: 'subjects of each gender saying Yes to about half of their partners',
  },
  {
    id: 'ask', kind: 'published', claim: 'People asking for something overestimate how many others they will have to ask before one says yes.',
    cite: 'Flynn & Lake (2008), Journal of Personality and Social Psychology, via Stanford GSB', url: 'https://www.gsb.stanford.edu/insights/francis-flynn-if-you-want-something-ask-it',
    quote: 'participants consistently overestimated by 50 percent the number of people they’d have to ask',
  },
  {
    id: 'height', kind: 'published', claim: 'The average measured height of a Canadian man aged 20 to 39 is 177.70 cm, which is 5′10″.',
    cite: 'Statistics Canada, Canadian Health Measures Survey (2009 to 2011), table 22', url: 'https://www150.statcan.gc.ca/n1/pub/82-626-x/2012001/t023-eng.htm',
    quote: '177.70 (95% CI 176.52 to 178.87)',
  },
  {
    id: 'law', kind: 'published', claim: 'Repeatedly following someone from place to place can be criminal harassment in Canada.',
    cite: 'Criminal Code (Canada), section 264', url: 'https://laws-lois.justice.gc.ca/eng/acts/c-46/section-264.html',
    quote: 'repeatedly following from place to place the other person or anyone known to them … an indictable offence and liable to imprisonment for a term of not more than 10 years',
  },
  {
    id: 'regret', kind: 'published', claim: 'Recent regrets are about what people did; long-term regrets are about what they did not do. A replication confirmed this in general but not in every detail.',
    cite: 'A very public replication of the temporal pattern to people’s regrets (Royal Society Open Science, 2023); after Gilovich & Medvec', url: 'https://pmc.ncbi.nlm.nih.gov/articles/PMC10282588/',
    quote: 'regrets of recent vintage tend to centre on mistakes of action, but long-term regrets tend to involve failures to act',
  },
  {
    id: 'similar', kind: 'published', claim: 'People tend to prefer partners who are similar to them, and status and income matter to who is contacted. Cited for direction only: no figure from it is used.',
    cite: 'Hitsch, Hortaçsu & Ariely (2010), Quantitative Marketing and Economics 8, 393–427', url: 'https://link.springer.com/article/10.1007/s11129-010-9088-6',
  },
  {
    id: 'inputs', kind: 'assumption', claim: 'The starting probability, every likelihood ratio, the payoffs and the chance she talks back are demo inputs, not measurements. Change them and the answer changes.',
    cite: 'Demo assumptions', url: '',
  },
]

const S = (id: string) => SOURCES.find((x) => x.id === id)!

// ---------------------------------------------------------------- evidence, and the two questions

/** From the background check. Each is a likelihood ratio: how many times likelier it is if she is interested than if not. */
export const BACKGROUND: Evidence[] = [
  { id: 'height', label: '5′10″ (177.8 cm)', from: 'your profile', lr: 1.0, kind: 'assumption', short: '5′10″ is average for men your age',
    why: 'This is the average for Canadian men of your age (177.70 cm, Statistics Canada), so it neither helps nor hurts.' },
  { id: 'company', label: 'Worked at a large software company', from: 'LinkedIn', lr: 1.1, kind: 'assumption', short: 'You worked at a large company',
    why: 'Status and income affect who gets contacted in online-dating data (Hitsch et al.). The size of the nudge is assumed.' },
  { id: 'shared', label: 'You are both at the same hackathon', from: 'GitHub', lr: 1.15, kind: 'assumption', short: 'You are at the same hackathon',
    why: 'A shared place and interests: people prefer similar partners (Hitsch et al.). The size is assumed.' },
]

export interface AnswerRule { lr: number; why: string }

/** The two questions, and what each answer does to the odds. All ratios are demo assumptions. */
export const QUESTIONS: { id: string; text: string; why: string; choices: { text: string; lr: number; label: string }[] }[] = [
  {
    id: 'q-eyes', text: 'Has she made eye contact or smiled at you?', why: 'It is the best evidence you have. Your answer changes the odds more than anything on your profile.',
    choices: [
      { text: 'Yes, more than once', lr: 3, label: 'She made eye contact or smiled more than once' },
      { text: 'Maybe once', lr: 1.5, label: 'She may have made eye contact once' },
      { text: 'No, not really', lr: 0.6, label: 'She has not really looked your way' },
    ],
  },
  {
    id: 'q-partner', text: 'Does she seem to be there with a partner?', why: 'If she is, the odds fall a long way, and that can change what is best.',
    choices: [
      { text: 'No, she seems to be on her own', lr: 1, label: 'She seems to be on her own' },
      { text: 'Not sure', lr: 0.8, label: 'You are not sure whether she is with someone' },
      { text: 'Yes, she seems to be with someone', lr: 0.1, label: 'She seems to be with someone' },
    ],
  },
]

/** The questions as a scenario carries them (unanswered). */
export const demoQuestions = (scenarioId: string, optionIds: string[]): Question[] =>
  QUESTIONS.map((q) => ({ id: `${q.id}-${scenarioId}`, scenario_id: scenarioId, text: q.text, why: q.why, choices: q.choices.map((c) => c.text), applies_to: [...optionIds], answer: null }))

const pct = (x: number) => `${Math.round(x * 100)}%`

/** What to say about each life, in plain words, from the current numbers. */
function pathSummaries(a: Analysis): Record<Action, PathSummary> {
  const p = a.p
  const best = a.recommended
  const t = a.thresholds
  const talkReasons: Reason[] = [
    { text: `${pct(p)} chance she’s interested`, effect: p >= t.talk ? 'up' : 'down', note: p >= t.talk ? `above the ${pct(t.talk)} where a chat pays` : `below the ${pct(t.talk)} where a chat pays` },
    { text: 'If she isn’t interested', effect: 'none', note: 'you lose almost nothing: it’s just a conversation' },
    { text: 'If she is', effect: 'up', note: 'it opens the door, and you can ask her out after' },
    { text: 'People expect more refusals than they get', effect: 'up', note: 'published finding' },
  ]
  const askReasons: Reason[] = [
    { text: `${pct(p)} chance she’s interested`, effect: p >= t.ask ? 'up' : 'down', note: p >= t.ask ? `above the ${pct(t.ask)} where asking pays` : `below the ${pct(t.ask)} where asking pays` },
    { text: 'If she says yes', effect: 'up', note: 'you get a date, the best outcome here' },
    { text: 'If she says no', effect: 'down', note: 'it stings and stays a little awkward all weekend' },
    { text: 'A chat first would tell you more', effect: p >= t.askOverTalk ? 'none' : 'down', note: p >= t.askOverTalk ? `you’re past the ${pct(t.askOverTalk)} where asking beats it` : `asking beats it only above ${pct(t.askOverTalk)}` },
  ]
  const followReasons: Reason[] = [
    { text: 'If she’s interested', effect: 'down', note: 'it still puts her off' },
    { text: 'If she isn’t', effect: 'down', note: 'it’s worse: she notices and is uncomfortable' },
    { text: 'The law', effect: 'down', note: 'repeatedly following someone can be criminal harassment' },
  ]
  const buryReasons: Reason[] = [
    { text: 'Nothing can go wrong', effect: 'up', note: 'a small, sure result' },
    { text: 'You may wonder for a long time', effect: 'down', note: 'regrets about not acting last longer (published)' },
    { text: `If she is interested (${pct(p)})`, effect: 'down', note: 'you miss it' },
  ]
  return {
    talk: {
      stat: pct(a.responds), of: 'chance she talks with you',
      pick: best === 'talk' ? 'Best first step' : best === 'ask' ? 'A good, gentle start' : 'Not worth it yet',
      why: best === 'talk'
        ? `It’s the gentlest way in: little to lose, and it shows you where you stand (about ${pct(p)} chance she’s interested). Ask her out once there’s a clearer sign.`
        : best === 'ask'
          ? `Low risk and worth doing, but at about ${pct(p)} chance she’s interested, asking her out directly is worth more.`
          : `With only about ${pct(p)} chance she’s interested, even a friendly chat isn’t worth it yet.`,
      reasons: talkReasons,
    },
    ask: {
      stat: pct(a.saysYes), of: 'chance she says yes',
      pick: best === 'ask' ? 'Worth asking' : best === 'talk' ? 'A bit early' : 'Not now',
      why: best === 'ask'
        ? `At about ${pct(p)} chance she’s interested it’s worth the risk: a date if she is, a small sting if not.`
        : best === 'talk'
          ? `At about ${pct(p)} it’s early: asking straight out only pays above about ${pct(t.askOverTalk)}. Talk first, then ask once you see a sign.`
          : `Below about ${pct(t.ask)} the sting isn’t worth the risk.`,
      reasons: askReasons,
    },
    follow: {
      stat: '0%', of: 'chance it leaves you better off', pick: 'Don’t',
      why: 'It loses whether she’s interested or not, and repeatedly following someone can be criminal harassment.',
      reasons: followReasons,
    },
    bury: {
      stat: '100%', of: 'chance you’re no worse off, but only just', pick: best === 'bury' ? 'Safe, and right for now' : 'Safe, but it lingers',
      why: best === 'bury'
        ? `At about ${pct(p)} chance she’s interested, a small sure thing beats a long shot. Waiting for a clearer sign costs nothing.`
        : 'It never goes wrong, but it never goes right either, and what you didn’t do tends to stay with you longer than what you did.',
      reasons: buryReasons,
    },
  }
}

/** Which scripted life an option is about, read from its words: following, burying it, asking her out, or (by default) just talking. */
export const lifeFor = (title: string): Action => {
  const t = title.toLowerCase()
  if (/\b(follow|stalk|trail|chase|shadow|creep)/.test(t)) return 'follow'
  if (/\b(bury|forget|ignore|suppress|nothing|feelings|move on|let it go|drop it|hide)/.test(t)) return 'bury'
  if (/\bask(ing)? (her )?(out|for her|to (dinner|lunch|coffee|go))|\btake her out|\binvite|\bdate\b|\bdinner\b|\bpropose/.test(t)) return 'ask'
  return 'talk'
}

const cap = (t: string) => t.charAt(0).toUpperCase() + t.slice(1)

/** How a ratio reads in plain words. */
const noteFor = (lr: number) => (lr === 1 ? 'no effect' : lr >= 2 ? 'raises it a lot' : lr > 1 ? 'nudges it up' : lr <= 0.5 ? 'lowers it a lot' : 'lowers it a little')

/** The analysis for a decision given the answers so far. `answers` maps a question id (without the scenario suffix) to the choice text;
 *  `titles` is the person's own wording for each life, so the summary speaks in their words. */
export function analysisFor(answers: Record<string, string>, titles: Partial<Record<Action, string>> = {}): AnalysisView {
  const steps: Evidence[] = [...BACKGROUND]
  for (const q of QUESTIONS) {
    const given = answers[q.id]
    const choice = q.choices.find((c) => c.text === given)
    if (choice) steps.push({ id: q.id, label: choice.label, from: 'your answer', lr: choice.lr, kind: 'assumption', short: choice.label, why: 'You told me this; the size of its effect is a demo assumption.' })
  }
  const a = analyse(steps)
  const final = QUESTIONS.every((q) => answers[q.id])
  const t = a.thresholds
  const headline = a.recommended === 'talk' ? cap(titles.talk ?? 'Talk to her') : a.recommended === 'ask' ? cap(titles.ask ?? 'Ask her out') : 'Don’t approach her yet'
  const why = a.recommended === 'talk'
    ? `Start with a chat: it’s worth doing once there’s a ${pct(t.talk)} chance she’s interested, and you’re at ${pct(a.p)}. Asking her out directly needs about ${pct(t.askOverTalk)}. Following her loses either way.`
    : a.recommended === 'ask'
      ? `At ${pct(a.p)}, asking her out is worth more than a chat (it pays above ${pct(t.askOverTalk)}). If she’s interested you get a date; if not, it stings for a bit. Following her loses either way.`
      : `Below ${pct(t.talk)} the risk isn’t worth it, and you are at ${pct(a.p)}. Staying quiet is a small, sure thing. Following her is worse than both.`
  return {
    ...a,
    payoff: PAYOFF,
    final,
    headline,
    why,
    reasons: steps.map((s) => ({ text: s.short ?? s.label, effect: s.lr > 1 ? 'up' : s.lr < 1 ? 'down' : 'none', note: noteFor(s.lr) })),
    byPath: pathSummaries(a),
    paths: {},
    titles,
    sources: SOURCES,
    respondsInputs: RESPONDS,
    labels: Object.fromEntries(ACTIONS.map((x) => [x, LABEL[x]])) as AnalysisView['labels'],
  }
}

// ---------------------------------------------------------------- the paths' own evidence, chapters, research feed

const e = (id: string, branch_id: string | null, kind: EvidenceDoc['kind'], claim: string, rest: Partial<EvidenceDoc>): EvidenceDoc => ({
  id, branch_id, kind, claim, value: null, unit: null, source_title: '', source_url: null, retrieved_at: today, snippet: null, used_for: null, ...rest,
})

export const demoEvidence: EvidenceDoc[] = [
  e('ev-ask', 'br-talk', 'researched', 'People who ask directly are told yes more often than they expect.', {
    value: '50%', unit: 'overestimate of how many people the asker thought they would have to ask', source_title: 'Flynn & Lake (2008), Journal of Personality and Social Psychology', source_url: S('ask').url,
    snippet: S('ask').quote ?? null, used_for: 'Set how likely it is that she at least talks with you when you go over.',
  }),
  e('ev-ask-out', 'br-ask', 'researched', 'People who ask directly are told yes more often than they expect.', {
    value: '50%', unit: 'overestimate of how many people the asker thought they would have to ask', source_title: 'Flynn & Lake (2008), Journal of Personality and Social Psychology', source_url: S('ask').url,
    snippet: S('ask').quote ?? null, used_for: 'Set how likely it is that she says yes when you ask.',
  }),
  e('ev-law', 'br-follow', 'researched', 'Repeatedly following someone from place to place can be criminal harassment in Canada.', {
    value: '10 years', unit: 'the most an indictable conviction can carry', source_title: 'Criminal Code (Canada), section 264', source_url: S('law').url,
    snippet: S('law').quote ?? null, used_for: 'Set how likely it is that someone steps in, and how heavy the downside of following is.',
  }),
  e('ev-regret', 'br-bury', 'researched', 'Regrets about what you did fade; regrets about what you did not do tend to last.', {
    source_title: 'A very public replication of the temporal pattern to people’s regrets (Royal Society Open Science, 2023)', source_url: S('regret').url,
    snippet: S('regret').quote ?? null, used_for: 'Set how often the wondering lingers, and why doing nothing is not a free choice.',
  }),
  e('ev-height', null, 'statistic', 'A man of 5′10″ is about the average height for his age group in Canada.', {
    value: '177.70', unit: 'cm, mean measured height, men 20 to 39', source_title: 'Statistics Canada, Canadian Health Measures Survey, table 22', source_url: S('height').url,
    snippet: S('height').quote ?? null, used_for: 'Why your height moves the odds by nothing.',
  }),
  e('ev-speed', null, 'statistic', 'Speed daters said yes to about half of the people they met.', {
    source_title: 'Fisman, Iyengar, Kamenica & Simonson (2006), Quarterly Journal of Economics', source_url: S('speed').url,
    snippet: S('speed').quote ?? null, used_for: 'An upper reference for the starting probability. A stranger at a hackathon is not a self-selected speed dater, so the demo starts lower.',
  }),
]

type Para = [text: string, ...evidence: string[]]
const chapter = (p: PathScript, a: number, b: number, title: string, paras: Para[]): Chapter => ({
  branch_id: p.id, revision: 1, from_year: +iso(p.steps[a]).slice(0, 4), to_year: +iso(p.steps[b]).slice(0, 4), from_at: iso(p.steps[a]), to_at: iso(p.steps[b]), title, status: 'ready',
  paragraphs: paras.map(([text, ...evidence_ids]) => ({ text, evidence_ids })),
})

export const demoChapters: Chapter[] = [
  chapter(talk, 0, 3, 'Hi', [
    ['You wait until the next break, walk over, and say hi before you can talk yourself out of it. Most people asked something directly answer, and she does. You end up talking about her project for ten minutes.', 'ev-ask'],
    ['The cost of the attempt was a few seconds of nerves. Asking is easier than it feels from where you are standing.'],
  ]),
  chapter(talk, 4, 5, 'Whatever happens next', [
    ['A second coffee turns into dinner. It might not have. About as often as not she would say no, politely, and you would be exactly where you started but without the wondering.'],
  ]),
  chapter(askOut, 0, 3, 'A question', [
    ['You pick a quiet moment after the demos and ask, plainly, if she would like to get food. It takes about four seconds and feels much longer. Most people asked directly say yes more often than the person asking expects.', 'ev-ask-out'],
    ['If she is interested, this is the best thing you can do. If she isn’t, it stings for an evening, and the weekend is a little awkward.'],
  ]),
  chapter(askOut, 4, 5, 'The next weekend', [
    ['She messages first. You see each other again. Whatever comes of it, you asked: you don’t have to guess at what the answer would have been.'],
  ]),
  chapter(follow, 0, 3, 'Space', [
    ['You tell yourself you are only staying nearby. By the third session she has moved to a different table, and an organizer asks you, kindly, to give her some room.', 'ev-law'],
    ['Whether or not she was interested, this could not have gone well. Repeatedly following someone is the one option here that loses in both worlds.'],
  ]),
  chapter(follow, 4, 5, 'The group photo', [
    ['You avoid the group photo and the chat you were in. The story goes around, in the version where you are the villain.'],
  ]),
  chapter(bury, 0, 3, 'Head down', [
    ['You put your head down and finish the project, and it is good. At the demos you see her across the room and look away.'],
    ['It feels like the safe choice, and in the short run it is: nothing can go wrong. That is exactly why it feels so good.'],
  ]),
  chapter(bury, 4, 5, 'The open tab', [
    ['A month on, her project page is still open in a tab. People tend to regret what they did not do more, and for longer, than what they did.', 'ev-regret'],
  ]),
]

export const demoRare: Record<string, { rarity_words: string; years: BranchYear[] }> = {}
export const demoRareChapters: Chapter[] = []
export const demoScenarios: Scenario[] = []

/** What each path reads while its research plays back: real sources, in the order they are read. */
const RESEARCH: Record<string, [state: ResearchStep['state'], message: string, url?: string][]> = {
  'br-talk': [
    ['found', 'Looked in your own log first: four things that bear on this'],
    ['reading', 'Reading: how often people say yes when asked directly', S('ask').url],
    ['found', 'Found a figure, with the sentence it came from'],
    ['reading', 'Reading: how tall men usually are at your age', S('height').url],
    ['found', 'Found a figure, with the sentence it came from'],
  ],
  'br-ask': [
    ['found', 'Looked in your own log first: four things that bear on this'],
    ['reading', 'Reading: how often people say yes when asked directly', S('ask').url],
    ['found', 'Found a figure, with the sentence it came from'],
    ['reading', 'Reading: how often people say yes to a date', S('speed').url],
    ['found', 'Found a figure, with the sentence it came from'],
  ],
  'br-follow': [
    ['found', 'Looked in your own log first: four things that bear on this'],
    ['reading', 'Reading: what the law says about following someone', S('law').url],
    ['found', 'Found the wording, and the penalty'],
    ['skipped', 'Skipped a forum thread that would not load', 'https://www.reddit.com/'],
  ],
  'br-bury': [
    ['found', 'Looked in your own log first: four things that bear on this'],
    ['reading', 'Reading: how long regrets about not acting last', S('regret').url],
    ['found', 'Found the finding, with the sentence it came from'],
    ['reading', 'Reading: how often people say yes to a date', S('speed').url],
    ['found', 'Found a figure, with the sentence it came from'],
  ],
}

export function demoResearch(templateId: string, branchLabel: string): ResearchStep[] {
  const at = new Date().toISOString()
  const step = (state: ResearchStep['state'], message: string, url: string | null = null): ResearchStep => ({ at, state, message, url, session_url: null })
  return [
    step('searching', `Working out what to look up for “${branchLabel}”`),
    ...(RESEARCH[templateId] ?? RESEARCH['br-talk']).map(([state, message, url]) => step(state, message, url ?? null)),
    step('done', 'Done. Simulated again with what was found.'),
  ]
}

export const demoInventory = {
  handles: [] as { source: string; handle: string }[],
  cached_pages: 0,
  sent_to_llm: ['The text of pages you pointed to', 'Your own words', 'Simulated event logs, to be written up'],
  stored_nowhere: ['Raw chat exports', 'Uploaded files', "Other people's names or messages", 'Passwords, cookies or logins of any kind'],
}

// ---------------------------------------------------------------- probabilities and the four measures on each path (sample values)

const WORD_P: Record<string, number> = { 'almost always': 0.93, usually: 0.74, 'as often as not': 0.49, sometimes: 0.27, rarely: 0.08 }
const logit = (x: number) => Math.log(x / (1 - x))
const expit = (x: number) => 1 / (1 + Math.exp(-x))

for (const view of demoBranches) {
  view.branch.model.events.forEach((m, n) => {
    const base = Math.min(0.97, Math.max(0.03, (WORD_P[m.words] ?? 0.5) + ((n % 3) - 1) * 0.03))
    const adjusted = expit(logit(base))
    const simulated = Math.round(adjusted * 1000 - (n % 2 ? 6 : -4)) / 1000
    m.probability = simulated
    m.breakdown = {
      base: {
        kind: m.basis === 'sourced' ? 'sourced' : 'estimated', value: base, range: m.basis === 'estimated' ? [Math.max(0.02, base - 0.13), Math.min(0.98, base + 0.13)] : null,
        evidence_id: m.evidence_id, reference_class: m.basis === 'sourced' ? 'the group the source describes' : null,
        note: m.basis === 'sourced' ? 'Read from a published source (a sample, offline).' : 'No published rate was found; drawn from this range.',
      },
      personality: [], dependencies: [], adjusted, simulated,
    }
  })
  view.branch.model.events.sort((a, b) => (b.probability ?? 0) - (a.probability ?? 0))
  for (const step of view.years) for (const m of view.branch.model.events) if (step.outlook[m.key]) step.outlook[m.key].probability = m.probability
}

const EFFECTS: Record<string, Partial<Record<Measure, number>>> = {
  replies: { joy: 2, fulfilment: 1 }, coffee: { joy: 2 }, declines: { joy: -1 }, date: { joy: 2, fulfilment: 2 },
  noticed: { joy: -2 }, steps_in: { joy: -2, fulfilment: -1 }, regret: { joy: -2, fulfilment: -1 }, shut_out: { joy: -1, fulfilment: -1 },
  says_yes: { joy: 3, fulfilment: 2 }, kind_no: { joy: -2 }, sting: { joy: -1 }, dinner: { joy: 2, fulfilment: 1 },
  relief: { joy: 1 }, wonder: { joy: -1, fulfilment: -1 }, lingers: { joy: -1 },
}
const MEASURE_LIST: Measure[] = ['health', 'joy', 'fulfilment', 'money']
const marksFor = (d: number): Marks => (d >= 2.2 ? '+++' : d >= 1.1 ? '++' : d >= 0.35 ? '+' : d <= -2.2 ? '−−−' : d <= -1.1 ? '−−' : d <= -0.35 ? '−' : '=')

for (const view of demoBranches) {
  for (const m of view.branch.model.events) {
    m.effects = { health: 0, joy: 0, fulfilment: 0, money: 0, ...(EFFECTS[m.key] ?? {}) }
    m.effects_basis = 'judgement'
  }
  const running: Record<Measure, number> = { health: 0, joy: 0, fulfilment: 0, money: 0 }
  const series = Object.fromEntries(MEASURE_LIST.map((k) => [k, [] as { at: string; mean: number; low: number; high: number }[]])) as Record<Measure, { at: string; mean: number; low: number; high: number }[]>
  view.years.forEach((step, i) => {
    running.joy *= 0.6
    for (const event of step.events) {
      const fx = EFFECTS[event.event_type] ?? {}
      const p = view.branch.model.events.find((x) => x.key === event.event_type)?.probability ?? 1
      for (const k of MEASURE_LIST) running[k] += (fx[k] ?? 0) * p
    }
    const spread = 0.25 + i * 0.1
    for (const k of MEASURE_LIST) series[k].push({ at: step.at, mean: Math.round(running[k] * 100) / 100, low: Math.round((running[k] - spread) * 100) / 100, high: Math.round((running[k] + spread) * 100) / 100 })
  })
  const end = Object.fromEntries(MEASURE_LIST.map((k) => {
    const last = series[k][series[k].length - 1]
    return [k, { delta: last.mean, low: last.low, high: last.high, marks: marksFor(last.mean) }]
  })) as Record<Measure, { delta: number; low: number; high: number; marks: Marks }>
  view.branch.measures = { series, end, money_end: null }
}
