import type { Measure, Measures, Person } from '../types'

const NAMES: Record<Measure, string> = { health: 'Health', joy: 'Joy, short term', fulfilment: 'Fulfilment, long term', money: 'Money' }
export const MEASURES: Measure[] = ['health', 'joy', 'fulfilment', 'money']
export const markTone = (marks: string) => (marks.includes('+') ? 'plus' : marks.includes('−') || marks.includes('-') ? 'minus' : 'even')

const money = (v: number, currency: string) => {
  const abs = Math.abs(v)
  const amount = abs >= 1000 ? `${Math.round(abs / 1000)}k` : String(Math.round(abs))
  const sign = v > 0 ? '+' : v < 0 ? '−' : ''
  return `${sign}${currency === 'CAD' || currency === 'USD' ? '$' : ''}${amount}${currency === 'CAD' || currency === 'USD' ? '' : ' ' + currency} a year`
}
const FRACTIONS: [number, string][] = [[0.08, 'a small part'], [0.15, 'about a tenth'], [0.23, 'about a fifth'], [0.29, 'about a quarter'], [0.4, 'about a third'], [0.6, 'about half'], [0.85, 'about three quarters']]

/** Compared with now: four rows, each a name, its marks and a small sparkline with the 10–90% band. */
export function MeasuresBlock({ measures, step, person }: { measures: Measures; step: number | null; person: Person | null }) {
  const W = 96
  const H = 20
  return (
    <div className="h-measures">
      <h3>Compared with now</h3>
      <ul>
        {MEASURES.map((m) => {
          const series = measures.series[m] ?? []
          const end = measures.end[m]
          if (!end) return null
          const span = Math.max(0.5, ...series.map((p) => Math.max(Math.abs(p.low), Math.abs(p.high), Math.abs(p.mean))))
          const x = (i: number) => (series.length < 2 ? 0 : (i / (series.length - 1)) * W)
          const y = (v: number) => H / 2 - (v / span) * (H / 2 - 2)
          const line = series.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)} ${y(p.mean).toFixed(1)}`).join(' ')
          const band = series.length > 1 ? `${series.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)} ${y(p.high).toFixed(1)}`).join(' ')} ${[...series].reverse().map((p, i) => `L${x(series.length - 1 - i).toFixed(1)} ${y(p.low).toFixed(1)}`).join(' ')} Z` : ''
          const tone = markTone(end.marks)
          const share = m === 'money' && measures.money_end && person?.money?.income ? Math.abs(measures.money_end.value) / person.money.income : null
          return (
            <li key={m} className={`h-measure h-measure--${tone}`}>
              <span className="h-measure__name">{NAMES[m]}</span>
              <b className="h-measure__marks" title={`${end.delta > 0 ? '+' : ''}${end.delta.toFixed(1)} by the end of this path (10–90%: ${end.low.toFixed(1)} to ${end.high.toFixed(1)})`}>{end.marks}</b>
              <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} preserveAspectRatio="none" aria-hidden="true">
                <line x1="0" x2={W} y1={H / 2} y2={H / 2} className="h-measure__zero" />
                {band && <path d={band} className="h-measure__band" />}
                <path d={line} className="h-measure__line" />
                {step !== null && series.length > 1 && <line x1={x(Math.min(step, series.length - 1))} x2={x(Math.min(step, series.length - 1))} y1="0" y2={H} className="h-measure__cursor" />}
              </svg>
              {m === 'money' && measures.money_end && (
                <span className="h-measure__amount">{money(measures.money_end.value, measures.money_end.currency)}{share !== null ? `, ${(FRACTIONS.find(([t]) => share <= t) ?? [0, 'more than your income'])[1]} of your income` : ''}</span>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}

/** Four tiny marks, H J F $, so paths can be compared at a glance. */
export function TinyMarks({ measures }: { measures: Measures }) {
  return (
    <span className="h-tiny" aria-label="health, joy, fulfilment, money compared with now">
      {MEASURES.map((m, i) => {
        const marks = measures.end[m]?.marks ?? '='
        return <i key={m} className={`h-tiny--${markTone(marks)}`} title={`${NAMES[m]}: ${marks} compared with now`}>{marks[0] === '=' ? '·' : marks[0]}<sub>{'HJF$'[i]}</sub></i>
      })}
    </span>
  )
}
