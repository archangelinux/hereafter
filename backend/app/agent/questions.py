"""Turning a chosen unknown into a good question.

The topic was picked by `uncertainty.rank_gaps`. Here the model only *words* it, and code checks
the result (verify.check_question). If the first attempt fails, the model is told exactly what was
wrong and tries once more. If that fails too, a plain question that makes no claim about the person
is used, and the QA is marked `fallback` so it shows.
"""

from __future__ import annotations

from . import verify
from .context import Context, numbered
from .model import DIMENSION_MEANING, DIMENSIONS, Choice, Cite, QA, Session
from .prompts import Brain
from .uncertainty import GapValue

TOP_CANDIDATES = 4
PLAIN = {"money": "Earning more", "growth": "Learning and growing", "stability": "Security and predictability",
         "wellbeing": "My health and free time", "freedom": "Control over my own path"}


def _gate(s: Session, gid: str):
    return next(g for g in s.gates if g.id == gid)


def _route_title(s: Session, rid: str) -> str:
    return next((r.title for r in s.routes if r.id == rid), rid)


def candidates(s: Session) -> list[str]:
    """The dimensions most worth offering as answers, most likely first."""
    ranked = sorted(DIMENSIONS, key=lambda d: s.priorities.probs.get(d, 0), reverse=True)
    return ranked[:TOP_CANDIDATES]


def spec_for(s: Session, gap: GapValue) -> dict:
    asked = [q.question for q in s.qas]
    if gap.kind == "gate":
        g = _gate(s, gap.gap)
        return {"kind": "requirement", "decision": s.decision, "unknown": g.requirement,
                "about_route": _route_title(s, g.route_id), "questions_already_asked": asked}
    return {"kind": "priority", "decision": s.decision, "unknown": "what matters most to them when choosing between these options",
            "options": [r.title for r in s.routes],
            "candidate_dimensions": {d: DIMENSION_MEANING[d] for d in candidates(s)}, "questions_already_asked": asked}


def why_it_matters(s: Session, gap: GapValue) -> str:
    """Said in plain words from the numbers; never written by the model."""
    pct = f"Your answer could change which option comes out ahead in {gap.flip:.0%} of cases."
    if gap.kind == "priorities":
        return f"How much each thing matters to you changes how these options rank. {pct}"
    which = _route_title(s, gap.affects[0]) if len(gap.affects) == 1 else "one of these options"
    return f"If this doesn't hold, “{which}” falls apart. {pct}"


def _allowed_text(s: Session) -> str:
    # where an item came from is shown to the model with the record, so naming it is not inventing
    parts = [i.text for i in s.items] + [i.source for i in s.items] + ["LinkedIn", "GitHub", "Instagram", "ChatGPT", "resume"] + [s.decision]
    for r in s.routes:
        parts += [r.title, r.summary] + [e.label for e in r.events]
    parts += [g.requirement for g in s.gates]
    return " ".join(parts)


def _choice_problems(s: Session, gap: GapValue, choices: list[Choice]) -> list[str]:
    got = {c.resolves.strip().lower() for c in choices}
    if gap.kind == "gate":
        if not got <= {"met", "unmet"} or got != {"met", "unmet"}:
            return ["for a requirement question the choices must resolve to 'met' and 'unmet' (at least one of each)"]
    else:
        allowed = set(candidates(s))
        if not got <= allowed or len(got) < 2:
            return [f"for a priority question each choice must resolve to one of {sorted(allowed)}, using at least two"]
    return []


def fallback(s: Session, gap: GapValue) -> tuple[str, list[Choice]]:
    if gap.kind == "gate":
        g = _gate(s, gap.gap)
        return (f"Is this true for you: “{g.requirement.rstrip('.?!')}”?",
                [Choice(text="Yes, that's true", resolves="met"), Choice(text="No, it isn't", resolves="unmet")])
    return ("When you weigh these options, which matters most to you?",
            [Choice(text=PLAIN[d], resolves=d) for d in candidates(s)[:3]])


def write(brain: Brain, s: Session, ctx: Context, gap: GapValue) -> QA:
    spec = spec_for(s, gap)
    query = f"{s.decision} {spec['unknown']}"
    items = ctx.relevant(query, 18)
    record = numbered(items)
    by_id = ctx.by_id()
    allowed = _allowed_text(s)

    feedback: list[str] = []
    for attempt in range(2):
        try:
            got = brain.write_question(spec, record, feedback)
        except Exception as exc:  # a failed call is a failed attempt, not a crash
            got, feedback = None, [f"the call failed: {type(exc).__name__}"]
        if got is None:
            continue
        choices = [Choice(text=c.text.strip(), resolves=c.resolves.strip().lower()) for c in got.choices]
        grounding = [Cite(item=c.item, quote=c.quote) for c in got.grounding]
        feedback = verify.check_question(got.question.strip(), choices, grounding, by_id, allowed) + _choice_problems(s, gap, choices)
        if not feedback:
            good = verify.valid_cites(grounding, by_id)
            return QA(n=len(s.qas) + 1, gap=gap.gap, question=got.question.strip(), choices=choices, grounding=good,
                      why=why_it_matters(s, gap), evpi=gap.evpi, flip=gap.flip)

    q, choices = fallback(s, gap)
    s.warnings.append(f"Question {len(s.qas) + 1}: the written question failed checks ({'; '.join(feedback) or 'no answer from the model'}); asked a plain one instead.")
    return QA(n=len(s.qas) + 1, gap=gap.gap, question=q, choices=choices, grounding=[], why=why_it_matters(s, gap),
              evpi=gap.evpi, flip=gap.flip, fallback=True)
