const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

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

const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

/** A step is shown by its date and nothing else: never "week 3". Year-scale branches show the year. */
export function stepDate(at: string, byYear = false): string {
  const d = new Date(parseDate(at))
  if (byYear) return String(d.getFullYear())
  const today = new Date()
  if (d.toDateString() === today.toDateString()) return 'today'
  const day = `${d.getDate()} ${MONTH_NAMES[d.getMonth()]}`
  return d.getFullYear() === today.getFullYear() ? day : `${day} ${d.getFullYear()}`
}

/** Steps a year or more apart are year-scale. */
export function isByYear(steps: { at: string }[]): boolean {
  if (steps.length < 2) return false
  return (parseDate(steps[steps.length - 1].at) - parseDate(steps[0].at)) / (steps.length - 1) > 300 * 86_400_000
}

const OFF_THE_LINE = new Set(['state_fact', 'breadcrumb', 'profile_glimpse', 'note'])

/** Undated things, and facts that are not happenings, are kept off the line (they live in the log and under "Your data"). */
export const isUndated = (e: { payload?: Record<string, unknown> }) => e.payload?.undated === true
export const belongsOnLine = (e: { event_type: string; payload?: Record<string, unknown> }) => !isUndated(e) && !OFF_THE_LINE.has(e.event_type)

/** A date said as precisely as it is known: "2024", "June 2025", "19 September 2026". Month and year until the backend says. */
export function preciseDate(e: { date: string; payload?: Record<string, unknown> }): string {
  const precision = e.payload?.date_precision
  if (precision === 'year') return e.date.slice(0, 4)
  if (precision === 'day') return dayLabel(e.date)
  return dateLabel(e.date)
}
