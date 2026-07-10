import re

import httpx

TWILIO_MESSAGES_URL = "https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"

_BOLD_RE = re.compile(r"<b>(.*?)</b>", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def to_whatsapp_text(html_text: str) -> str:
    """Converts the app's Telegram-style <b>...</b> HTML into WhatsApp's *bold* markdown."""
    text = _BOLD_RE.sub(r"*\1*", html_text)
    return _TAG_RE.sub("", text)


def send_message(account_sid: str, auth_token: str, from_number: str, to_number: str, text: str) -> None:
    url = TWILIO_MESSAGES_URL.format(account_sid=account_sid)
    message = to_whatsapp_text(text)
    # WhatsApp message bodies are capped around 1600 characters via Twilio.
    chunks = [message[i : i + 1500] for i in range(0, len(message), 1500)] or [message]
    for chunk in chunks:
        resp = httpx.post(
            url,
            auth=(account_sid, auth_token),
            data={"From": f"whatsapp:{from_number}", "To": f"whatsapp:{to_number}", "Body": chunk},
            timeout=30,
        )
        resp.raise_for_status()


def send_document(
    account_sid: str, auth_token: str, from_number: str, to_number: str, pdf_url: str, caption: str = ""
) -> None:
    url = TWILIO_MESSAGES_URL.format(account_sid=account_sid)
    data = {"From": f"whatsapp:{from_number}", "To": f"whatsapp:{to_number}", "MediaUrl": pdf_url}
    if caption:
        data["Body"] = to_whatsapp_text(caption)[:1500]
    resp = httpx.post(url, auth=(account_sid, auth_token), data=data, timeout=30)
    resp.raise_for_status()
