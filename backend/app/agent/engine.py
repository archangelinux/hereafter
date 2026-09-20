"""The agent loop.

    start()            lay out routes, judge them against the person's record, find what is unknown
    next_question()    the unknown worth the most (uncertainty.py), worded and checked (questions.py)
    answer()/skip()    fold the answer into memory, re-score, say what moved
    decide()           the person picks a route; the session is saved with that path marked

At most MAX_QUESTIONS are asked, and fewer when nothing left could change the answer. The session
is saved to disk after every step, so what the agent knows is never only in memory.
"""

from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from .. import config, ticket
from . import memory, questions, uncertainty, verify
from .context import Context, numbered
from .model import DIMENSIONS, QA, Cite, Event, Gate, Priorities, Route, Session
from .prompts import Brain

MAX_QUESTIONS = 3
MAX_ROUTES = 4
MAX_EVENTS = 7
MAX_GATES = 3
ANSWERED_MET, ANSWERED_UNMET = 0.97, 0.03
PRIORITY_CONFIDENT = 0.85


class AgentError(Exception):
    """Something the agent cannot carry on without (the model is off, or laid out no routes)."""


def sessions_dir() -> Path:
    return Path(os.getenv("HEREAFTER_SESSIONS") or config.ROOT / "backend" / "sessions")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "decision"


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


def _key(raw: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", raw.strip().lower()).strip("_")[:50] or "outcome"


class Agent:
    def __init__(self, brain: Brain, context: Context, who: str, root: Optional[Path] = None,
                 say: Optional[Callable[[str], None]] = None):
        self.brain, self.ctx, self.who = brain, context, who
        self.root = root or sessions_dir()
        self.say = say or (lambda _msg: None)
        self.s: Optional[Session] = None

    # --- persistence ---

    @property
    def folder(self) -> Path:
        return self.root / self.s.id

    def save(self) -> Path:
        self.s.items = [i.model_copy() for i in self.ctx.items]
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / "session.json").write_text(self.s.model_dump_json(indent=1))
        (self.folder / "memory.md").write_text(memory.markdown(self.s))
        return self.folder

    @staticmethod
    def load_session(session_id: str, root: Optional[Path] = None) -> Session:
        path = (root or sessions_dir()) / session_id / "session.json"
        if not path.exists():
            raise AgentError(f"no saved session '{session_id}' in {path.parent.parent}")
        return Session.model_validate_json(path.read_text())

    # --- 1. start ---

    def start(self, decision: str, options: Optional[list[str]] = None) -> Session:
        decision = decision.strip()
        if not decision:
            raise AgentError("say what you are deciding")
        titles = [o.strip() for o in options if o.strip()] if options else ticket.parse(decision)[1]
        titles = titles[:MAX_ROUTES]
        self.s = Session(id=f"{datetime.now():%Y%m%d-%H%M%S}-{_slug(decision)}", created=datetime.now().isoformat(timespec="seconds"),
                         decision=decision, who=self.who, items=list(self.ctx.items))
        record = numbered(self.ctx.relevant(decision, 30))

        self.say("Imagining what could happen on each route…")
        proposal = self._call(self.brain.propose_routes, decision, titles, record, self.ctx.about)
        if proposal is None or len(proposal.routes) < 2:
            raise AgentError("the model could not lay out the routes (is OPENAI_API_KEY set and HEREAFTER_LLM=on?). Nothing was saved.")
        for i, pr in enumerate(proposal.routes[:MAX_ROUTES]):
            seen: set[str] = set()
            events = []
            for pe in pr.events[:MAX_EVENTS]:
                key = _key(pe.key)
                while key in seen:
                    key += "_2"
                seen.add(key)
                events.append(Event(key=key, label=pe.label.strip(), dimension=pe.dimension, valence=pe.valence,
                                    impact=pe.impact, bin=pe.bin, category=pe.category))
            self.s.routes.append(Route(id=f"r{i + 1}", title=(titles[i] if i < len(titles) else pr.title).strip(), summary=pr.summary.strip(), events=events))

        self.say("Judging each outcome against what we know about you…")
        by_id = self.ctx.by_id()
        with ThreadPoolExecutor(max_workers=len(self.s.routes) + 1) as pool:
            route_jobs = [pool.submit(self._call, self.brain.judge_route, decision,
                                      {"title": r.title, "summary": r.summary, "events": [e.model_dump() for e in r.events]}, record)
                          for r in self.s.routes]
            prio_job = pool.submit(self._call, self.brain.judge_priorities, decision, [r.title for r in self.s.routes], record)
            judged = [j.result() for j in route_jobs]
            priorities = prio_job.result()
        for route, j in zip(self.s.routes, judged):
            self._apply_route_judgement(route, j, by_id)
        self._apply_priorities(priorities, by_id)
        self.s.initial_scores = uncertainty.scores(self.s)
        self.save()
        return self.s

    def _call(self, fn, *args):
        try:
            return fn(*args)
        except Exception as exc:
            self.s.warnings.append(f"{fn.__name__} failed: {type(exc).__name__}: {str(exc)[:120]}")
            return None

    def _apply_route_judgement(self, route: Route, j, by_id) -> None:
        if j is None:
            self.s.warnings.append(f"Route '{route.title}': the judge was unavailable, so its outcomes are scored neutral and no requirements were found.")
            return
        judged = {_key(e.key): e for e in j.events}
        for e in route.events:
            got = judged.get(e.key)
            cites = verify.valid_cites([Cite(item=c.item, quote=c.quote) for c in got.cites], by_id) if got else []
            if got and cites:  # receipts: scores move off neutral only when they can be backed
                e.personal_fit, e.experience_fit = (int(_clamp(x, 1, 5)) for x in (got.personal_fit, got.experience_fit))
                e.difficulty, e.accessibility = (int(_clamp(x, 1, 5)) for x in (got.difficulty, got.accessibility))
                e.evidence_strength = int(_clamp(got.evidence_strength, 1, 5))
                e.cites, e.note = cites, got.note.strip()
            elif got:
                e.difficulty = int(_clamp(got.difficulty, 1, 5))  # difficulty is about the outcome, not the person
                e.note = "no quotable evidence in the record; fit scored neutral"
        keys = {e.key for e in route.events}
        for n, g in enumerate(j.gates[:MAX_GATES], 1):
            cites = verify.valid_cites([Cite(item=c.item, quote=c.quote) for c in g.cites], by_id)
            # no receipt, no personal claim: fall back to the typical person's base rate
            p = _clamp(g.p_met, 0.05, 0.95) if cites else _clamp(g.p_typical, 0.1, 0.9)
            self.s.gates.append(Gate(id=f"{route.id}.g{n}", route_id=route.id, requirement=g.requirement.strip(),
                                     applies_to=[_key(k) for k in g.applies_to if _key(k) in keys], p_met=round(p, 3),
                                     basis="record" if cites else "typical", cites=cites))

    def _apply_priorities(self, j, by_id) -> None:
        if j is None:
            self.s.warnings.append("Priorities could not be judged; assuming no leaning.")
            return
        cites = verify.valid_cites([Cite(item=c.item, quote=c.quote) for c in j.cites], by_id)
        if not cites:
            return
        raw = {d: 0.02 for d in DIMENSIONS}
        for p in j.probs:
            raw[p.dimension] = max(0.02, float(p.p))
        total = sum(raw.values())
        self.s.priorities = Priorities(probs={d: round(v / total, 4) for d, v in raw.items()}, cites=cites)

    # --- 2. ask ---

    def ranked(self):
        return uncertainty.rank_gaps(self.s)

    def pending(self) -> Optional[QA]:
        return next((q for q in self.s.qas if q.answer is None and q.kind != "skip"), None)

    def next_question(self) -> Optional[QA]:
        """The next question, or None when asking is over (the reason is in `session.stop_reason`)."""
        s = self.s
        if self.pending():
            return self.pending()
        if len(s.qas) >= MAX_QUESTIONS:
            return self._stop(f"asked the maximum of {MAX_QUESTIONS} questions")
        ranked = self.ranked()
        # The first question is always asked when anything is unknown: an advisor who asks nothing is not
        # useful, and a decision that looks settled is worth a check. Later ones must earn their place.
        why_stop = "there is nothing left that we are unsure about" if not ranked else (uncertainty.should_stop(ranked) if s.qas else None)
        if why_stop:
            return self._stop(why_stop)
        self.say("Choosing the question worth the most…")
        qa = questions.write(self.brain, s, self.ctx, ranked[0])
        s.qas.append(qa)
        self.save()
        return qa

    def _stop(self, reason: str) -> None:
        self.s.status, self.s.stop_reason = "done", reason
        self.save()
        return None

    # --- 3. answer ---

    def answer(self, kind: str, value: str = "") -> QA:
        """kind: "choice" (value = 1-based number), "text" (value = their words) or "skip"."""
        qa = self.pending()
        if qa is None:
            raise AgentError("there is no open question")
        s = self.s
        qa.before = uncertainty.scores(s)
        target = next((g for g in s.gates if g.id == qa.gap), None)

        if kind == "skip":
            qa.kind, qa.answer = "skip", "(not sure)"
            if target:
                target.status = "skipped"
            else:
                s.priorities.status = "skipped"
            qa.after = uncertainty.scores(s)
            self.save()
            return qa

        chosen = None
        if kind == "choice":
            n = int(value)
            if not 1 <= n <= len(qa.choices):
                raise AgentError(f"choose 1-{len(qa.choices)}")
            chosen = qa.choices[n - 1]
            said = chosen.text
        else:
            said = value.strip()
            if not said:
                raise AgentError("say something, or skip")
            chosen = next((c for c in qa.choices if verify.norm(c.text) == verify.norm(said)), None)
            kind = "choice" if chosen else "text"
        qa.kind, qa.answer = kind, said

        # memory first: the answer is a new numbered item, so later questions can build on it
        item = self.ctx.add_told(f"Asked “{qa.question}” — they said: {said}")
        qa.answer_item = item.id
        s.items = list(self.ctx.items)

        if chosen:
            self._resolve(qa.gap, chosen.resolves, ANSWERED_MET if chosen.resolves == "met" else ANSWERED_UNMET)
        open_gaps = [g for g in self._open_gaps() if not (chosen and g["id"] == qa.gap)]
        if open_gaps:
            reading = self._call(self.brain.read_answer, qa.question, said, open_gaps)
            for u in (reading.updates if reading else []):
                if u.resolves.lower() == "unclear" or not verify.norm(u.quote) or verify.norm(u.quote) not in verify.norm(said):
                    continue  # only what their own words support
                self._resolve(u.gap, u.resolves.lower(), u.p)
        if not chosen and target and target.status == "open":
            target.status = "skipped"  # a free-text answer we could not read as settling it: do not ask again
            s.warnings.append(f"Question {qa.n}: the answer did not clearly settle it, so it stays unknown.")
        if not chosen and qa.gap == "priorities" and s.priorities.status == "open":
            s.priorities.status = "skipped"

        qa.after = uncertainty.scores(s)
        self.save()
        return qa

    def _open_gaps(self) -> list[dict]:
        out = [{"id": g.id, "kind": "requirement", "statement": g.requirement, "p_met": g.p_met}
               for g in self.s.gates if g.status == "open"]
        if self.s.priorities.status == "open":
            out.append({"id": "priorities", "kind": "priorities", "statement": "which dimension matters most to them",
                        "dimensions": list(DIMENSIONS)})
        return out

    def _resolve(self, gap: str, resolves: str, p: float) -> None:
        if gap == "priorities":
            if resolves in DIMENSIONS:
                rest = (1 - PRIORITY_CONFIDENT) / (len(DIMENSIONS) - 1)
                self.s.priorities.probs = {d: (PRIORITY_CONFIDENT if d == resolves else round(rest, 4)) for d in DIMENSIONS}
                self.s.priorities.status = "resolved"
            return
        g = next((g for g in self.s.gates if g.id == gap), None)
        if g is None or resolves not in ("met", "unmet"):
            return
        g.p_met = round(_clamp(p, 0.85, ANSWERED_MET) if resolves == "met" else _clamp(p, ANSWERED_UNMET, 0.15), 3)
        g.status, g.basis = "resolved", "answer"

    # --- 4. finish ---

    def decide(self, route_id: str) -> Session:
        if not any(r.id == route_id for r in self.s.routes):
            raise AgentError(f"no route '{route_id}'")
        self.s.status, self.s.decided_route = "decided", route_id
        self.save()
        return self.s
