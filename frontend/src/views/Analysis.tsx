import type { AnalysisView, Question } from '../types'
import { Sheet } from './Sheet'

const pct = (x: number) => `${Math.round(x * 100)}%`
const pts = (x: number) => `${x > 0 ? '+' : x < 0 ? '−' : ''}${Math.abs(Math.round(x))}`

interface Props {
  analysis: AnalysisView
  /** the question the person asked, shown as the sheet's eyebrow */
  situation: string
  /** the next question to ask, if any are left */
  question: Question | null
  answered: number
  total: number
  busy: boolean
  onAnswer: (q: Question, text: string) => void
  onClose: () => void
}

/**
 * The numbers behind the choice, on one sheet: how the odds were built up from what is known, what each option
 * is worth in each possible world, the recommendation, and where every figure came from. The questions are asked
 * here too, so the odds and the bars move in front of the person as they answer.
 */
export function Analysis({ analysis: a, situation, question, answered, total, busy, onAnswer, onClose }: Props) {
  // P(interested) after each piece of evidence, so the person can watch it move
  let odds = a.prior / (1 - a.prior)
  const running = a.steps.map((s) => (odds *= s.lr) / (1 + odds))
  const best = a.actions.find((x) => x.action === a.recommended)!
  const talk = a.actions.find((x) => x.action === 'talk')!
  const above = a.margin >= 0

  return (
    <Sheet title="The numbers" eyebrow={situation} lede="How likely she is to be interested, and what each choice is worth in each possible world." onClose={onClose} wide>
      {question && (
        <section className="an an-in an-in--0 an-ask" aria-label="A question that would sharpen this">
          <p className="caps">Question {answered + 1} of {total}</p>
          <p className="an-ask__q">{question.text}</p>
          <p className="an-muted">{question.why}</p>
          <p className="an-ask__choices">
            {question.choices.map((c) => <button key={c} type="button" className="h-chip" disabled={busy} onClick={() => onAnswer(question, c)}>{c}</button>)}
          </p>
        </section>
      )}

      <section className="an an-in an-in--1" aria-label="The chance she is interested">
        <div className="an-odds">
          <div>
            <p className="caps">Chance she is interested</p>
            <p className="an-odds__big" aria-live="polite">{pct(a.p)}</p>
          </div>
          <div className="an-gauge" role="img" aria-label={`${pct(a.p)} chance she is interested; talking beats doing nothing above ${pct(a.threshold)}`}>
            <i className="an-gauge__fill" style={{ width: pct(a.p) }} />
            <b className="an-gauge__mark" style={{ left: pct(a.threshold) }}><span>{pct(a.threshold)}: where talking starts to beat doing nothing</span></b>
          </div>
        </div>
        <ol className="an-steps">
          <li className="an-step">
            <span className="an-step__label">Starting point</span>
            <span className="an-step__from">before anything is known</span>
            <span className="an-step__lr">{pct(a.prior)}</span>
            <span className="an-tag is-assumption">assumption</span>
          </li>
          {a.steps.map((s, i) => (
            <li key={s.id} className="an-step">
              <span className="an-step__label">{s.label}</span>
              <span className="an-step__from">from {s.from}</span>
              <span className={`an-step__lr ${s.lr > 1 ? 'is-up' : s.lr < 1 ? 'is-down' : ''}`} title="how many times likelier this is if she is interested than if she is not">×{s.lr}</span>
              <span className="an-step__run">→ {pct(running[i])}</span>
              <span className="an-step__why">{s.why}</span>
            </li>
          ))}
        </ol>
      </section>

      <section className="an an-in an-in--2" aria-label="What each choice is worth">
        <p className="caps">What each choice is worth</p>
        <table className="an-table">
          <thead>
            <tr><th scope="col">Choice</th><th scope="col">If she is interested</th><th scope="col">If not</th><th scope="col">Expected worth</th></tr>
          </thead>
          <tbody>
            {a.actions.map((x) => {
              const w = Math.min(50, (Math.abs(x.ev) / 70) * 50) // one fixed scale, so the bars move rather than re-scale as the odds change
              return (
                <tr key={x.action} className={x.action === a.recommended ? 'is-best' : ''}>
                  <th scope="row">
                    <span className="an-table__name">{x.label}{x.action === a.recommended && <em className="an-pill">best</em>}</span>
                    <span className="an-muted">{x.gain === 0 ? 'Never comes out ahead' : x.gain === 1 ? 'Always comes out ahead, but only slightly' : `${pct(x.gain)} chance of coming out ahead`}. {x.sd === 0 ? 'A sure thing: no swing.' : `Swings by about ±${Math.round(x.sd)}.`}</span>
                  </th>
                  <td className={a.payoff[x.action].interested < 0 ? 'is-neg' : 'is-pos'}>{pts(a.payoff[x.action].interested)}</td>
                  <td className={a.payoff[x.action].not < 0 ? 'is-neg' : 'is-pos'}>{pts(a.payoff[x.action].not)}</td>
                  <td>
                    <span className="an-ev" title={`${a.p.toFixed(2)} × ${a.payoff[x.action].interested} + ${(1 - a.p).toFixed(2)} × ${a.payoff[x.action].not} = ${x.ev.toFixed(1)}`}>
                      <i className="an-ev__axis" />
                      <i className={`an-ev__bar ${x.ev < 0 ? 'is-neg' : 'is-pos'}`} style={{ left: x.ev < 0 ? `${50 - w}%` : '50%', width: `${w}%` }} />
                    </span>
                    <b className="an-ev__n">{pts(x.ev)}</b>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
        <p className="an-muted">Points are how good or bad each outcome is for you (an assumption you can change). Expected worth is the payoff in each world weighted by how likely that world is.</p>
      </section>

      <section key={`${a.p.toFixed(3)}-${a.final}`} className={`an an-in an-in--3 an-verdict ${a.final ? 'is-final' : ''}`} aria-label="The recommendation" aria-live="polite">
        <p className="caps">{a.final ? 'Where that leaves you' : 'What it says so far'}</p>
        <h2 className="an-verdict__head">{a.headline}</h2>
        <p>{a.verdict}</p>
        <p className="an-muted">
          Break-even: talking beats doing nothing once the chance she is interested is above {pct(a.threshold)}. You are at {pct(a.p)}, {above ? 'above' : 'below'} it by {Math.abs(Math.round(a.margin * 100))} points.
          {' '}If you go over, there is about a {pct(a.responds)} chance she at least talks with you.
          {!a.final && ` Answering the ${total - answered === 1 ? 'last question' : 'remaining questions'} would sharpen this.`}
          {a.final && a.recommended === 'talk' && ' It would take a clear sign she is with someone to change this.'}
          {a.final && a.recommended !== 'talk' && ' A clear sign of interest from her would change this.'}
        </p>
        {a.recommended !== 'talk' && <p className="an-muted">Best: {best.label.toLowerCase()} ({pts(best.ev)}). Talking would be worth {pts(talk.ev)}.</p>}
      </section>

      <details className="an an-in an-in--4 an-how">
        <summary>How these numbers are made</summary>
        <p className="an-muted">
          The odds start at the starting point and are multiplied by one ratio per fact (Bayes’ rule). Each choice’s worth is the payoff if she is interested times the chance she is, plus the payoff if not times the chance she is not.
          For talking: {a.p.toFixed(2)} × {a.payoff.talk.interested} + {(1 - a.p).toFixed(2)} × {a.payoff.talk.not} = {talk.ev.toFixed(1)}.
        </p>
        <ul className="an-sources">
          {a.sources.map((s) => (
            <li key={s.id}>
              <span className={`an-tag ${s.kind === 'published' ? 'is-published' : 'is-assumption'}`}>{s.kind === 'published' ? 'published' : 'assumption'}</span>
              <span>
                {s.claim}
                {s.quote && <q className="an-quote">{s.quote}</q>}
                <span className="an-muted">{s.url ? <a href={s.url} target="_blank" rel="noreferrer">{s.cite}</a> : s.cite}</span>
              </span>
            </li>
          ))}
        </ul>
      </details>

      <p className="an-foot">Illustrative model, not dating advice. It uses only your own accounts and what you tell it, and it knows nothing about her.</p>
    </Sheet>
  )
}
