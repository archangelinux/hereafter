"""The agent's memory as a readable markdown file (written next to session.json after every step).

It is the same information the terminal shows with /memory: what the agent knows, where it came
from, what it is unsure of, what it asked and what each answer changed.
"""

from __future__ import annotations

from . import uncertainty
from .model import DIMENSION_MEANING, Session


def _bar(x: float, width: int = 10) -> str:
    n = max(0, min(width, round(x * width)))
    return "█" * n + "░" * (width - n)


def markdown(s: Session) -> str:
    likely = uncertainty.event_likelihoods(s)
    scores = uncertainty.scores(s)
    lead = uncertainty.leader(scores)
    out = [f"# Memory: {s.decision}", "",
           f"- session `{s.id}` · about `{s.who}` · status **{s.status}**"
           + (f" · decided **{next((r.title for r in s.routes if r.id == s.decided_route), s.decided_route)}**" if s.decided_route else ""), ""]

    out += ["## What the agent knows about you", "", "| # | source | date | what it says |", "|---|---|---|---|"]
    for i in s.items:
        out.append(f"| {i.id} | {i.source}{' **(your answer)**' if i.source == 'told' else ''} | {i.date} | {i.text} |")

    out += ["", "## Routes", ""]
    for r in s.routes:
        mark = " ← currently leads" if r.id == lead and len(s.routes) > 1 else ""
        out += [f"### {r.title}{mark}", r.summary, "", f"outlook score: {scores.get(r.id, 0):+.3f} (started at {s.initial_scores.get(r.id, 0):+.3f})", ""]
        for e in r.events:
            sign = "+" if e.valence > 0 else "−"
            evidence = "; ".join(f"[{c.item}] “{c.quote}”" for c in e.cites) or "no evidence in the record: scored neutral"
            out.append(f"- {sign} **{likely[r.id][e.key]:.0%}** {e.label} _({e.dimension}, impact {e.impact}/3)_ · fit {e.personal_fit}/{e.experience_fit} · {evidence}")
        gates = [g for g in s.gates if g.route_id == r.id]
        if gates:
            out += ["", "Requirements this route depends on:"]
            for g in gates:
                where = {"record": "from your record", "typical": "a typical person's base rate: your record doesn't say", "answer": "your answer"}[g.basis]
                out.append(f"- {g.requirement} — P(true) {g.p_met:.0%} `{_bar(g.p_met)}` ({g.status}; {where})"
                           + (" · evidence " + ", ".join(f"[{i}]" for i in sorted({c.item for c in g.cites})) if g.cites else ""))
        out.append("")

    out += ["## What matters most to you", ""]
    for d, p in sorted(s.priorities.probs.items(), key=lambda kv: -kv[1]):
        out.append(f"- {d} ({DIMENSION_MEANING[d]}): {p:.0%} `{_bar(p)}`")
    out.append(f"\nstatus: {s.priorities.status}" + (" · evidence " + "; ".join(f"[{c.item}]" for c in s.priorities.cites) if s.priorities.cites else " · nothing in the record pointed either way"))

    out += ["", "## Questions", ""]
    if not s.qas:
        out.append("None asked yet.")
    for q in s.qas:
        out += [f"**Q{q.n}.** {q.question}" + ("  _(plain fallback question)_" if q.fallback else ""),
                f"- unknown: `{q.gap}` · worth {q.evpi:.4f} · could change the leader in {q.flip:.0%} of answers",
                f"- why it matters: {q.why}",
                "- choices: " + " / ".join(f"{c.text} → {c.resolves}" for c in q.choices),
                f"- answer: {q.answer if q.answer is not None else '(waiting)'}" + (f" (saved as item {q.answer_item})" if q.answer_item else "")]
        if q.before and q.after:
            moved = [f"{next((r.title for r in s.routes if r.id == rid), rid)} {q.before[rid]:+.3f} → {q.after[rid]:+.3f}" for rid in q.before if abs(q.after[rid] - q.before[rid]) > 1e-4]
            out.append("- changed: " + ("; ".join(moved) or "nothing moved"))
        out.append("")

    if s.stop_reason:
        out.append(f"Stopped asking because {s.stop_reason}.")
    for w in s.warnings:
        out.append(f"> ⚠ {w}")
    return "\n".join(out) + "\n"
