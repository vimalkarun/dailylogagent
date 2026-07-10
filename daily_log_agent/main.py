import asyncio
import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from playwright.async_api import async_playwright

from .categorize import (
    categorize_with_anthropic,
    categorize_with_gemini,
    summarize_circular_with_anthropic,
    summarize_circular_with_gemini,
)
from .config import Config, load_config
from . import notify
from .pdf_text import extract_text
from .portal import capture_circular_details, capture_pdf_bytes, get_todays_circulars, get_todays_entries, login

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("daily_log_agent")

IST = ZoneInfo("Asia/Kolkata")


def _build_ai_client(config: Config):
    """Returns (categorize_fn, circular_fn, client, model) for the configured AI provider."""
    if config.ai_provider == "gemini":
        from google import genai

        return (
            categorize_with_gemini,
            summarize_circular_with_gemini,
            genai.Client(api_key=config.gemini_api_key),
            config.gemini_model,
        )

    from anthropic import Anthropic

    return (
        categorize_with_anthropic,
        summarize_circular_with_anthropic,
        Anthropic(api_key=config.anthropic_api_key),
        config.anthropic_model,
    )


def compose_message(target_date: date, results: list[dict]) -> str:
    header = f"<b>School Daily Log - {target_date.strftime('%d %b %Y')}</b>"
    if not results:
        return f"{header}\n\nNo daily log entries were posted for today."

    # Most days have exactly one Daily Log entry covering every subject, so
    # only add a per-entry subheader when there's more than one to tell apart.
    blocks = []
    for r in results:
        if len(results) > 1:
            due = f" (Due: {r['due_date']})" if r["due_date"] else ""
            blocks.append(f"<b>{r['title']}</b>{due}\n{r['summary']}")
        else:
            blocks.append(r["summary"])
    return header + "\n\n" + "\n\n---\n\n".join(blocks)


def compose_circular_message(target_date: date, results: list[dict]) -> str:
    header = f"<b>School Circulars - {target_date.strftime('%d %b %Y')}</b>"
    if not results:
        return f"{header}\n\nNo circulars were posted for today."

    blocks = []
    for r in results:
        due = f" (Due: {r['due_date']})" if r["due_date"] else ""
        blocks.append(f"<b>{r['title']}</b>{due}\n{r['body']}")
    return header + "\n\n" + "\n\n---\n\n".join(blocks)


async def run() -> None:
    config = load_config()
    target_date = (
        datetime.strptime(config.target_date, "%d/%m/%Y").date()
        if config.target_date
        else datetime.now(IST).date()
    )

    results = []
    circular_results = []
    circular_documents = []  # (title, pdf_bytes, pdf_url) to send as documents in "raw" mode
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True)
        try:
            page = await login(context, config.base_url, config.user_id, config.password)
            entries = await get_todays_entries(page, target_date)
            log.info("Found %d daily log entr(y/ies) for %s", len(entries), target_date)

            categorize_fn, circular_fn, ai_client, ai_model = _build_ai_client(config)
            log.info("Using AI provider: %s (model %s)", config.ai_provider, ai_model)
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
                    categorized = categorize_fn(ai_client, ai_model, entry, pdf_text)
                except Exception:
                    log.exception("Failed to process entry %r - sending metadata only", entry["title"])
                    categorized = {
                        "summary": "Could not read this entry's PDF automatically - please check the portal directly.",
                    }
                results.append({**entry, **categorized})

            circulars = await get_todays_circulars(page, target_date)
            log.info("Found %d circular(s) for %s", len(circulars), target_date)

            for circular in circulars:
                pdf_bytes = None
                pdf_url = None
                try:
                    details = await capture_circular_details(context, page, circular["row_index"])
                    description = details["description"]
                    pdf_bytes = details["pdf_bytes"]
                    pdf_url = details["pdf_url"]
                    pdf_text = extract_text(pdf_bytes) if pdf_bytes else ""
                    log.info(
                        "Circular %r: description %d chars, attachment %s bytes, extracted %d chars",
                        circular["title"],
                        len(description),
                        len(pdf_bytes) if pdf_bytes else 0,
                        len(pdf_text),
                    )
                    if config.circular_delivery_mode == "raw":
                        body = description or "(no description text on the portal)"
                    else:
                        categorized = circular_fn(ai_client, ai_model, circular, description, pdf_text)
                        body = categorized["summary"]
                except Exception:
                    log.exception("Failed to process circular %r - sending metadata only", circular["title"])
                    body = "Could not read this circular automatically - please check the portal directly."
                circular_results.append({**circular, "body": body})
                if config.circular_delivery_mode == "raw" and pdf_bytes:
                    circular_documents.append((circular["title"], pdf_bytes, pdf_url))
        finally:
            await browser.close()

    message = compose_message(target_date, results)
    notify.send_text(config, message)
    log.info("Sent %s notification with %d entries", config.notification_channel, len(results))

    circular_message = compose_circular_message(target_date, circular_results)
    notify.send_text(config, circular_message)
    log.info("Sent %s circular notification with %d entries", config.notification_channel, len(circular_results))

    for title, pdf_bytes, pdf_url in circular_documents:
        filename = f"{(title.strip() or 'circular')[:60]}.pdf"
        notify.send_document(config, filename, pdf_bytes, pdf_url, caption=f"<b>{title}</b>")
    if circular_documents:
        log.info("Sent %d circular PDF attachment(s)", len(circular_documents))


def main() -> None:
    try:
        asyncio.run(run())
    except Exception as exc:
        log.exception("Daily log agent failed")
        try:
            config = load_config()
            notify.send_text(config, f"⚠️ School Daily Log Agent failed: {exc}")
        except Exception:
            log.exception("Additionally failed to send failure alert")
        raise


if __name__ == "__main__":
    main()
