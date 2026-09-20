"""LinkedIn, read through Stagehand when a signed-in browser is available (docs/STAGEHAND.md).

Logged out, LinkedIn shows a wall and `links` can only keep a glimpse. If HEREAFTER_LINKEDIN_CONTEXT names a
Browserbase context that is already signed in to LinkedIn, Stagehand opens the profile on it, expands the
"Show all" sections and extracts the roles and schools. It first checks that the login still holds: if
LinkedIn sends the browser to a sign-in page instead, nothing is read here and the ordinary page read runs.

What comes back is only *page text*: it returns a `links.Page`, so it goes through the same extraction,
encrypted cache and consent gate as any page. Hereafter has no sign-in step of its own and never handles a
password. Every failure returns None.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from pydantic import BaseModel

from .. import config
from . import links

log = logging.getLogger("hereafter.ingest")

LOGGED_OUT = ("/login", "/authwall", "/checkpoint", "/uas/")


class Role(BaseModel):
    company: str = ""
    title: str = ""
    start: str = ""
    end: str = ""
    location: str = ""
    description: str = ""


class School(BaseModel):
    school: str = ""
    degree: str = ""
    start: str = ""
    end: str = ""


class Experience(BaseModel):
    roles: list[Role] = []


class Education(BaseModel):
    schools: list[School] = []


def enabled() -> bool:
    return bool(config.LINKEDIN_CONTEXT and config.BROWSERBASE_API_KEY and config.BROWSERBASE_PROJECT_ID)


def _model_key() -> Optional[str]:
    return os.getenv("OPENAI_API_KEY") or None


def _signed_out(url: str) -> bool:
    return any(part in url for part in LOGGED_OUT)


def _text(roles: list[Role], schools: list[School]) -> str:
    lines = []
    for r in roles:
        when = " – ".join(x for x in (r.start, r.end) if x)
        head = f"{r.title} at {r.company}" if r.title and r.company else r.title or r.company
        lines.append(" ".join(x for x in (f"Work: {head}", f"({when})" if when else "", f"in {r.location}." if r.location else "", r.description) if x.strip()))
    for s in schools:
        when = " – ".join(x for x in (s.start, s.end) if x)
        lines.append(" ".join(x for x in (f"Education: {s.degree + ' at ' if s.degree else ''}{s.school}", f"({when})" if when else "") if x.strip()))
    return "\n".join(lines)


async def _read(context_id: str, url: str) -> str:
    from stagehand import Stagehand, browserbase

    browser = await browserbase.launch(
        api_key=config.BROWSERBASE_API_KEY,
        browser_settings={"context": {"id": context_id, "persist": True}},  # persist: LinkedIn refreshes its cookies as it goes
    )
    stagehand = await Stagehand.create(browser=browser, model=config.STAGEHAND_MODEL, model_api_key=_model_key())
    try:
        page = await stagehand.browser.context.active_page() or await stagehand.browser.context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        if _signed_out(await page.url()):
            log.info("the LinkedIn context is not signed in; reading LinkedIn the ordinary way")
            return ""
        await stagehand.act("If the Experience section has a 'Show all' link or button, open it. If it does not, do nothing.", page=page)
        roles = (await stagehand.extract(
            "Every work experience listed: company, job title, start date, end date (or 'Present'), location, and the "
            "description if one is shown. Only what is on the page.", Experience, page=page)).data.roles
        await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        await stagehand.act("If the Education section has a 'Show all' link or button, open it. If it does not, do nothing.", page=page)
        schools = (await stagehand.extract(
            "Every school listed: school name, degree and field, start and end dates. Only what is on the page.",
            Education, page=page)).data.schools
        return _text(roles, schools)
    finally:
        await stagehand.close()


def read_profile(url: str) -> Optional[links.Page]:
    """A LinkedIn profile as page text, or None (no signed-in context, signed out, or it did not work)."""
    if not enabled():
        return None
    try:
        with links.session_lock:
            text = asyncio.run(_read(config.LINKEDIN_CONTEXT, url))
    except Exception as exc:
        log.warning("Stagehand could not read the LinkedIn profile: %s", exc)
        return None
    return links.Page(url, "substantial", text[: links.MAX_PAGE_CHARS], "", "live") if text else None
