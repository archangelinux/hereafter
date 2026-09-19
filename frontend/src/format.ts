const MONTHS = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december']

/** Parses 'YYYY-MM-DD' (or a full ISO stamp) as a local date, so a day never slips across midnight UTC. */
export function parseDate(iso: string): number {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  return m ? new Date(+m[1], +m[2] - 1, +m[3]).getTime() : new Date(iso).getTime()
}

const YEAR_MS = 365.25 * 24 * 3600 * 1000

/** A date as a fractional year: the one time scale the line is drawn on. */
export const yearOf = (iso: string) => {
  const t = parseDate(iso)
  const y = new Date(t).getFullYear()
  return y + (t - new Date(y, 0, 1).getTime()) / YEAR_MS
}

export function dateLabel(iso: string): string {
  const d = new Date(parseDate(iso))
  return `${MONTHS[d.getMonth()]} ${d.getFullYear()}`
}

export function dayLabel(iso: string): string {
  const d = new Date(parseDate(iso))
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`
}

export const words = (s: string) => s.replace(/_/g, ' ')

export const sentence = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s)

/** "offer_deadline: 2026-09-26" → "2026-09-26" */
export const deadlineOf = (precondition: string | null) => precondition?.match(/(\d{4}-\d{2}-\d{2})/)?.[1] ?? null

/** How sure a source is, in words. Confidence never appears as a figure. */
export function sureness(confidence: number): string {
  if (confidence >= 0.9) return 'certain'
  if (confidence >= 0.7) return 'fairly sure'
  if (confidence >= 0.4) return 'a reading'
  if (confidence >= 0.2) return 'a glimpse'
  return 'a breadcrumb'
}

export const SOURCE_WORDS: Record<string, string> = {
  scraped: 'read from your pages',
  told: 'told by you',
  passive: 'from your calendar',
  simulated: 'simulated',
}

/** Only the evidence drawer may say this. */
export function inEveryTen(share: number): string {
  const n = Math.round(share * 10)
  if (n >= 10) return 'in nearly every simulated life'
  if (n <= 0) return 'in almost none of the simulated lives'
  return `in ${n} of every 10 simulated lives`
}
