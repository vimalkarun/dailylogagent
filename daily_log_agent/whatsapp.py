import logging
import re
import time
from typing import List

import httpx

log = logging.getLogger("daily_log_agent.whatsapp")

TWILIO_MESSAGES_URL = "https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
TWILIO_MESSAGE_STATUS_URL = "https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages/{message_sid}.json"

# How long to wait before checking whether a send actually got delivered.
# Twilio's POST /Messages response only confirms it queued the message - a
# WhatsApp-side rejection (e.g. error 63016, freeform message outside the
# 24h session window) only shows up if you check back afterwards.
_STATUS_CHECK_DELAY_SECONDS = 4
_FAILURE_STATUSES = {"failed", "undelivered"}

_BOLD_RE = re.compile(r"<b>(.*?)</b>", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def to_whatsapp_text(html_text: str) -> str:
    """Converts the app's Telegram-style <b>...</b> HTML into WhatsApp's *bold* markdown."""
    text = _BOLD_RE.sub(r"*\1*", html_text)
    return _TAG_RE.sub("", text)


def _check_delivery(account_sid: str, auth_token: str, message_sid: str) -> None:
    """Logs the eventual delivery status of a sent message. Never raises - this
    is visibility only, since Twilio's send response can't tell us whether
    WhatsApp actually accepted the message (see error 63016)."""
    time.sleep(_STATUS_CHECK_DELAY_SECONDS)
    try:
        url = TWILIO_MESSAGE_STATUS_URL.format(account_sid=account_sid, message_sid=message_sid)
        resp = httpx.get(url, auth=(account_sid, auth_token), timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        log.warning("Could not check delivery status for WhatsApp message %s", message_sid, exc_info=True)
        return

    status = data.get("status")
    if status in _FAILURE_STATUSES:
        log.warning(
            "WhatsApp message %s to %s FAILED after being accepted: status=%s, error_code=%s, error_message=%s",
            message_sid,
            data.get("to"),
            status,
            data.get("error_code"),
            data.get("error_message"),
        )
    else:
        log.info("WhatsApp message %s to %s status=%s", message_sid, data.get("to"), status)


def _post(account_sid: str, auth_token: str, data: dict) -> None:
    url = TWILIO_MESSAGES_URL.format(account_sid=account_sid)
    resp = httpx.post(url, auth=(account_sid, auth_token), data=data, timeout=30)
    resp.raise_for_status()
    message_sid = resp.json().get("sid")
    if message_sid:
        _check_delivery(account_sid, auth_token, message_sid)


def send_message(account_sid: str, auth_token: str, from_number: str, to_numbers: List[str], text: str) -> None:
    message = to_whatsapp_text(text)
    # WhatsApp message bodies are capped around 1600 characters via Twilio.
    chunks = [message[i : i + 1500] for i in range(0, len(message), 1500)] or [message]
    for to_number in to_numbers:
        for chunk in chunks:
            _post(
                account_sid,
                auth_token,
                {"From": f"whatsapp:{from_number}", "To": f"whatsapp:{to_number}", "Body": chunk},
            )


def send_document(
    account_sid: str, auth_token: str, from_number: str, to_numbers: List[str], pdf_url: str, caption: str = ""
) -> None:
    body = to_whatsapp_text(caption)[:1500] if caption else None
    for to_number in to_numbers:
        data = {"From": f"whatsapp:{from_number}", "To": f"whatsapp:{to_number}", "MediaUrl": pdf_url}
        if body:
            data["Body"] = body
        _post(account_sid, auth_token, data)
