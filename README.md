# School Daily Log Agent

Logs into the Entab CampusCare10X parent portal every day, reads today's
Daily Assignment/Log entries and Circulars, downloads and categorizes each
PDF using Claude or Gemini, and sends the results to Telegram as two separate
messages.

## How it works

1. `daily_log_agent/portal.py` drives a headless Chromium browser (Playwright)
   to log in at `SCHOOL_BASE_URL`, accepting the Privacy Policy/DPDP checkbox
   automatically.
2. **Daily Log**: it navigates to `/ParentPortal/ParentAssignment`, reads the
   assignment grid, keeping only rows whose Assignment Date is today
   (Asia/Kolkata), then clicks each row's "View" icon and captures the
   resulting PDF.
3. **Circulars**: it navigates to `/ParentPortal/ParentCircular`, waits
   (patiently - this grid can take a while to populate) for rows whose
   Circular Date is today, then clicks each row's eye icon to read the
   circular's description text and, if present, its PDF attachment.
4. `pdf_text.py` extracts text from each PDF; `categorize.py` sends that text
   to an AI provider (Claude via Anthropic, or Gemini via Google - selected by
   the `AI_PROVIDER` setting) to produce a per-subject Daily Log summary with
   bolded Homework and Exam/Test Intimation sections, and a short Circular
   summary that calls out any action required from the parent in bold.
5. `telegram.py` sends the Daily Log summary and the Circulars summary as two
   separate Telegram messages. When `CIRCULAR_DELIVERY_MODE=raw`, circulars
   skip AI summarization (their portal text is sent as-is) and any PDF
   attachment is sent as a Telegram document instead of being summarized.
6. `.github/workflows/daily-log.yml` runs this via GitHub Actions, triggered
   daily at 17:00 IST by an **external** cron service calling the
   `workflow_dispatch` API (see setup step 5 below) - not GitHub's own
   `schedule:` trigger, which is "best effort" and can be delayed
   unpredictably by tens of minutes or more.

## One-time setup

### 1. Telegram bot
1. Message [@BotFather](https://t.me/BotFather) on Telegram, run `/newbot`,
   and copy the bot token it gives you.
2. Send any message to your new bot (or add it to a group).
3. Visit `https://api.telegram.org/bot<token>/getUpdates` in a browser and
   find `"chat":{"id": ...}` — that number is your `TELEGRAM_CHAT_ID`.

### 2. AI provider API key
Pick one (both can be configured; only the selected one needs a real key):
- **Anthropic (default)**: create a key at [console.anthropic.com](https://console.anthropic.com).
- **Gemini**: create a key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey).

### 3. GitHub repository secrets and variables
In this repo's Settings → Secrets and variables → Actions:

**Secrets** (Secrets tab):
- `SCHOOL_USER_ID`
- `SCHOOL_PASSWORD`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `ANTHROPIC_API_KEY` (if using Anthropic)
- `GEMINI_API_KEY` (if using Gemini)

**Variables** (Variables tab — not secrets, since none of these are sensitive):
- `SCHOOL_BASE_URL` — optional, only if your school's portal URL differs from
  the default (`https://entab.online/HISSJR`)
- `AI_PROVIDER` — optional, `anthropic` (default) or `gemini`; this is the
  switch that picks which AI provider categorizes the log
- `ANTHROPIC_MODEL` / `GEMINI_MODEL` — optional, override the default model
  for whichever provider you're using
- `CIRCULAR_DELIVERY_MODE` — optional, `summary` (default, AI-summarized) or
  `raw` (the circular's own text as-is, plus its PDF sent as a Telegram
  document if it has one)

### 4. Test manually before setting up the daily trigger
Use the **Actions** tab → "Daily School Log Notification" → **Run workflow**
and confirm you get a Telegram message.

If there's no log entry for today (e.g. while testing on a weekend), tick
**test_run** in the "Run workflow" form and point it at a different date, in
`DD/MM/YYYY` format — matching the date as it's shown in the portal's own
table:
- Type a date directly into the **target_date** box, or
- Set a repository **variable** (Settings → Secrets and variables → Actions →
  Variables tab, not Secrets — a date isn't sensitive) named `TARGET_DATE` so
  you don't have to retype it every time.

If **test_run** is left unticked (the default), the run always processes
"today" and ignores both `target_date` and `TARGET_DATE` — this is what
protects the real daily trigger from accidentally picking up a leftover test
date.

### 5. Set up the daily 5 PM trigger (external cron)
GitHub's own `schedule:` trigger is unreliable for this (can be delayed by
tens of minutes or more), so an external cron service calls the
`workflow_dispatch` REST API directly instead, at exactly 17:00 IST.

1. **Create a GitHub Personal Access Token** scoped to just this repo:
   - Go to [github.com/settings/personal-access-tokens](https://github.com/settings/personal-access-tokens/new)
   - Resource owner: your account. Repository access: **Only select repositories** → this repo.
   - Permissions → Repository permissions → **Actions: Read and write**.
   - Generate and copy the token. Treat it like a password — it will only be
     entered into the cron service below, never committed to this repo.

2. **Register a scheduled HTTP request** with a cron service that supports
   custom headers and timezones (e.g. [cron-job.org](https://cron-job.org), free):
   - **URL**: `https://api.github.com/repos/vimalkarun/dailylogagent/actions/workflows/daily-log.yml/dispatches`
   - **Method**: `POST`
   - **Headers**:
     ```
     Authorization: Bearer <your PAT>
     Accept: application/vnd.github+json
     X-GitHub-Api-Version: 2022-11-28
     Content-Type: application/json
     ```
   - **Body**: `{"ref": "main"}`
   - **Schedule**: daily at `17:00`, timezone `Asia/Kolkata`

   A successful call returns HTTP 204 with no body. The workflow run then
   appears in the Actions tab exactly as if you'd clicked "Run workflow"
   yourself, with `test_run` defaulting to false — so it always processes
   today's log.

3. Confirm the next day that a run actually fired at 17:00 IST in the
   Actions tab before fully trusting it.

## Local testing

```bash
pip install -r requirements.txt
playwright install chromium
cp .env.example .env   # fill in values (TARGET_DATE is optional, format DD/MM/YYYY)
set -a && source .env && set +a
python -m daily_log_agent.main
```

## Known limitations

- **No MFA/OTP support.** If "Login OTP Required" is enabled for this account
  (portal setting under Change Password), unattended login will fail with a
  clear error sent to Telegram. Turn that setting off for this account, or
  extend `portal.login()` to handle it.
- **Selectors are calibrated against one snapshot of the portal's HTML**
  (login page + `/ParentPortal/ParentAssignment`, July 2026). Entab may change
  markup; if the agent starts failing, re-check `daily_log_agent/portal.py`
  against the current page source.
- **The "View" click flow is confirmed against a live run, but tied to this
  portal's current JS.** Clicking the eye icon opens the in-page
  `.assignment-details` modal (never a popup); clicking the PDF thumbnail
  inside it triggers an AJAX call whose JSON response contains the real
  signed S3 URL in a `classDetails` field (despite the endpoint being named
  `...Base64`). If Entab changes this client-side flow, `capture_pdf_bytes()`
  in `daily_log_agent/portal.py` is the place to adjust - the function is
  built to intercept that network response rather than any popup.
- **The Circular PDF-capture flow (`capture_circular_details()`) mirrors the
  Daily Log flow by analogy** (same `classDetails`-in-a-`...Base64...`-named
  response pattern) but hasn't been confirmed against a live circular that
  actually has a PDF attached. If circular PDFs stop being picked up, check
  the network requests fired when clicking a circular's thumbnail in
  `#caresoul` and adjust the response matcher in that function. A circular
  with no attachment at all is expected and handled normally (its
  description text is still sent).
- Any unhandled failure (login error, portal change, etc.) sends a
  `⚠️ School Daily Log Agent failed: ...` Telegram message instead of failing
  silently, so a broken run is never invisible.
