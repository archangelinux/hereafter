// Tests for the demo's decision maths (src/fixtures/decision.ts). Run: npm run test:decision
import { ACTIONS, PAYOFF, PRIOR, analyse, breakEven, chanceOfGain, ev, odds, posterior, prob, respondsWell, sd, type Action, type Evidence } from '../src/fixtures/decision.ts'
import { BACKGROUND, QUESTIONS, SOURCES, analysisFor, demoBranches, demoEvidence, demoQuestions, lifeFor } from '../src/fixtures/demo.ts'

let failed = 0
const close = (a: number, b: number, eps = 1e-9) => Math.abs(a - b) < eps
const check = (name: string, ok: boolean, detail = '') => {
  if (!ok) failed++
  console.log(ok ? 'ok  ' : 'FAIL', name, ok ? '' : detail)
}
const grid = Array.from({ length: 101 }, (_, i) => i / 100)

// --- Bayes in odds form
check('no evidence leaves the prior alone', close(posterior(0.25, []), 0.25))
check('odds and probability are inverses', grid.slice(1, 100).every((p) => close(prob(odds(p)), p)))
check('a ratio of 1 changes nothing', close(posterior(0.3, [1, 1, 1]), 0.3))
check('hand-computed: prior 0.25 with ratios 3 and 0.5 -> odds 1/3*3*0.5 = 0.5 -> p = 1/3', close(posterior(0.25, [3, 0.5]), 1 / 3))
check('order of the evidence does not matter', close(posterior(0.25, [3, 0.5, 2]), posterior(0.25, [2, 3, 0.5])))
check('a bigger ratio never lowers the posterior', [0.1, 0.5, 1, 2, 5].every((lr, i, a) => i === 0 || posterior(0.25, [lr]) > posterior(0.25, [a[i - 1]])))
check('the posterior stays strictly inside (0, 1)', [0.001, 0.1, 1, 10, 1000].every((lr) => { const p = posterior(0.25, [lr]); return p > 0 && p < 1 }))

// --- payoffs, expected value, spread (hand-computed at p = 0.5)
check('EV talk at p=0.5 is 0.5*70 + 0.5*(-5) = 32.5', close(ev('talk', 0.5), 32.5))
check('EV ask at p=0.5 is 0.5*100 + 0.5*(-30) = 35', close(ev('ask', 0.5), 35))
check('EV follow at p=0.5 is -45', close(ev('follow', 0.5), -45))
check('EV bury is 5 whatever p is', grid.every((p) => close(ev('bury', p), 5)))
check('bury has zero spread everywhere', grid.every((p) => sd('bury', p) === 0))
check('SD talk at p=0.5 is 75*0.5 = 37.5', close(sd('talk', 0.5), 37.5))
check('SD ask at p=0.5 is 130*0.5 = 65', close(sd('ask', 0.5), 65))
check('SD follow at p=0.5 is 30*0.5 = 15', close(sd('follow', 0.5), 15))
check('asking swings most, then talking, then following, then a sure thing, wherever p is between 0 and 1', grid.slice(1, 100).every((p) => sd('ask', p) > sd('talk', p) && sd('talk', p) > sd('follow', p) && sd('follow', p) > sd('bury', p)))
check('EV is the payoff at the extremes', close(ev('talk', 1), 70) && close(ev('talk', 0), -5) && close(ev('ask', 1), 100) && close(ev('ask', 0), -30))

// --- following loses in both worlds, so it is never best
check('follow has a negative payoff in both states', PAYOFF.follow.interested < 0 && PAYOFF.follow.not < 0)
check('follow EV is negative for every p from 0 to 1', grid.every((p) => ev('follow', p) < 0))
check('follow is never the best action, for any P(interested) or any evidence', grid.every((p) => ACTIONS.every((a) => ev('follow', p) < Math.max(ev('talk', p), ev('bury', p)))))

// --- the break-even
check('talk beats bury above (5+5)/(70+5) = 0.1333 and loses below', close(breakEven('talk', 'bury')!, 10 / 75))
check('ask beats bury above (5+30)/(100+30) = 0.2692', close(breakEven('ask', 'bury')!, 35 / 130))
check('ask beats a chat above (-5+30)/(130-75) = 0.4545', close(breakEven('ask', 'talk')!, 25 / 55))
check('each pair ties exactly at its break-even', close(ev('talk', 10 / 75), ev('bury', 10 / 75)) && close(ev('ask', 35 / 130), ev('bury', 35 / 130)) && close(ev('ask', 25 / 55), ev('talk', 25 / 55)))
check('talk beats bury just above its break-even, loses just below', ev('talk', 10 / 75 + 0.01) > ev('bury', 0.5) && ev('talk', 10 / 75 - 0.01) < ev('bury', 0.5))
check('a chat beats asking at low odds, asking beats a chat at high odds', ev('talk', 0.3) > ev('ask', 0.3) && ev('ask', 0.56) > ev('talk', 0.56))
check('follow never ties with bury (no break-even in [0,1])', breakEven('follow', 'bury') === null)

// --- the chance of ending better than where you started
check('chance of gain: talk = p, follow = 0, bury = 1', close(chanceOfGain('talk', 0.4), 0.4) && chanceOfGain('follow', 0.4) === 0 && chanceOfGain('bury', 0.4) === 1)
check('P(she at least talks to you) rises with P(interested) and stays a probability', grid.every((p) => respondsWell(p) >= 0.6 - 1e-9 && respondsWell(p) <= 0.95 + 1e-9) && respondsWell(0.9) > respondsWell(0.1))

// --- analyse(): the recommendation follows the numbers and can flip
const ev1 = (id: string, lr: number): Evidence => ({ id, label: id, from: 'test', lr, kind: 'assumption', why: '' })
const strong = analyse([ev1('smile', 3), ev1('alone', 1)])
const partner = analyse([ev1('smile', 3), ev1('partner', 0.02)])
check('with encouraging evidence it recommends approaching her (asking, at these odds)', strong.recommended === 'ask' && strong.p > strong.thresholds.askOverTalk)
check('with strong evidence against, it flips to burying it', partner.recommended === 'bury' && partner.p < partner.threshold)
check('it never recommends following, across a spread of evidence', [0.001, 0.05, 0.3, 1, 3, 30, 1000].every((lr) => analyse([ev1('x', lr)]).recommended !== 'follow'))
check('the default prior is what the module says it is', close(analyse([]).prior, PRIOR) && close(analyse([]).p, PRIOR))
check('margin is P(interested) minus the threshold', close(strong.margin, strong.p - strong.threshold))
check('every action is reported once, in a fixed order', ACTIONS.every((a: Action, i) => analyse([]).actions[i].action === a))

// --- the scripted demo, end to end
const eyes = QUESTIONS[0].choices.map((c) => c.text)
const withPartner = QUESTIONS[1].choices.map((c) => c.text)
const start = analysisFor({})
check('before any answer: P(interested) is the prior moved only by the background check', close(start.p, posterior(PRIOR, BACKGROUND.map((b) => b.lr))) && !start.final)
check('height 5′10″ is the average, so it moves the odds by exactly nothing', BACKGROUND.find((b) => b.id === 'height')!.lr === 1)
check('the opening recommendation is to talk, above the break-even', start.recommended === 'talk' && start.p > start.threshold)
const happy = analysisFor({ 'q-eyes': eyes[0], 'q-partner': withPartner[0] })
check('happy path: smiles and she is alone -> final, ask her out, P(interested) around 56%', happy.final && happy.recommended === 'ask' && Math.abs(happy.p - 0.5586) < 0.001)
check('happy path headline says to ask, in a few words', happy.headline === 'Ask her out' && happy.why.length > 40 && happy.why.length < 400)
const flip = analysisFor({ 'q-eyes': eyes[0], 'q-partner': withPartner[2] })
check('she is with someone: it flips to do not approach, still not follow', flip.final && flip.recommended === 'bury' && flip.p < flip.threshold && flip.headline === 'Don’t approach her yet')
check('all nine answer combinations reach a verdict and none recommends following', eyes.every((e) => withPartner.every((q) => { const a = analysisFor({ 'q-eyes': e, 'q-partner': q }); return a.final && a.recommended !== 'follow' && a.why.length > 40 })))
check('a half-answered demo is not final', !analysisFor({ 'q-eyes': eyes[0] }).final)
check('every choice text matches a rule (a typo would silently do nothing)', QUESTIONS.every((q) => q.choices.every((c) => analysisFor({ [q.id]: c.text }).steps.length === BACKGROUND.length + 1)))
check('a smile raises the odds and a partner lowers them', analysisFor({ 'q-eyes': eyes[0] }).p > start.p && analysisFor({ 'q-partner': withPartner[2] }).p < start.p)
check('follow is worst in every combination', eyes.every((e) => withPartner.every((q) => { const a = analysisFor({ 'q-eyes': e, 'q-partner': q }); return a.actions.find((x) => x.action === 'follow')!.ev < Math.min(a.actions.find((x) => x.action === 'talk')!.ev, a.actions.find((x) => x.action === 'bury')!.ev + 1e9) })))
check('the payoff table travels with the analysis, unchanged', JSON.stringify(happy.payoff) === JSON.stringify(PAYOFF))

// --- the summary in the side panel: short, in plain words, in the person's own wording
check('the summary reads in the person’s own words for the option they chose', analysisFor({}, { talk: 'ask her out' }).headline === 'Ask her out')
check('the summary lists one plain reason per piece of evidence, and says so when one changes nothing', (() => { const r = analysisFor({}).reasons; return r.length === 3 && r[0].effect === 'none' && r[0].note === 'no effect' && r[1].effect === 'up' })())
check('answers add their own reason, and a partner is a strong "down"', (() => { const r = analysisFor({ 'q-partner': withPartner[2] }).reasons; return r.length === 4 && r[3].effect === 'down' && r[3].note === 'lowers it a lot' })())
check('no reason or note uses jargon', analysisFor({ 'q-eyes': eyes[0], 'q-partner': withPartner[2] }).reasons.every((r) => !/likelihood|bayes|posterior|prior|expected value|ratio/i.test(r.text + r.note)) && !/likelihood|bayes|posterior|expected value|ratio/i.test(analysisFor({}).why + analysisFor({}).headline))

// --- each path has its own summary, so the panel changes when a different path is selected
const paths = (a: ReturnType<typeof analysisFor>) => (['talk', 'ask', 'follow', 'bury'] as const).map((k) => a.byPath[k])
check('every path has a figure, a verdict, a reason and at least three lines of reasoning', [start, happy, flip].every((a) => paths(a).every((x) => x.stat && x.of && x.pick && x.why.length > 30 && x.reasons.length >= 3)))
check('the four paths say different things', [start, happy, flip].every((a) => new Set(paths(a).map((x) => x.why)).size === 4 && new Set(paths(a).map((x) => x.pick)).size >= 3))
check('talking and asking show different figures and different reasons', happy.byPath.talk.stat !== happy.byPath.ask.stat && happy.byPath.talk.of !== happy.byPath.ask.of && happy.byPath.ask.of === 'chance she says yes' && JSON.stringify(happy.byPath.talk.reasons) !== JSON.stringify(happy.byPath.ask.reasons))
check('talking shows the chance she talks with you', happy.byPath.talk.stat === `${Math.round(happy.responds * 100)}%` && happy.byPath.talk.of.includes('talks with you'))
check('following is always "Don’t", with the law among its reasons', [start, happy, flip].every((a) => a.byPath.follow.pick === 'Don’t' && a.byPath.follow.reasons.some((r) => /law|harassment/i.test(r.text + r.note))))
check('talking reads as the best first step when it wins, a gentle start when asking wins, and not worth it when neither', start.byPath.talk.pick === 'Best first step' && happy.byPath.talk.pick === 'A good, gentle start' && flip.byPath.talk.pick === 'Not worth it yet')
check('asking reads as worth it when it wins, a bit early when a chat wins, and not now when neither', happy.byPath.ask.pick === 'Worth asking' && start.byPath.ask.pick === 'A bit early' && flip.byPath.ask.pick === 'Not now')
check('burying reads as right for now when talking is not worth it, and as lingering when it is', flip.byPath.bury.pick === 'Safe, and right for now' && happy.byPath.bury.pick === 'Safe, but it lingers')
check('the per-path text uses no jargon', [start, happy, flip].every((a) => paths(a).every((x) => !/likelihood|bayes|posterior|expected value|ratio|prior/i.test([x.stat, x.of, x.pick, x.why, ...x.reasons.map((r) => r.text + r.note)].join(' ')))))
check('a path lookup starts empty until a decision fills it in', Object.keys(start.paths).length === 0)

// --- what she says changes which of the two is better
const maybe = analysisFor({ 'q-eyes': eyes[1], 'q-partner': withPartner[0] })
const cold = analysisFor({ 'q-eyes': eyes[2], 'q-partner': withPartner[0] })
check('a clear sign of interest makes asking her out the best choice', happy.recommended === 'ask')
check('a mild sign makes a chat the best choice, not asking', maybe.recommended === 'talk' && maybe.p > maybe.thresholds.talk && maybe.p < maybe.thresholds.askOverTalk)
check('no sign at all still favours a chat over asking or nothing, and never following', cold.recommended !== 'follow' && cold.recommended !== 'ask')
check('the headline follows the person’s own wording for whichever wins', analysisFor({ 'q-eyes': eyes[0], 'q-partner': withPartner[0] }, { ask: 'invite her to dinner' }).headline === 'Invite her to dinner')
check('the chance she says yes rises with the odds and is a probability', analysisFor({ 'q-eyes': eyes[0] }).saysYes > analysisFor({ 'q-eyes': eyes[2] }).saysYes && [start, happy, flip].every((a) => a.saysYes > 0 && a.saysYes < 1))

// --- typed options play the life they are about, whatever order they come in
check('talking words play the talking life, and asking words play the asking life', lifeFor('talk to her') === 'talk' && lifeFor('Say hi at the coffee stand') === 'talk' && lifeFor('ask her out') === 'ask' && lifeFor('Take her out for dinner') === 'ask' && lifeFor('invite her to the after party') === 'ask')
check('following words play the following life', ['Follow her around', 'follow her', 'stalk her', 'Trail her all day'].every((t) => lifeFor(t) === 'follow'))
check('burying words play the burying life', ['Bury your feelings and forget about it', 'ignore it', 'do nothing', 'Let it go'].every((t) => lifeFor(t) === 'bury'))
check('the four kinds of option map to four different lives, in any order', ['Bury your feelings and forget about it', 'Ask her out', 'Talk to her', 'Follow her around'].map(lifeFor).join() === 'bury,ask,talk,follow')

// --- sources: nothing is called published without a link, and quoted where a figure was read
check('every published source has a link', SOURCES.filter((x) => x.kind === 'published').every((x) => x.url.startsWith('https://')))
check('every published source that gives a figure carries the sentence it was read in', SOURCES.filter((x) => ['speed', 'ask', 'height', 'law', 'regret'].includes(x.id)).every((x) => !!x.quote && x.quote.length > 8))
check('the source that was only cited for direction carries no quote', !SOURCES.find((x) => x.id === 'similar')!.quote)
check('the inputs are labelled as assumptions', SOURCES.find((x) => x.id === 'inputs')!.kind === 'assumption')
check('every background and answer ratio is honestly tagged as an assumption', [...BACKGROUND, ...QUESTIONS.flatMap((q) => q.choices.map((c) => analysisFor({ [q.id]: c.text }).steps.at(-1)!))].every((x) => x.kind === 'assumption'))
check('evidence documents quote their source exactly', demoEvidence.filter((x) => x.snippet).every((x) => SOURCES.some((s) => s.quote === x.snippet)))

// --- the three lives and the questions
check('four lives, six steps each, each opening with the choice itself, in the order of the actions', demoBranches.length === 4 && demoBranches.map((b) => b.branch.id).join() === 'br-talk,br-ask,br-follow,br-bury' && demoBranches.every((b) => b.years.length === 6 && b.years[0].events[0].event_type === 'choice'))
check('the questions attach to every path and start unanswered', (() => { const q = demoQuestions('sc-x', ['a', 'b', 'c']); return q.length === 2 && q.every((x) => x.answer === null && x.applies_to.length === 3 && x.choices.length === 3 && x.scenario_id === 'sc-x') })())

console.log(failed ? `\n${failed} FAILED` : `\nall passed`)
process.exit(failed ? 1 : 0)
