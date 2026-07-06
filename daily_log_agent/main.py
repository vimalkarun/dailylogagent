import asyncio
import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from anthropic import Anthropic
from playwright.async_api import async_playwright

from .categorize import categorize_entry
from .config import load_config
from .pdf_text import extract_text
from .portal import capture_pdf_bytes, get_todays_entries, login
from .telegram import send_message

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("daily_log_agent")

IST = ZoneInfo("Asia/Kolkata")


def compose_message(target_date: date, results: list[dict]) -> str:
    header = f"<b>School Daily Log - {target_date.strftime('%d %b %Y')}</b>"
    if not results:
        return f"{header}\n\nNo daily log entries were posted for today."

    lines = [header, ""]
    for r in results:
        lines.append(f"<b>[{r['category']}]</b> {r['subject']} - {r['title']}")
        lines.append(f"Due: {r['due_date']}")
        lines.append(r["summary"])
        lines.append("")
    return "\n".join(lines).strip()


async def run() -> None:
    config = load_config()
    target_date = (
        datetime.strptime(config.target_date, "%d/%m/%Y").date()
        if config.target_date
        else datetime.now(IST).date()
    )

    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True)
        try:
            page = await login(context, config.base_url, config.user_id, config.password)
            entries = await get_todays_entries(page, target_date)
            log.info("Found %d daily log entr(y/ies) for %s", len(entries), target_date)

            client = Anthropic(api_key=config.anthropic_api_key)
            for entry in entries:
                try:
                    pdf_bytes = await capture_pdf_bytes(context, page, entry["row_index"])
                    pdf_text = extract_text(pdf_bytes) if pdf_bytes else ""
                    log.info(
                        "Entry %r: downloaded %s bytes, extracted %d chars of text. Preview: %r",
                        entry["title"],
                        len(pdf_bytes) if pdf_bytes else 0,
                        len(pdf_text),
                        pdf_text[:300],
                    )
                    categorized = categorize_entry(client, config.anthropic_model, entry, pdf_text)
                except Exception:
                    log.exception("Failed to process entry %r - sending metadata only", entry["title"])
                    categorized = {
                        "category": "Other",
                        "summary": "Could not read this entry's PDF automatically - please check the portal directly.",
                    }
                results.append({**entry, **categorized})
        finally:
            await browser.close()

    message = compose_message(target_date, results)
    send_message(config.telegram_bot_token, config.telegram_chat_id, message)
    log.info("Sent Telegram notification with %d entries", len(results))


def main() -> None:
    try:
        asyncio.run(run())
    except Exception as exc:
        log.exception("Daily log agent failed")
        try:
            config = load_config()
            send_message(
                config.telegram_bot_token,
                config.telegram_chat_id,
                f"⚠️ School Daily Log Agent failed: {exc}",
            )
        except Exception:
            log.exception("Additionally failed to send failure alert to Telegram")
        raise


if __name__ == "__main__":
    main()
