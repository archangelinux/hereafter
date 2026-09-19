import { useEffect, useState } from 'react'
import type { Api } from '../api'
import { aspectLabel } from '../derive'
import { BasisMark } from '../page/marks'
import { theme } from '../theme'
import type { BranchView, CompareResponse, Scenario } from '../types'
import { Sheet } from './Sheet'

/** Side by side, as cards: what is distinctive about each life, then only where they part. */
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

  // where these lives part: per aspect, the first checkpoint at which the branches differ
  const partings = data
    ? [...new Set(data.checkpoints.flatMap((c) => c.rows.map((r) => r.aspect)))].flatMap((aspect) => {
        const cp = data.checkpoints.find((c) => c.rows.find((r) => r.aspect === aspect)?.differs)
        const row = cp?.rows.find((r) => r.aspect === aspect)
        return cp && row ? [{ aspect, when: cp.label ?? String(cp.year), row }] : []
      })
    : []

  return (
    <Sheet title="Side by side" eyebrow="compare" lede={scenario ? `“${scenario.situation}”` : undefined} onClose={onClose} wide>
      {error && <p className="page__error">{error}</p>}
      {!data && !error && <p className="dim">laying the branches side by side</p>}
      {data && (
        <div className="cards" style={{ gridTemplateColumns: `repeat(${branches.length}, minmax(0, 1fr))` }}>
          {branches.map((b) => (
            <article key={b.id} className="card" style={{ ['--accent' as string]: accent(b.id) }}>
              <h2>{b.label}</h2>
              {!!data.distinctive?.some((d) => d.branch_id === b.id) && (
                <>
                  <p className="caps">only here</p>
                  <ul className="card__distinct">
                    {data.distinctive!.filter((d) => d.branch_id === b.id).map((d) => (
                      <li key={d.label}><BasisMark basis={d.basis} /><span>{d.label}</span><em>{d.words}</em></li>
                    ))}
                  </ul>
                </>
              )}
              <p className="caps">where it parts from the others</p>
              {partings.length === 0 && <p className="dim">Nowhere Hereafter checked.</p>}
              <ul className="card__parts">
                {partings.map(({ aspect, when, row }) => {
                  const mine = row.values.find((v) => v.branch_id === b.id)
                  return mine ? (
                    <li key={aspect}>
                      <span className="caps">{when}</span>
                      <span>{aspectLabel(aspect, branches)}</span>
                      <b>{mine.value}</b>
                      <em>{mine.words}</em>
                    </li>
                  ) : null
                })}
              </ul>
              <button type="button" className="verb" onClick={() => onSwitch(b.id)}>live this one</button>
            </article>
          ))}
        </div>
      )}
    </Sheet>
  )
}
