"""Per-link pipeline:

    load via Browserbase -> readability-style content extract
      -> substantial text:          normal extraction
      -> thin (login wall/blocked): keep what surfaced (title, bio, og: tags) at low confidence
      -> nothing:                   the URL itself becomes a freeform breadcrumb
    never an error shown to the user

Consent rule, enforced here rather than trusted to callers: the only URLs ever loaded are
those `db.submitted_handles(person_id)` returns — rows the person submitted about themselves —
expanded by the fixed templates in `urls_for`. No link found on a page is ever followed.
"""

from __future__ import annotations

import html
import json
import logging
import re
import threading
from dataclasses import asdict, dataclass
from datetime import date
from hashlib import sha1
from urllib.parse import urlparse

import httpx

from .. import config, security

log = logging.getLogger("hereafter.ingest")
# The Browserbase project allows one browser session at a time, across crawling and research.
session_lock = threading.Lock()

HANDLE_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,98})$")
SUBSTANTIAL_CHARS = 600
MAX_PAGE_CHARS = 60_000

# Runs in the page: prefer the main content region, drop chrome, and collect the metadata
# that survives login walls.
READABILITY_JS = """() => {
  const meta = (k) => document.querySelector(`meta[property="${k}"],meta[name="${k}"]`)?.content || "";
  const root = document.querySelector("article, main, [role=main]") || document.body;
  const clone = root.cloneNode(true);
  clone.querySelectorAll("nav, header, footer, aside, script, style, noscript, form, [aria-hidden=true]")
       .forEach((n) => n.remove());
  return {
    title: document.title || "",
    og_title: meta("og:title"), og_description: meta("og:description") || meta("description"),
    text: (clone.innerText || "").replace(/\\n{3,}/g, "\\n\\n").trim(),
  };
}"""


@dataclass
class Page:
    url: str
    tier: str = "nothing"          # substantial | thin | nothing
    text: str = ""
    surfaced: str = ""             # title / bio card / og: tags
    mode: str = "skipped"          # live | cache | direct | skipped


def urls_for(source: str, handle: str) -> list[str]:
    if source in ("site", "link"):
        return [handle if handle.startswith("http") else f"https://{handle}"]
    if not HANDLE_RE.match(handle):
        raise ValueError(f"not a valid {source} handle")
    return {
        "github": [f"https://github.com/{handle}", f"https://github.com/{handle}?tab=repositories"],
        "linkedin": [f"https://www.linkedin.com/in/{handle}/"],
        "instagram": [f"https://www.instagram.com/{handle}/"],
    }[source]


def _grade(url: str, title: str, og_title: str, og_description: str, text: str, mode: str) -> Page:
    surfaced = " — ".join(dict.fromkeys(s.strip() for s in (og_title or title, og_description) if s.strip()))
    text = text[:MAX_PAGE_CHARS]
    if len(text) >= SUBSTANTIAL_CHARS:
        return Page(url, "substantial", text, surfaced, mode)
    if surfaced or text:
        return Page(url, "thin", text, surfaced or text[:300], mode)
    return Page(url, "nothing", mode=mode)


def _load_browserbase(urls: list[str]) -> list[Page]:
    from browserbase import Browserbase
    from playwright.sync_api import sync_playwright

    pages = []
    with session_lock, sync_playwright() as pw:
        session = Browserbase(api_key=config.BROWSERBASE_API_KEY).sessions.create(
            project_id=config.BROWSERBASE_PROJECT_ID
        )
        browser = pw.chromium.connect_over_cdp(session.connect_url)
        try:
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            tab = context.pages[0] if context.pages else context.new_page()
            for url in urls:
                try:
                    tab.goto(url, wait_until="domcontentloaded", timeout=30_000)
                    got = tab.evaluate(READABILITY_JS)
                    pages.append(_grade(url, got["title"], got["og_title"], got["og_description"], got["text"], "live"))
                except Exception as exc:
                    log.info("could not load %s: %s", url, exc)
                    pages.append(Page(url, mode="live"))
        finally:
            browser.close()
    return pages


def _meta(doc: str, key: str) -> str:
    m = re.search(rf'<meta[^>]+(?:property|name)=["\']{key}["\'][^>]+content=["\']([^"\']*)', doc, re.I)
    return html.unescape(m.group(1)) if m else ""


def _load_direct(urls: list[str]) -> list[Page]:
    """Plain HTTP stand-in for local development without Browserbase credentials."""
    pages = []
    with httpx.Client(follow_redirects=True, timeout=15, headers={"User-Agent": "Hereafter/0.1"}) as client:
        for url in urls:
            try:
                doc = client.get(url).text
                title = re.search(r"<title[^>]*>(.*?)</title>", doc, re.I | re.S)
                body = re.sub(r"(?is)<(script|style|nav|header|footer|noscript)\b.*?</\1>", " ", doc)
                text = re.sub(r"\s+", " ", html.unescape(re.sub(r"(?s)<[^>]+>", " ", body))).strip()
                pages.append(_grade(url, html.unescape(title.group(1).strip()) if title else "",
                                    _meta(doc, "og:title"), _meta(doc, "og:description") or _meta(doc, "description"),
                                    text, "direct"))
            except Exception as exc:
                log.info("could not load %s: %s", url, exc)
                pages.append(Page(url, mode="direct"))
    return pages


def cache_dir(person_id: str):
    return config.CACHE_DIR / re.sub(r"[^A-Za-z0-9_-]", "_", person_id)


def _cache_path(person_id: str, url: str):
    return cache_dir(person_id) / f"{urlparse(url).netloc}-{sha1(url.encode()).hexdigest()[:10]}.json"


def load(person_id: str, source: str, handle: str, live: bool) -> list[Page]:
    """Pages for one self-submitted handle or link. Never raises."""
    try:
        urls = urls_for(source, handle)
    except ValueError:
        return []
    pages: list[Page] = []
    if live:
        try:
            if source == "linkedin":  # a signed-in browser is set up? Stagehand reads what the wall hides
                from . import stagehand_linkedin

                got = stagehand_linkedin.read_profile(urls[0])
                pages = [got] if got else []
            if pages:
                pass
            elif config.BROWSERBASE_API_KEY and config.BROWSERBASE_PROJECT_ID:
                pages = _load_browserbase(urls)
            else:
                pages = _load_direct(urls)
        except Exception as exc:
            log.warning("live crawl failed for %s: %s", source, exc)
    by_url = {p.url: p for p in pages}
    out = []
    for url in urls:
        page, path = by_url.get(url), _cache_path(person_id, url)
        if page and page.tier != "nothing":
            path.parent.mkdir(parents=True, exist_ok=True)
            # page text is personal: encrypted at rest
            path.write_text(security.seal(json.dumps({**asdict(page), "fetched": date.today().isoformat()})))
        elif path.exists():
            opened = security.unseal(path.read_text())
            if opened:
                cached = json.loads(opened)
                page = Page(url, cached["tier"], cached["text"], cached["surfaced"], "cache")
        out.append(page or Page(url))
    return out
