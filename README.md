# School Daily Log Agent

Logs into the Entab CampusCare10X parent portal every day, reads today's
Daily Assignment/Log entries, downloads and categorizes each PDF using
Claude, and sends a summary to Telegram.

## How it works

1. `daily_log_agent/portal.py` drives a headless Chromium browser (Playwright)
   to log in at `SCHOOL_BASE_URL`, accepting the Privacy Policy/DPDP checkbox
   automatically, and navigates to `/ParentPortal/ParentAssignment`.
2. It reads the assignment grid, keeping only rows whose Assignment Date is
   today (Asia/Kolkata), then clicks each row's "View" icon and captures the
   resulting PDF from the popup window.
3. `pdf_text.py` extracts text from each PDF; `categorize.py` sends that text
   to Claude (Anthropic API) to classify it (Homework / Exam-Test /
   Practice-Learning / Project / Circular-Notice / Other) and produce a short
   parent-friendly summary.
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

### 2. Anthropic API key
Create a key at [console.anthropic.com](https://console.anthropic.com).

### 3. GitHub repository secrets
In this repo's Settings → Secrets and variables → Actions, add:
- `SCHOOL_USER_ID`
- `SCHOOL_PASSWORD`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `ANTHROPIC_API_KEY`

Optionally add a repository **variable** `SCHOOL_BASE_URL` if your school's
portal URL differs from the default (`https://entab.online/HISSJR`).

### 4. Test before trusting the schedule
Use the **Actions** tab → "Daily School Log Notification" → **Run workflow**
to trigger it manually (optionally with a specific `target_date`) and confirm
you get a Telegram message before relying on the 5 PM cron.

## Local testing

```bash
pip install -r requirements.txt
playwright install chromium
cp .env.example .env   # fill in values
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
- **The "View" click flow is inferred, not directly observed.** The portal's
  `ParentAssignment.js` (which defines the exact click handler) wasn't
  available for inspection, so `capture_pdf_bytes()` tries two strategies:
  a popup opening directly from the eye icon, or an in-page modal with a PDF
  thumbnail that opens the popup on a second click. If neither matches your
  portal's actual behavior, this function is the place to adjust.
- Any unhandled failure (login error, portal change, etc.) sends a
  `⚠️ School Daily Log Agent failed: ...` Telegram message instead of failing
  silently, so a broken run is never invisible.
