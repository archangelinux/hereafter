import { Brand } from '../views/Brand'

interface Fact {
  from: 'linkedin' | 'github' | 'instagram' | null
  text: string
}

/** What Hereafter picked up from the connected accounts, each with where it came from. */
export function Profile({ facts, onClose }: { facts: Fact[]; onClose: () => void }) {
  return (
    <section className="h-panel h-profile" aria-label="What Hereafter learned about you">
      <header className="h-panel__head">
        <h2>What I learned about you</h2>
        <button type="button" className="h-link" onClick={onClose}>Hide</button>
      </header>
      <ul className="h-profile__list">
        {facts.map((f) => (
          <li key={f.text}>
            <span className="h-profile__mark" aria-hidden="true">{f.from ? <Brand kind={f.from} /> : <i />}</span>
            <span>{f.text}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}
