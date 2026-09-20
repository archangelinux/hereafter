// The storybook-morning palette, as flat face triples: top / warm side (+x) / shadow side (+z).
// Spec values are the user's; the rest are value steps derived from them. Self-contained on
// purpose: the world module reads nothing outside src/world except types, format and fixtures.

export interface Faces {
  top: string
  sideX: string
  sideZ: string
}

export const stone = {
  past: { top: '#E3CBB0', sideX: '#CE9878', sideZ: '#BCA891' },
  open: { top: '#EADCC8', sideX: '#D3BC9F', sideZ: '#BCA891' }, // pale stone, a step deeper than the sky so it reads; the shadow face is the spec's #C9B8A3,
  mist: { top: '#EDE4F0', sideX: '#E4D9E9', sideZ: '#DBCFE1' },
  ruin: { top: '#D8D3CC', sideX: '#C4BFB8', sideZ: '#B6B0A8' },
  cloud: { top: '#FFFEFC', sideX: '#FBF1EE', sideZ: '#F1E8EE' },
  coral: { top: '#E9A08A', sideX: '#E2917A', sideZ: '#CC7F69' },
  sage: { top: '#B7D2C2', sideX: '#A8C6B5', sideZ: '#93B3A1' },
  gold: { top: '#F7DCA6', sideX: '#F0C987', sideZ: '#E0B670' },
  bark: { top: '#C9B8A3', sideX: '#B99E85', sideZ: '#A58D77' },
  roof: { top: '#DDAA8E', sideX: '#D9A588', sideZ: '#C48F73' },
} satisfies Record<string, Faces>

export type StoneFamily = keyof typeof stone

export const ink = {
  text: '#5C5347',
  textDim: '#8A8073',
  outline: '#B7A6C4', // an unbuilt stretch, drawn as its two edges
  mist: '#EDE4F0',
  moss: '#A8C6B5',
  contact: '#C9B8A3',
  coralDeep: '#C4705A',
}

// one restrained accent per option within a scenario: terracotta, sage, ochre, dusk
export const accents = ['#C4705A', '#6E9C86', '#C2923F', '#8E86A8']
