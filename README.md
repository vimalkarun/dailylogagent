# School Daily Log Agent

Logs into the Entab CampusCare10X parent portal every day, reads today's
Daily Assignment/Log entries, downloads and categorizes each PDF using
Claude or Gemini, and sends a summary to Telegram.

## How it works

1. `daily_log_agent/portal.py` drives a headless Chromium browser (Playwright)
   to log in at `SCHOOL_BASE_URL`, accepting the Privacy Policy/DPDP checkbox
   automatically, and navigates to `/ParentPortal/ParentAssignment`.
2. It reads the assignment grid, keeping only rows whose Assignment Date is
   today (Asia/Kolkata), then clicks each row's "View" icon and captures the
   resulting PDF from the popup window.
3. `pdf_text.py` extracts text from each PDF; `categorize.py` sends that text
   to an AI provider (Claude via Anthropic, or Gemini via Google - selected by
   the `AI_PROVIDER` setting) to produce a per-subject summary with bolded
   Homework and Exam/Test Intimation sections.
4. `telegram.py` sends the compiled summary to a Telegram chat.
5. `.github/workflows/daily-log.yml` runs this on a schedule (17:00 IST daily)
   via GitHub Actions.

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

### 4. Test before trusting the schedule
Use the **Actions** tab → "Daily School Log Notification" → **Run workflow**
to trigger it manually and confirm you get a Telegram message before relying
on the 5 PM cron.

If there's no log entry for today (e.g. while testing on a weekend), you can
point the run at a different date, in `DD/MM/YYYY` format — matching the date
as it's shown in the portal's own table:
- Type a date directly into the **target_date** box in the "Run workflow" form, or
- Set a repository **variable** (Settings → Secrets and variables → Actions →
  Variables tab, not Secrets — a date isn't sensitive) named `TARGET_DATE` so
  you don't have to retype it every time you re-run the workflow manually.

Either way only affects manual runs. The scheduled 5 PM run always ignores
both and processes "today", so a leftover test date can't silently break the
daily notification.

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
- Any unhandled failure (login error, portal change, etc.) sends a
  `⚠️ School Daily Log Agent failed: ...` Telegram message instead of failing
  silently, so a broken run is never invisible.
