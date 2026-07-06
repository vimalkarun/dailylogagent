import httpx


def send_message(bot_token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    # Telegram caps messages at 4096 characters.
    chunks = [text[i : i + 4000] for i in range(0, len(text), 4000)] or [text]
    for chunk in chunks:
        resp = httpx.post(url, json={"chat_id": chat_id, "text": chunk, "parse_mode": "HTML"}, timeout=30)
        resp.raise_for_status()
