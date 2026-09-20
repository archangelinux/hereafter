"""What the terminal shows. Only presentation: every number comes from uncertainty.py."""

from __future__ import annotations

from typing import Optional

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import uncertainty
from .model import DIMENSION_MEANING, QA, Session

console = Console()
SOURCE_STYLE = {"linkedin": "blue", "github": "white", "instagram": "magenta", "resume": "cyan", "chat": "yellow",
                "told": "bold green", "web": "cyan", "other": "dim"}


def bar(x: float, width: int = 12, style: str = "green") -> Text:
    n = max(0, min(width, round(x * width)))
    return Text("█" * n, style=style) + Text("░" * (width - n), style="dim")


def _route_title(s: Session, rid: str) -> str:
    return next((r.title for r in s.routes if r.id == rid), rid)


def context_line(items) -> str:
    counts: dict[str, int] = {}
    for i in items:
        counts[i.source] = counts.get(i.source, 0) + 1
    return ", ".join(f"{n} {src}" for src, n in counts.items())


def memory(s: Session, only_new: bool = False) -> None:
    """Everything the agent knows, numbered and tagged by where it came from."""
    t = Table(box=box.SIMPLE_HEAD, show_lines=False, expand=True, title="MEMORY: what I know about you", title_style="bold")
    t.add_column("#", justify="right", style="dim", width=3)
    t.add_column("from", width=10)
    t.add_column("date", style="dim", width=8)
    t.add_column("what it says", ratio=1)
    for i in s.items:
        if only_new and i.source != "told":
            continue
        style = SOURCE_STYLE.get(i.source, "")
        t.add_row(str(i.id), Text(i.source, style=style), i.date, Text(i.text, style="bold green" if i.source == "told" else ""))
    console.print(t)


def routes(s: Session) -> None:
    sc = uncertainty.scores(s)
    lead = uncertainty.leader(sc)
    like = uncertainty.event_likelihoods(s)
    top = max((abs(v) for v in sc.values()), default=0) or 1
    panels = []
    for r in s.routes:
        delta = sc[r.id] - s.initial_scores.get(r.id, sc[r.id])
        head = Text.assemble((f"{r.title}", "bold"), ("  ", ""), bar(max(0, sc[r.id]) / top, 10, "cyan"),
                             (f"  {sc[r.id]:+.3f}", "cyan"),
                             ((f"  {'▲' if delta > 0 else '▼'} {delta:+.3f}", "green" if delta > 0 else "red") if abs(delta) > 1e-4 else ("", "")),
                             ("   ← leads" if r.id == lead else "", "bold yellow"))
        t = Table(box=None, show_header=False, padding=(0, 1), expand=True)
        t.add_column(width=1)
        t.add_column(width=5, justify="right")
        t.add_column(width=12)
        t.add_column(ratio=1)
        t.add_column(style="dim", width=3)
        t.add_column(style="dim", width=10)
        for e in sorted(r.events, key=lambda e: -like[r.id][e.key] * e.impact):
            t.add_row(Text("+" if e.valence > 0 else "−", style="green" if e.valence > 0 else "red"), f"{like[r.id][e.key]:.0%}",
                      bar(like[r.id][e.key], 12, "green" if e.valence > 0 else "red"), e.label, "●" * e.impact + "○" * (3 - e.impact), e.dimension)
        gates = [g for g in s.gates if g.route_id == r.id]
        body: list = [Text(r.summary, style="italic dim"), t]
        for g in gates:
            where = {"record": "from your record", "typical": "typical for someone like you", "answer": "your answer"}[g.basis]
            state = {"open": "", "resolved": " ✓", "skipped": ", skipped"}[g.status]
            body.append(Text.assemble(("needs: ", "dim"), g.requirement, ("  ", ""), bar(g.p_met, 8, "yellow"),
                                      (f" {g.p_met:.0%}", "yellow"), (f" ({where}{state})", "dim")))
        panels.append(Panel(Group(*body), title=head, title_align="left", border_style="cyan" if r.id == lead else "dim"))
    console.print(Panel.fit(Text("ROUTES: how the outcomes look right now (likelihood of each; ●●● = how much it would change your life; score = what a route is worth to you)", style="bold"), border_style="none"))
    for p in panels:
        console.print(p)


def priorities(s: Session) -> None:
    t = Table(box=None, show_header=False, padding=(0, 1))
    for d, p in sorted(s.priorities.probs.items(), key=lambda kv: -kv[1]):
        t.add_row(d, bar(p, 12, "magenta"), f"{p:.0%}", Text(DIMENSION_MEANING[d], style="dim"))
    note = "answered" if s.priorities.status == "resolved" else "" if s.priorities.cites else "nothing in your record points either way yet"
    console.print(Panel(t, title=f"What seems to matter most to you {('(' + note + ')') if note else ''}", title_align="left", border_style="magenta"))


def unknowns(s: Session, ranked: list[uncertainty.GapValue], limit: int = 5) -> None:
    """What the agent is unsure of, and how much each would matter: the reason for the next question."""
    t = Table(box=box.SIMPLE_HEAD, title="UNKNOWNS: what I'm unsure of, and how much it matters", title_style="bold", expand=True)
    t.add_column("unsure about", ratio=1)
    t.add_column("P(true)", justify="right")
    t.add_column("worth knowing", justify="right")
    t.add_column("changes the leader", justify="right")
    for k, g in enumerate(ranked[:limit]):
        style = "bold yellow" if k == 0 else ""
        p = f"{g.p:.0%}" if g.kind == "gate" else f"top: {g.p:.0%}"
        t.add_row(Text(("→ " if k == 0 else "  ") + g.label, style=style), p, f"{g.rel:.0%}", f"{g.flip:.0%} of answers")
    if not ranked:
        t.add_row("nothing left that we are unsure about", "", "", "")
    console.print(t)


def question(s: Session, qa: QA, total: int) -> None:
    body: list = [Text(qa.question, style="bold"), Text("")]
    if qa.grounding:
        body.append(Text("Because I read:", style="dim"))
        for c in qa.grounding:
            item = next((i for i in s.items if i.id == c.item), None)
            body.append(Text(f"  [{c.item}] {item.source if item else ''}: “{c.quote}”", style="dim italic"))
    elif qa.fallback:
        body.append(Text("(a plain question: the worded one didn't pass my checks)", style="dim red"))
    body += [Text(""), Text(qa.why, style="yellow"), Text("")]
    for n, c in enumerate(qa.choices, 1):
        body.append(Text.assemble((f"  {n}. ", "bold cyan"), c.text))
    body.append(Text.assemble(("  s. ", "bold cyan"), ("Not sure", "dim")))
    body.append(Text.assemble(("  or type your own answer.   ", "dim"), ("/memory /why /routes /help  e = finish", "dim")))
    console.print(Panel(Group(*body), title=f"Question {qa.n} of at most {total}", title_align="left", border_style="yellow"))


def delta(s: Session, qa: QA) -> None:
    if qa.kind == "skip":
        console.print(Text("Skipped: stays unknown, and I won't ask about it again.", style="dim"))
        return
    console.print(Text(f"Saved to memory as item {qa.answer_item}: “{qa.answer}”", style="green"))
    rows = []
    for r in s.routes:
        b, a = qa.before.get(r.id, 0), qa.after.get(r.id, 0)
        rows.append(Text.assemble((f"  {r.title}: ", ""), (f"{b:+.3f} → {a:+.3f}  ", "cyan"),
                                  (("▲" if a > b else "▼" if a < b else "•") + f" {a - b:+.3f}", "green" if a > b else "red" if a < b else "dim")))
    moved = any(abs(qa.after.get(r.id, 0) - qa.before.get(r.id, 0)) > 1e-4 for r in s.routes)
    lead_b, lead_a = uncertainty.leader(qa.before), uncertainty.leader(qa.after)
    console.print(Text("What that changed:", style="bold"))
    for row in rows:
        console.print(row)
    if lead_b != lead_a:
        console.print(Text(f"  The leading route changed: {_route_title(s, lead_b)} → {_route_title(s, lead_a)}", style="bold yellow"))
    elif not moved:
        console.print(Text("  Nothing moved: that fits what I expected.", style="dim"))


def why(s: Session, ranked: list[uncertainty.GapValue]) -> None:
    t = Table(box=box.SIMPLE_HEAD, title="WHY THESE QUESTIONS: ranked by how much the answer could improve your choice", title_style="bold", expand=True)
    t.add_column("unknown", ratio=1)
    t.add_column("possible answers")
    t.add_column("EVPI", justify="right")
    t.add_column("flips leader", justify="right")
    t.add_column("affects")
    for g in ranked[:5]:
        answers = " / ".join(f"{name} {p:.0%}" for p, name in g.outcomes if p > 0.005)
        t.add_row(g.label, answers, f"{g.evpi:.4f}", f"{g.flip:.0%}", ", ".join(_route_title(s, r) for r in g.affects))
    console.print(t)
    console.print(Text("EVPI = how much better your choice is on average if you knew the answer. Zero means it could not change the choice, so I would not ask.", style="dim"))


def summary(s: Session) -> None:
    sc = uncertainty.scores(s)
    order = sorted(s.routes, key=lambda r: -sc[r.id])
    margin = sc[order[0].id] - sc[order[1].id] if len(order) > 1 else 0
    t = Table(box=box.ROUNDED, title="WHERE THAT LEAVES YOU", title_style="bold")
    t.add_column("#", style="bold cyan", justify="right")
    t.add_column("route")
    t.add_column("score", justify="right")
    t.add_column("was", justify="right", style="dim")
    t.add_column("best thing about it", ratio=1)
    like = uncertainty.event_likelihoods(s)
    for n, r in enumerate(order, 1):
        good = max((e for e in r.events if e.valence > 0), key=lambda e: like[r.id][e.key], default=None)
        t.add_row(str(s.routes.index(r) + 1), Text(r.title, style="bold" if n == 1 else ""), f"{sc[r.id]:+.3f}", f"{s.initial_scores.get(r.id, 0):+.3f}",
                  f"{like[r.id][good.key]:.0%} {good.label}" if good else "")
    console.print(t)
    console.print(Text(f"{order[0].title} leads by {margin:.3f}." + ("  That is a close call." if margin < 0.01 else ""), style="bold"))
    ranked = uncertainty.rank_gaps(s)
    if ranked:
        console.print(Text(f"What could still tip it: {ranked[0].label} (would change the leader in {ranked[0].flip:.0%} of answers).", style="yellow"))
    if s.stop_reason:
        console.print(Text(f"I stopped asking because {s.stop_reason}.", style="dim"))
    for w in s.warnings:
        console.print(Text(f"⚠ {w}", style="red"))


def saved(folder, decided: Optional[str] = None) -> None:
    console.print(Text(f"Context saved: {folder}/session.json and memory.md", style="green"))
    if decided:
        console.print(Text(f"Decided path: {decided}. The agent's memory is now tied to this path.", style="bold green"))
