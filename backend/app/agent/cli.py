"""Talk to the agent in the terminal.

    python -m app.agent --fixture dev -q "Take the Berlin startup offer, stay at Acme, or start my own thing?"
    python -m app.agent --fixture maya -q "Waterloo or McMaster?" --answers "1;s;e" --decide 1
    python -m app.agent --show LATEST            # look at what a saved session remembers
    python -m app.agent --fixtures               # the built-in test people
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional

from rich.text import Text

from . import render
from .context import fixture_names, load
from .engine import Agent, AgentError, sessions_dir
from .prompts import LLMBrain

console = render.console
HELP = ("Type a number to pick an answer, 's' if you're not sure, or just write your own answer.\n"
        "  /memory  everything I know about you      /why  why I chose this question\n"
        "  /routes  the routes and their outcomes    e     stop asking and see where that leaves you")


def _latest() -> str:
    found = sorted(p.name for p in sessions_dir().glob("*/session.json") for p in [p.parent])
    if not found:
        raise AgentError(f"no saved sessions in {sessions_dir()}")
    return found[-1]


def show(session_id: str) -> None:
    sid = _latest() if session_id.upper() == "LATEST" else session_id
    s = Agent.load_session(sid)
    console.print(Text(f"Session {s.id}  ·  {s.who}  ·  {s.status}", style="bold"))
    console.print(Text(f"Decision: {s.decision}", style="bold"))
    render.memory(s)
    render.routes(s)
    render.priorities(s)
    for qa in s.qas:
        console.print(Text(f"Q{qa.n}. {qa.question}", style="bold yellow"))
        console.print(Text(f"    → {qa.answer if qa.answer is not None else '(unanswered)'}", style="green"))
    render.summary(s)
    console.print(Text(f"\nFiles: {sessions_dir() / s.id}", style="dim"))


class Input:
    """Where answers come from: a script (--answers), or the keyboard."""

    def __init__(self, script: Optional[list[str]]):
        self.script = script

    def read(self, prompt: str) -> Optional[str]:
        """One line, or None at the end of the script or of the keyboard input."""
        if self.script is not None:
            if not self.script:
                return None
            line = self.script.pop(0)
            console.print(Text(f"{prompt}{line}", style="dim"))
            return line
        try:
            return console.input(f"[bold cyan]{prompt}[/]")
        except (EOFError, KeyboardInterrupt):
            console.print()
            return None


def run(args) -> int:
    ctx, who = load(args.fixture, args.person)
    agent = Agent(LLMBrain(), ctx, who)
    decision = args.question or (console.input("[bold]What are you deciding?[/] ").strip() if sys.stdin.isatty() else "")
    console.print(Text(f"\nAbout: {who}: {len(ctx.items)} things known ({render.context_line(ctx.items)})", style="dim"))

    with console.status("Working…") as status:
        agent.say = status.update
        agent.start(decision, [o for o in args.options.split("|")] if args.options else None)
    s = agent.s
    render.routes(s)
    render.priorities(s)
    render.unknowns(s, agent.ranked())
    for w in s.warnings:
        console.print(Text(f"⚠ {w}", style="red"))

    answers = Input([a.strip() for a in args.answers.split(";")] if args.answers else None)

    while True:
        with console.status("Working…") as status:
            agent.say = status.update
            qa = agent.next_question()
        if qa is None:
            break
        render.question(s, qa, 3)
        while True:
            raw = answers.read("> ")
            if raw is None or raw.lower() in ("e", "end", "/end"):
                agent.s.status, agent.s.stop_reason = "done", "you chose to finish"
                agent.save()
                qa = None
                break
            low = raw.lower()
            if not raw:
                continue
            if low in ("/help", "?"):
                console.print(HELP)
            elif low == "/memory":
                render.memory(s)
            elif low == "/why":
                render.why(s, agent.ranked())
            elif low == "/routes":
                render.routes(s)
            else:
                try:
                    if low in ("s", "skip"):
                        done = agent.answer("skip")
                    elif raw.isdigit():
                        done = agent.answer("choice", raw)
                    else:
                        with console.status("Reading your answer…"):
                            done = agent.answer("text", raw)
                except AgentError as exc:
                    console.print(Text(str(exc), style="red"))
                    continue
                render.delta(s, done)
                if done.kind != "skip" and args.memory:
                    render.memory(s, only_new=True)
                render.unknowns(s, agent.ranked())
                break
        if qa is None:
            break

    console.print()
    render.summary(s)
    decided = None
    choice = args.decide
    if choice is None and sys.stdin.isatty() and not args.answers:
        choice = (console.input("\n[bold]Decide on a route?[/] Enter its number, or press Enter to leave it open: ").strip() or None)
    if choice and str(choice).isdigit() and 1 <= int(choice) <= len(s.routes):
        agent.decide(s.routes[int(choice) - 1].id)
        decided = s.routes[int(choice) - 1].title
    folder = agent.save()
    render.saved(folder, decided)
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="python -m app.agent", description="A decision agent that asks the few questions that matter.")
    p.add_argument("--fixture", help=f"a built-in test person ({', '.join(fixture_names())})")
    p.add_argument("--person", help="a person already in the app's store (Elastic or local)")
    p.add_argument("-q", "--question", help="the decision, in your words")
    p.add_argument("--options", help="the options, separated by | (otherwise found in the question)")
    p.add_argument("--answers", help="scripted answers separated by ; (a number, s to skip, e to end, or text)")
    p.add_argument("--decide", help="pick this route number at the end (skips the prompt)")
    p.add_argument("--memory", action="store_true", help="after each answer, also show the memory it created")
    p.add_argument("--show", metavar="SESSION", help="print a saved session (use LATEST for the newest)")
    p.add_argument("--fixtures", action="store_true", help="list the built-in test people")
    args = p.parse_args(argv)
    try:
        if args.fixtures:
            console.print("Built-in test people: " + ", ".join(fixture_names()))
            return 0
        if args.show:
            show(args.show)
            return 0
        if not (args.fixture or args.person):
            p.error("choose who this is about: --fixture NAME or --person ID (or --show / --fixtures)")
        return run(args)
    except AgentError as exc:
        console.print(Text(f"\n{exc}", style="bold red"))
        return 1
    except SystemExit as exc:
        if exc.code not in (0, None):
            console.print(Text(f"\n{exc}", style="bold red"))
        return int(exc.code or 0) if isinstance(exc.code, int) else 1


if __name__ == "__main__":
    raise SystemExit(main())
