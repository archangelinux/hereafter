# Hereafter — frontend

```bash
npm install
npm run dev        # http://localhost:5642 — proxies /api → http://127.0.0.1:8642 (prefix stripped)
npm run build      # tsc --noEmit && vite build
```

- `?person=demo` opens the seeded demo person (token `demo`). `?offline` forces the in-memory sample
  (`src/fixtures`), which is also what loads by itself when `/api/health` is unreachable.
- `?view=line|island`, `?branch=<id>`, `?sheet=composer|compare|log|inventory`, `?read` open a given state.

Two views of the same place, one HUD over both (`V` switches; the choice is remembered):

| | |
|---|---|
| `src/world/` | **Island view**: the 3D world (a drop-in module with the same props as the line). Loaded lazily; if it is missing, throws, or WebGL is unavailable, Line view is the only view and the switch hides. |
| `src/line/` | **Line view**: main as one inked line, forks peeling into lanes, merges rejoining, roads not taken capped, stale branches cut, rare lives as a faint offshoot. Line quality is likelihood. Also the corner map in Island view (`compact`). |
| `src/hud/` | Narration box (a few lines at a time; space / arrows / scroll / click), waypoint cards, branch card with "what could happen", clarifying questions, action bar (merge set apart and heavy, no shortcut), quest log, satchel, mode switch. |
| `src/page/` | "Read the whole chapter": the full prose with margin notes, commit-here and pick; the evidence drawer / codex — the only place figures appear. |
| `src/views/` | Sheets: the Offering, the scenario composer with its live research feed, compare (cards), the merge ceremony, the log, inventory / erase. |
| `src/api.ts` | Client for docs/API.md v1–v2.2 with bearer auth. A v2 route that 404s is answered locally and noted in `api.missing`. |
| `src/theme.ts` | Every colour, type and motion token. |

Vocabulary in the UI: main, branch, commit, undo, switch, compare, merge, pick, log. No probabilities or
shares outside the codex; elsewhere likelihood is line quality and words.
