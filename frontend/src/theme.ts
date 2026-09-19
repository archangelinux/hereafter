// Every colour, type and motion token lives here. The CSS custom properties used by styles.css
// are written from this object at boot (applyTheme), so the palette is swapped here only.
//
// A storybook morning: light, pastel, ink on paper. Hex values marked "spec" are the user's,
// verbatim; the rest are value steps derived from them.

export const theme = {
  color: {
    // sky (spec)
    skyTop: '#FDF6EC',
    skyMid: '#F9E4E0',
    skyHorizon: '#DCE9E6',
    // text and main's ink (spec: warm charcoal, never pure black)
    text: '#5C5347',
    textDim: '#8A8073',
    textFaint: '#B3A999',
    // paper (spec)
    paper: '#FFFDF8',
    hairline: '#D9CDBB',
    veil: '#FDF6EC',
    // the past's stone, used for main's terracotta marks (spec)
    sand: '#E8D5C0',
    terracotta: '#D9A588',
    // roads not taken (spec: weathered, desaturated)
    ruin: '#B9B3AA',
    ruinPale: '#D8D3CC',
    // accents, tiny doses (spec)
    coral: '#E2917A',
    coralDeep: '#C4705A',
    sage: '#A8C6B5',
    gold: '#F0C987',
    goldDeep: '#CFA04E',
    mist: '#EDE4F0',
  },
  // one restrained ink per open branch, in option order: terracotta, sage, ochre, dusk
  branch: ['#C4705A', '#6E9C86', '#C2923F', '#8E86A8'],
  font: {
    display: "'Cormorant Garamond', 'Cormorant', Georgia, serif",
    body: "'Newsreader Variable', 'Newsreader', Georgia, serif",
    caps: "'Cormorant SC', 'Cormorant Garamond', Georgia, serif",
  },
  tracking: {
    display: '0.04em',
    heading: '0.02em',
    caps: '0.12em',
  },
  size: {
    body: '18px',
    small: '15px',
    caps: '13px',
    title: '40px',
    heading: '34px',
    chapter: '30px',
  },
  motion: {
    slow: '1400ms',
    medium: '520ms',
    quick: '200ms',
    ease: 'cubic-bezier(0.22, 0.61, 0.36, 1)',
    pollMs: 60_000, // main + branches re-poll; "now" advances on its own
    busyPollMs: 2_500, // while research is running or a chapter is being written
  },
} as const

export type Theme = typeof theme

const kebab = (s: string) => s.replace(/[A-Z]/g, (m) => '-' + m.toLowerCase())

/** Mirror the tokens into CSS custom properties: --color-text, --font-display, --motion-slow … */
export function applyTheme(root: HTMLElement = document.documentElement) {
  const groups = ['color', 'font', 'tracking', 'size', 'motion'] as const
  for (const group of groups) {
    for (const [key, value] of Object.entries(theme[group])) root.style.setProperty(`--${group}-${kebab(key)}`, String(value))
  }
  theme.branch.forEach((c, i) => root.style.setProperty(`--branch-${i}`, c))
}
