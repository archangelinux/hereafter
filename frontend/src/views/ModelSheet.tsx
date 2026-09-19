import { useEffect, useState } from 'react'
import type { Api } from '../api'
import type { ModelCard } from '../types'
import { Sheet } from './Sheet'

/** How the numbers are made: the model card, in plain words. */
export function ModelSheet({ api, onClose }: { api: Api; onClose: () => void }) {
  const [card, setCard] = useState<ModelCard | null>(null)
  useEffect(() => void api.model().then(setCard).catch(() => undefined), [api])
  return (
    <Sheet title="How these numbers are made" eyebrow={card ? `model ${card.version}` : undefined} lede={card?.summary} onClose={onClose}>
      {!card && <p className="dim">Loading…</p>}
      {card && (
        <div className="model">
          <ol>{card.steps.map((s) => <li key={s.title}><b>{s.title}.</b> {s.text}</li>)}</ol>
          {card.constants.length > 0 && <><h2>Constants</h2><dl>{card.constants.map((c) => [<dt key={c.name}>{c.name}{c.value !== '' ? ` = ${c.value}` : ''}</dt>, <dd key={c.name + 'm'}>{c.meaning}</dd>])}</dl></>}
          {!card.steps.some((x) => /measure/i.test(x.title)) && (
            <><h2>Four measures</h2><p>Health, joy (short term), fulfilment (long term) and money are tracked along every path as a difference from now. Each event nudges them up or down by a judged amount, or by a published or stated figure for money; the lines show the average of the thousand lives and the band shows where most of them fall.</p></>
          )}
          <h2>Limits</h2>
          <ul>{card.limits.map((l) => <li key={l}>{l}</li>)}</ul>
        </div>
      )}
    </Sheet>
  )
}
