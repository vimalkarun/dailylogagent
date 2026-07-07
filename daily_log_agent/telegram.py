import httpx


def send_message(bot_token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    # Telegram caps messages at 4096 characters.
    chunks = [text[i : i + 4000] for i in range(0, len(text), 4000)] or [text]
    for chunk in chunks:
        resp = httpx.post(url, json={"chat_id": chat_id, "text": chunk, "parse_mode": "HTML"}, timeout=30)
        resp.raise_for_status()


def send_document(bot_token: str, chat_id: str, filename: str, pdf_bytes: bytes, caption: str = "") -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    # Telegram caption cap is 1024 characters, well under sendMessage's 4096.
    resp = httpx.post(
        url,
        data={"chat_id": chat_id, "caption": caption[:1024], "parse_mode": "HTML"},
        files={"document": (filename, pdf_bytes, "application/pdf")},
        timeout=60,
    )
    resp.raise_for_status()
