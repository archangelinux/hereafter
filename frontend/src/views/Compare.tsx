import { useEffect, useState } from 'react'
import type { Api } from '../api'
import { aspectLabel } from '../derive'
import { theme } from '../theme'
import type { BranchView, CompareResponse, Scenario } from '../types'
import { MEASURES, markTone } from '../hud/MeasuresBlock'
import { Sheet } from './Sheet'

const pct = (x: number | undefined) => (x === undefined ? '' : `${Math.round(x * 100)}%`)

/** The paths side by side: each outcome's probability on each path, biggest differences first. */
export function Compare({ api, views, scenario, onSwitch, onClose }: { api: Api; views: BranchView[]; scenario: Scenario | null; onSwitch: (id: string) => void; onClose: () => void }) {
  const [data, setData] = useState<CompareResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const ids = views.slice(0, 3).map((v) => v.branch.id)
  useEffect(() => {
    let live = true
    api.compare(ids).then((d) => live && setData(d)).catch((e) => live && setError(e instanceof Error ? e.message : 'The comparison could not be made.'))
    return () => {
      live = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, ids.join(',')])

  const accent = (id: string) => theme.branch[Math.max(0, scenario?.branch_ids.indexOf(id) ?? ids.indexOf(id)) % theme.branch.length]
  const branches = data?.branches ?? views.map((v) => v.branch)
  // one row per outcome, read at the last checkpoint; the rows that differ most come first
  const last = data?.checkpoints[data.checkpoints.length - 1]
  const rows = (last?.rows ?? [])
    .map((r) => {
      const ps = r.values.map((v) => v.probability ?? v.share)
      const spread = r.values.every((v) => v.value === r.values[0].value) ? Math.max(...ps) - Math.min(...ps) : 1 + Math.max(...ps) - Math.min(...ps)
      return { ...r, spread }
    })
    .sort((a, b) => b.spread - a.spread)

  return (
    <Sheet title="Compare paths" lede={scenario?.situation} onClose={onClose} wide>
      {error && <p className="page__error">{error}</p>}
      {!data && !error && <p className="dim">Comparing…</p>}
      {data && (
        <table className="cmp">
          <thead>
            <tr>
              <th />
              {branches.map((b) => (
                <th key={b.id} style={{ ['--accent' as string]: accent(b.id) }}><button type="button" className="quiet" onClick={() => onSwitch(b.id)}>{b.label}</button></th>
              ))}
            </tr>
          </thead>
          <tbody>
            {MEASURES.map((m) => {
              const ends = branches.map((b) => data.measures?.[b.id]?.[m] ?? views.find((v) => v.branch.id === b.id)?.branch.measures?.end[m] ?? null)
              if (ends.every((x) => !x)) return null
              return (
                <tr key={m}>
                  <th>{m === 'joy' ? 'Joy, short term' : m === 'fulfilment' ? 'Fulfilment, long term' : m[0].toUpperCase() + m.slice(1)} <span className="dim">· compared with now</span></th>
                  {ends.map((x, i) => <td key={i}>{x ? <b className={`h-tiny--${markTone(x.marks)}`}>{x.marks}</b> : '—'}</td>)}
                </tr>
              )
            })}
            {data.distinctive?.map((d) => (
              <tr key={d.branch_id + d.label}>
                <th>{d.label} <span className="dim">· only here</span></th>
                {branches.map((b) => <td key={b.id}>{b.id === d.branch_id ? <b>{pct(d.probability) || d.words}</b> : '—'}</td>)}
              </tr>
            ))}
            {rows.map((r) => (
              <tr key={r.aspect}>
                <th>{aspectLabel(r.aspect, branches)}</th>
                {r.values.map((v) => <td key={v.branch_id}><b>{pct(v.probability ?? v.share)}</b> {v.value}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Sheet>
  )
}
