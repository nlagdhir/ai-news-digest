# AI Daily News Digest (Gujarati) 🤖

A fully automated, **₹0-cost** daily AI news briefing, emailed to you every
morning in natural Gujarati — no server, no VPS, no paid services. It runs
entirely on **GitHub Actions**.

---

## 1. What this project does

Every morning at ~8:00 AM IST, a GitHub Actions workflow:

1. Reads ~25 configured RSS feeds (official AI company blogs, tech news
   sites, and Google News topic searches).
2. Keeps only articles published in the last 24 hours.
3. Locally (no AI, no cost) groups articles that report the same event into
   single "stories" and picks the most authoritative source for each.
4. Sends the surviving candidate stories to **Google Gemini** (`gemini-2.5-flash`)
   in one or two batched requests, asking it to pick the 8–10 genuinely
   important stories, categorize them, and write short Gujarati summaries.
5. Renders a mobile-friendly HTML email and sends it via Gmail SMTP.

If anything fails along the way (a dead RSS feed, a Gemini outage, etc.) the
run degrades gracefully instead of crashing — see [Error Handling](#error-handling--fallback-behavior).

## 2. Architecture

```
config/feeds.yaml (RSS + Google News feeds, source priority)
        │
        ▼
 rss_reader.py   ──►  fetch feeds, keep last 24h          (no AI)
        │
        ▼
 deduplicator.py ──►  cluster duplicate stories            (no AI)
        │
        ▼
 news_ranker.py  ──►  trim to MAX_ARTICLES_TO_PROCESS      (no AI)
        │
        ▼
 gemini_provider.py ──► AIProvider.select_and_summarize()  (1-2 Gemini calls)
        │                 rank → select top 8-10 → categorize → Gujarati summary
        ▼
 email_sender.py ──►  render templates/email.html, send via Gmail SMTP
        │
        ▼
      Your inbox
```

Everything runs once, top-to-bottom, inside a single GitHub Actions job.
There is no continuously running server or background process.

The AI step is behind a small abstraction (`AIProvider` in `src/ai_provider.py`)
so a different model/vendor can be added later as a new file without
touching the rest of the pipeline.

## 3. Requirements

- A **GitHub account** (free) — to host the repository and run the workflow.
- A **Google account** — for the free Gemini API key.
- A **Gmail account** — to send the email (can be the same or a different
  Google account).
- For local development only: **Python 3.10+** installed on your machine.

## 4. Google Gemini API

1. Go to **[Google AI Studio](https://aistudio.google.com/apikey)** and sign in.
2. Click **Create API key** and copy it.
3. This project uses the **`gemini-2.5-flash`** model by default (configurable
   via the `GEMINI_MODEL` environment variable) because it has a generous
   free tier and is fast/cheap enough for this use case.
4. You will add this key as the `GEMINI_API_KEY` GitHub Secret (see [Section 6](#6-github)).

Gemini's free tier has request-per-minute and request-per-day limits that
change over time — check your current limits at
[ai.google.dev/pricing](https://ai.google.dev/pricing). This project is
designed to use only **1–2 requests per day**, so it comfortably fits even a
conservative free tier. See [Cost Protection](#cost-protection) below for
the safeguards in place.

## 5. Gmail (sending the email)

Gmail requires an **App Password** to send mail from a script — your normal
Gmail password will NOT work if 2-Step Verification is enabled (and Google
requires 2-Step Verification to be enabled to even create an App Password).

1. Go to your [Google Account → Security](https://myaccount.google.com/security).
2. Turn on **2-Step Verification** if it isn't already on.
3. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).
4. Create a new app password (name it e.g. "AI News Digest") and copy the
   16-character password shown.
5. This becomes your `EMAIL_PASSWORD` secret. Your normal Gmail address is
   `EMAIL_ADDRESS`. The address that should receive the digest is
   `RECIPIENT_EMAIL` (can be the same address, or a different one).

## 6. GitHub

### Push the code

```bash
git init
git add .
git commit -m "Initial commit: AI daily news digest"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```

### Add GitHub Secrets

Go to your repository → **Settings → Secrets and variables → Actions →
New repository secret**, and add each of these:

| Secret name         | Value                                                        |
|----------------------|--------------------------------------------------------------|
| `GEMINI_API_KEY`     | Your Gemini API key from Section 4                            |
| `EMAIL_ADDRESS`      | The Gmail address the email will be sent **from**             |
| `EMAIL_PASSWORD`     | The 16-character Gmail App Password from Section 5            |
| `RECIPIENT_EMAIL`    | The email address that should **receive** the daily digest    |
| `TIMEZONE` (optional)| Defaults to `Asia/Kolkata` if not set                          |

### Enable Actions and run it manually

1. Go to the **Actions** tab of your repository.
2. If prompted, click **"I understand my workflows, go ahead and enable them"**.
3. Click **Daily AI News Digest** in the left sidebar.
4. Click **Run workflow**, choose mode `send-test` (sends one real email so
   you can verify everything end-to-end), and click **Run workflow**.
5. Check your inbox. If something went wrong, open the failed run and read
   the log output, or download the `run-logs` artifact attached to the run.

## 7. Daily schedule

The workflow runs automatically every day at **~8:00 AM IST**
(`Asia/Kolkata`), via the cron schedule `30 2 * * *` (2:30 AM UTC) in
[.github/workflows/daily_ai_news.yml](.github/workflows/daily_ai_news.yml).
GitHub's scheduler can run a few minutes late during high load, which is
normal.

## 8. Local testing

Clone the repo locally, then:

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

pip install -r requirements.txt
cp .env.example .env          # then fill in your real values
```

**Dry run (no email sent, writes `preview.html`):**

```bash
python src/main.py --test
```

Open `preview.html` in your browser to see exactly what the email will look
like.

**Send one real test email:**

```bash
python src/main.py --send-test
```

**Run the automated tests** (no network calls, no real API calls):

```bash
pytest tests/
```

## 9. Adding or removing an RSS feed

Open [config/feeds.yaml](config/feeds.yaml) and add an entry to the `feeds:`
list — no code changes needed:

```yaml
  - name: "Some New AI Blog"
    url: "https://example.com/feed.xml"
    type: ai_pub                 # official | wire | tech_pub | ai_pub | google_news
    category_hint: "New AI Models"
```

To remove a feed, delete its entry. To make a source count as more
authoritative when the same story appears in multiple places, add its
domain to the `source_priority:` table at the bottom of the same file
(lower number = higher priority).

## 10. Changing the language

The pipeline is written so the output language is a single setting
(`LANGUAGE` environment variable, currently only `gu` is implemented). The
prompt and field names in `src/summarizer.py` are the only place language-specific
instructions live — adding Hindi (`hi`) or English (`en`) later means adding
an alternate system-instruction template there and switching on
`settings.language`, without changing any other file.

## 11. Troubleshooting

**An RSS feed is unavailable / failing**
This is expected occasionally — the app logs a warning (`Feed failed: ...`)
and continues with the remaining feeds. If a feed fails consistently for
weeks, remove or replace it in `config/feeds.yaml`.

**Gemini API error**
The app retries a failed call up to 2 times with backoff, then falls back to
a headline-only digest (clearly labeled) rather than sending nothing. Check
the run logs for the specific error (e.g. invalid key, quota exceeded).

**Gmail authentication failure**
Almost always means: (a) you used your normal Gmail password instead of an
App Password, or (b) 2-Step Verification isn't enabled on the account. Redo
the steps in [Section 5](#5-gmail-sending-the-email).

**GitHub Actions run failed**
Open the failed run in the **Actions** tab and expand the "Run AI news
digest" step. Download the `run-logs` artifact for the full log file. Common
causes: a missing/misspelled secret name, or all feeds failing at once
(check your network/feed URLs).

**Empty news result ("nothing to send today")**
If every configured feed had no articles in the last 24 hours (rare) or the
AI genuinely found no important stories, the app logs this and exits
successfully without sending an email — this is expected behavior per the
"never pad with low-quality news" requirement, not a bug.

---

## Cost Protection

All numeric limits live in `.env` (locally) / GitHub Secrets & workflow env
(in CI) — never hard-coded:

| Variable                   | Default | Purpose                                            |
|-----------------------------|---------|-----------------------------------------------------|
| `LOOKBACK_HOURS`             | `24`    | Only consider articles published in this window     |
| `MAX_ARTICLES_TO_PROCESS`    | `40`    | Cap on candidate stories sent to the AI step         |
| `MAX_STORIES`                | `10`    | Maximum stories in the final email                   |
| `MAX_AI_REQUESTS`            | `5`     | Hard cap on actual Gemini API calls per run          |

The pipeline **never calls Gemini once per article** — local, free,
pure-Python deduplication and ranking happen first, and the survivors are
sent as a single batch (occasionally two, for very large candidate sets).
A typical run makes **1–2 Gemini calls total**. If the request budget would
be exceeded, the run stops calling the API and falls back to a local,
headline-only digest instead of retrying indefinitely.

## Error Handling / Fallback Behavior

- One feed failing (timeout, 404, malformed XML) never stops the run —
  it's logged and skipped.
- One unparseable article is skipped, not the whole feed.
- A Gemini failure retries a limited number of times, then falls back to a
  headline-only English digest so an email still goes out.
- A Gmail send failure is logged clearly and the workflow fails (visible in
  the Actions tab) rather than silently losing the run.

## Project Structure

```
.github/workflows/daily_ai_news.yml   GitHub Actions workflow (schedule + manual)
config/feeds.yaml                     RSS feeds + source-priority table
src/
  main.py            orchestrator / CLI entry point
  models.py           shared dataclasses (Article, StoryCluster, DigestResult)
  config.py            loads .env + feeds.yaml into a Settings object
  rss_reader.py        feed fetching + 24h window filter
  deduplicator.py       local dedup (canonical URL + title similarity)
  news_ranker.py         pre-AI trim to MAX_ARTICLES_TO_PROCESS
  ai_provider.py           abstract AIProvider interface
  gemini_provider.py        Gemini implementation (batching, retries, fallback)
  summarizer.py               prompt building + response parsing
  email_sender.py               Jinja2 render + Gmail SMTP send
  utils.py                        URL/title normalization, date/tz helpers
templates/email.html    HTML email template (inline CSS, mobile responsive)
tests/                   pytest suite (no network, no real API calls)
requirements.txt
.env.example
```

## What's free, and what to watch

- **GitHub Actions**: free for public repos; private repos get 2,000 free
  minutes/month — this workflow takes well under a minute per run.
- **Gemini API free tier**: generous request-per-day/minute limits for
  `gemini-2.5-flash` (check current limits at ai.google.dev/pricing) — this
  project uses 1–2 requests/day by design.
- **Gmail SMTP**: free, with Gmail's standard sending limits (500 emails/day
  for regular accounts) — this project sends 1 email/day.

## Next Improvements (optional, after the MVP works)

Not implemented yet, but the architecture is compatible with:
Hindi/English language output, Telegram/WhatsApp delivery, a weekly digest,
keyword filtering, an "AI tools only" or "India only" mode, user-selected
feeds, a web dashboard, news history, and multiple recipients.
