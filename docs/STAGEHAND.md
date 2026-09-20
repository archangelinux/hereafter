# Stagehand in Hereafter

Stagehand is Browserbase's AI browser-automation layer. Where Playwright is told *"click this
selector"*, Stagehand is given an instruction (`act`), a question (`observe`) or a schema (`extract`)
and works the page out itself. Each call is a model call, so it is slower and costs money.

Hereafter uses it for one job: **reading a LinkedIn work history that a logged-out visit cannot see.**
Everything else stays on Playwright ([BROWSERBASE.md](BROWSERBASE.md)), which is faster, free and
predictable on static pages.

## What it does

1. Given a Browserbase *context* that is signed in to LinkedIn, it opens the person's profile in it.
2. If LinkedIn sends the browser to a sign-in page instead, the login has lapsed. Nothing is read this
   way and the ordinary public read runs, which returns a glimpse (title and bio).
3. If it is signed in, Stagehand clicks "Show all" on Experience and Education (`act`) and returns
   every role and school as structured data (`extract`).
4. That comes back as page text, so it goes through the same extraction call, confidence handling,
   encrypted cache and consent gate as any other page. It has no side door into the life log.

Code: [`backend/app/ingest/stagehand_linkedin.py`](../backend/app/ingest/stagehand_linkedin.py)
(the read), [`logins.py`](../backend/app/ingest/logins.py) (the signed-in contexts), hooked in at
`links.load`. It uses OpenAI (`openai/gpt-5.4-mini`, or `HEREAFTER_STAGEHAND_MODEL`) with
`OPENAI_API_KEY`.

```
LinkedIn handle ingested → links.load("linkedin")
   ↓ a signed-in context? (else: the ordinary public read)
Browserbase browser on that context
   ↓ Stagehand: act(open "Show all") → extract(roles, schools)
Page(text) → pipeline._from_pages → LLM extraction → events on main
```

## Getting a signed-in context

Two ways, both in `.env` (see `.env.example`):

- **By hand, once (the reliable one).** `backend/scripts/sign_in_by_hand.py linkedin` opens a Browserbase
  browser and prints a link. Open it, sign in yourself (codes and captchas included), press Enter, and
  put the context id it prints in `HEREAFTER_LINKEDIN_CONTEXT`. The app uses that login as it is.
- **Automatically at startup.** With `LINKEDIN_EMAIL` and `LINKEDIN_PASSWORD` set, the backend signs in
  in the background and keeps the context. The password is typed into LinkedIn's own form and nowhere
  else. This often fails: from a cloud browser LinkedIn and X tend to ask for a code, a captcha or
  "verify it's you", which a script cannot answer. Failures are logged and change nothing.

