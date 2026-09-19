// Every text tone against every background it is set on. WCAG AA for body text: 4.5:1.
const lin = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4 }
const L = (hex) => { const n = parseInt(hex.slice(1), 16); return 0.2126 * lin(n >> 16) + 0.7152 * lin((n >> 8) & 255) + 0.0722 * lin(n & 255) }
const ratio = (a, b) => { const [x, y] = [L(a), L(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05) }
const text = { 'text #5C5347': '#5C5347', 'secondary #6E6558': '#6E6558', '(asked for) 72% of text on paper = #8A8379': '#8A8379', 'paper on merge button': '#FFFDF8' }
const grounds = { 'paper card': '#FFFDF8', 'veil (drawer)': '#FDF6EC', 'sky top': '#FDF6EC', 'sky mid (blush)': '#F9E4E0', 'sky horizon (mint)': '#DCE9E6', 'merge button': '#5C5347' }
let failed = 0
for (const [tn, t] of Object.entries(text)) for (const [gn, g] of Object.entries(grounds)) {
  if ((tn.startsWith('paper')) !== (gn === 'merge button')) continue
  const r = ratio(t, g); const ok = r >= 4.5; if (!ok && !tn.startsWith('(asked')) failed++
  console.log(`${ok ? 'pass' : 'FAIL'}  ${r.toFixed(2)}:1  ${tn}  on  ${gn}`)
}
process.exit(failed ? 1 : 0)
