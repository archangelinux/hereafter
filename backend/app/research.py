"""Field research on the options of a scenario, at the moment the person branches.

For each option the LLM chooses up to four things worth looking up (never the answers). The
Browserbase Search API finds a page for each; one Browserbase browser session reads them all
through the same readability tiers the cold-start crawl uses; the LLM copies out the figure and
the sentence it came from. Plain code then maps those facts onto simulator parameters, records
on each fact what it was used for, and re-simulates the branch. Every step is logged for the UI.

Nothing here can fail a branch: on any error the branch simply keeps its first simulation.
"""

from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime
from hashlib import sha1
from typing import Optional

from . import branches, config, db, llm, outcome_model, probability
from .ingest import links
from .models import Evidence, ResearchStep, Scenario
from .store import get_store

log = logging.getLogger("hereafter.research")

# Hand-set national baselines for the housing_cost_ratio (see data/SOURCES.md, model assumptions).
BASELINE_HOME_PRICE_CAD = 700_000
SKIP_HOSTS = ("reddit.com", "quora.com", "facebook.com", "youtube.com", "tiktok.com", "instagram.com", "x.com")


@dataclass
class Lead:
    branch_id: str
    question: str
    parameter: str          # a simulator parameter, or "event" for an outcome-model event
    query: str
    event_key: str = ""
    label: str = ""
    rate: object = None
    remembered: Optional[Evidence] = None
    url: str = ""
    title: str = ""
    page: Optional[links.Page] = None
    facts: list = field(default_factory=list)


def _step(branch_id: str, state: str, message: str, url: str | None = None, session_url: str | None = None) -> None:
    db.add_research_step(branch_id, ResearchStep(at=datetime.now().isoformat(timespec="seconds"), state=state,
                                                 message=message, url=url, session_url=session_url))


def _set_status(branch_id: str, status: str) -> None:
    with branches.lock:
        found = db.get_branch(branch_id)
        if found:
            found[0].research = status
            db.save_branch(found[0])


def _same_question(a: str, b: str) -> bool:
    ta, tb = set(re.findall(r"[a-z0-9]{3,}", a.lower())), set(re.findall(r"[a-z0-9]{3,}", b.lower()))
    return bool(ta and tb) and len(ta & tb) / len(ta | tb) >= 0.6


def _recall(leads: list[Lead]) -> None:
    """Before crawling anything: has this already been looked up? Hybrid search over the evidence index."""
    for lead in leads:
        if lead.parameter != "event":
            continue
        for old in get_store().remembered(lead.question):
            if old.question and old.figure and old.snippet and _same_question(old.question, lead.question):
                lead.remembered = old
                _step(lead.branch_id, "found", f"Found in memory: {old.claim}", old.source_url)
                break


def _find_pages(bb, leads: list[Lead]) -> None:
    extra: list[Lead] = []
    for lead in list(leads):
        if lead.remembered:
            continue
        _step(lead.branch_id, "searching", f"Nearest studied group: {lead.question}" if lead.parameter == "event" else lead.question)
        try:
            results = bb.search.web(query=lead.query, num_results=5).results
        except Exception as exc:
            log.info("search failed for %r: %s", lead.query, exc)
            results = []
        picks = [r for r in results if r.url and not any(h in r.url for h in SKIP_HOSTS)]
        if not picks:
            _step(lead.branch_id, "skipped", f"Nothing worth reading turned up for: {lead.question}")
            continue
        lead.url, lead.title = picks[0].url, picks[0].title or picks[0].url
        if lead.parameter == "event" and len(picks) > 1:  # a second source, read only if time allows
            extra.append(Lead(lead.branch_id, lead.question, "event", lead.query, event_key=lead.event_key,
                              label=lead.label, url=picks[1].url, title=picks[1].title or picks[1].url))
    leads += extra


def _read_pages(bb, leads: list[Lead], deadline: float) -> None:
    """One Browserbase session for the whole scenario; each page goes through the usual tiers."""
    from playwright.sync_api import sync_playwright

    todo = [l for l in leads if l.url]
    if not todo:
        return
    with links.session_lock:
        session = bb.sessions.create(project_id=config.BROWSERBASE_PROJECT_ID)
        session_url = f"https://www.browserbase.com/sessions/{session.id}"
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(session.connect_url)
            try:
                context = browser.contexts[0] if browser.contexts else browser.new_context()
                tab = context.pages[0] if context.pages else context.new_page()
                for lead in todo:
                    if time.monotonic() > deadline:
                        _step(lead.branch_id, "skipped", f"Ran out of time before reading {lead.title}", lead.url)
                        continue
                    _step(lead.branch_id, "reading", f"Reading {lead.title}", lead.url, session_url)
                    try:
                        tab.goto(lead.url, wait_until="domcontentloaded", timeout=20_000)
                        got = tab.evaluate(links.READABILITY_JS)
                        lead.page = links._grade(lead.url, got["title"], got["og_title"], got["og_description"],
                                                 got["text"], "live")
                    except Exception as exc:
                        log.info("could not read %s: %s", lead.url, exc)
                        lead.page = links.Page(lead.url, mode="live")
            finally:
                browser.close()


def _extract(lead: Lead) -> None:
    page = lead.page
    if not page or page.tier == "nothing":
        _step(lead.branch_id, "skipped", f"The door was closed at {lead.title}", lead.url)
        return
    text = page.text if page.tier == "substantial" else page.surfaced
    if lead.parameter == "event":
        lead.rate = llm.extract_rate(lead.label, lead.question, lead.url, text[:30_000])
        if lead.rate is None:
            _step(lead.branch_id, "skipped", f"{lead.title} gave no published rate", lead.url)
        return
    lead.facts = llm.extract_facts(lead.question, lead.url, text[:30_000]) or []
    if not lead.facts:
        _step(lead.branch_id, "skipped", f"{lead.title} did not answer the question", lead.url)


def _evidence_id(branch_id: str, url: str, claim: str) -> str:
    return "ev_" + sha1(f"{branch_id}|{url}|{claim}".encode()).hexdigest()[:14]


def _apply(branch, leads: list[Lead]) -> list[Evidence]:
    """Facts -> evidence, and (in plain code) -> simulator parameters."""
    city = branch.assumption.get("city")
    out: list[Evidence] = []
    seen_figures: set = set()
    for lead in leads:
        for fact in lead.facts:
            if (lead.url, fact.value) in seen_figures:  # the same figure restated on the same page
                continue
            seen_figures.add((lead.url, fact.value))
            used_for = None
            value = fact.value
            cad = branches.to_cad(value, fact.currency, city) if value else None
            if value and lead.parameter == "salary" and "salary" not in branch.params and 15_000 < cad < 2_000_000:
                branch.params["salary"] = round(cad)
                used_for = "starting income: placed at this pay within the published income spread for your field and age"
            elif value and lead.parameter == "program_years" and "graduates_in" not in branch.params and 0 < value <= 8:
                branch.params["graduates_in"] = int(round(value))
                used_for = "how many years of study come before work begins"
            elif value and lead.parameter == "home_price" and cad > 100_000:
                branch.params["housing_cost_ratio"] = round(cad / BASELINE_HOME_PRICE_CAD, 2)
                used_for = "how hard buying a home is here, relative to the national picture behind the ownership table"
            # Rents are kept as evidence for the narrative only: a room in a shared flat and a whole
            # apartment are not comparable, so a rent never sets a simulator parameter.
            out.append(Evidence(
                id=_evidence_id(branch.id, lead.url, fact.claim), person_id=branch.person_id, branch_id=branch.id,
                kind="researched", claim=fact.claim, value=f"{value:,.0f}" if value else None,
                unit=" ".join(x for x in (fact.currency, fact.unit) if x) or None,
                source_title=lead.title, source_url=lead.url, retrieved_at=date.today().isoformat(),
                snippet=fact.snippet[:500], used_for=used_for,
            ))
            _step(branch.id, "found", fact.claim, lead.url)
    return out


def _apply_rates(branch, leads: list[Lead]) -> tuple[list[Evidence], bool]:
    """Published rates -> sourced events, but only through outcome_model.apply_rate's checks."""
    by_key = {e["key"]: e for e in branch.model.get("events", [])}
    out, changed = [], False
    for lead in leads:
        event = by_key.get(lead.event_key)
        if event is None or event["basis"] != "estimated":  # already sourced from an earlier page
            continue
        if lead.remembered:
            old = lead.remembered
            rate = llm.PublishedRate(claim=old.claim, figure_as_written=old.figure, span_days=old.span_days,
                                     snippet=old.snippet, gap=old.gap or "", gap_is_large=True)
            url, title = old.source_url, old.source_title
        elif lead.rate is not None:
            rate, url, title = lead.rate, lead.url, lead.title
        else:
            continue
        evidence_id = _evidence_id(branch.id, url or "", rate.claim)
        arithmetic = outcome_model.apply_rate(event, rate, evidence_id, branch.span.unit)
        if arithmetic is None:
            _step(branch.id, "skipped", f"A figure from {title} could not be verified in its own quoted text; left as an estimate", url)
            continue
        changed = True
        out.append(Evidence(
            id=evidence_id, person_id=branch.person_id, branch_id=branch.id, kind="researched", claim=rate.claim,
            value=rate.figure_as_written, unit=None, source_title=title, source_url=url,
            retrieved_at=date.today().isoformat(), snippet=rate.snippet[:500], used_for=arithmetic,
            question=lead.question, figure=rate.figure_as_written, span_days=rate.span_days,
            reference_class=lead.question, gap=rate.gap or None,
        ))
        if not lead.remembered:
            _step(branch.id, "found", rate.claim, url)
    return out, changed


def research_scenario(scenario: Scenario, only: Optional[list[str]] = None) -> None:
    """Background task. Researches the scenario's branches (or just `only`) inside one time budget."""
    branch_ids = list(only or scenario.branch_ids)
    can_browse = config.BROWSERBASE_API_KEY and config.BROWSERBASE_PROJECT_ID
    if not (config.RESEARCH_ENABLED and llm.enabled() and can_browse):
        for bid in branch_ids:
            _set_status(bid, "none")
        return
    deadline = time.monotonic() + config.RESEARCH_BUDGET_SECONDS * max(1, len(branch_ids))
    try:
        from browserbase import Browserbase

        bb = Browserbase(api_key=config.BROWSERBASE_API_KEY)
        options = {o.id: o for o in scenario.options}
        leads: list[Lead] = []

        def plan(bid: str) -> list[Lead]:
            _set_status(bid, "running")
            branch, _ = db.get_branch(bid)
            option = options[branch.option_id]
            known = {k: v for k, v in {**branch.assumption, **branch.params}.items() if k != "salary_source"}
            found = [Lead(bid, e["reference_class"], "event", e["search_query"], event_key=e["key"], label=e["label"])
                     for e in branch.model.get("events", [])
                     if e.get("reference_class") and e.get("search_query") and e["basis"] == "estimated"][:4]
            if branches.has_background(branch.span):  # pay, rent, program length only matter to the life-course underneath
                questions = llm.plan_research(scenario.situation, option.title, option.details, known) or []
                found += [Lead(bid, q.question, q.parameter, q.search_query) for q in questions][:3]
            return found

        with ThreadPoolExecutor(max_workers=4) as pool:
            for found in pool.map(plan, branch_ids):
                leads += found
            _recall(leads)
            _find_pages(bb, leads)
            _read_pages(bb, leads, deadline)
            list(pool.map(_extract, [l for l in leads if l.url]))

        person = db.get_person(scenario.person_id)
        for bid in branch_ids:
            with branches.lock:
                branch, _ = db.get_branch(bid)
                before = dict(branch.params)
                mine = [l for l in leads if l.branch_id == bid]
                sourced, changed = _apply_rates(branch, [l for l in mine if l.parameter == "event"])
                if changed:  # an estimated event now has a published base rate: recombine with Jev's scores
                    probability.assess_events(branch.model.get("events", []))
                get_store().add_evidence(_apply(branch, [l for l in mine if l.parameter != "event"]) + sourced)
                branch.research = "done"
                if (branch.params != before or changed) and branch.status == "open":
                    branch.revision += 1
                    branches.resimulate(person, branch)
                else:
                    db.save_branch(branch)
            _step(bid, "done", "Research folded into this path.")
    except Exception:
        log.exception("research failed; branches keep their first simulation")
        for bid in branch_ids:
            _set_status(bid, "failed")
            _step(bid, "done", "Research could not finish; this path rests on the statistics alone.")
