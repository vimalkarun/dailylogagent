from typing import Optional

from . import telegram, whatsapp
from .config import Config


def send_text(config: Config, text: str) -> None:
    if config.notification_channel == "whatsapp":
        whatsapp.send_message(
            config.twilio_account_sid,
            config.twilio_auth_token,
            config.twilio_whatsapp_from,
            config.whatsapp_to_number,
            text,
        )
    else:
        telegram.send_message(config.telegram_bot_token, config.telegram_chat_id, text)


def send_document(
    config: Config, filename: str, pdf_bytes: bytes, pdf_url: Optional[str], caption: str = ""
) -> None:
    if config.notification_channel == "whatsapp":
        whatsapp.send_document(
            config.twilio_account_sid,
            config.twilio_auth_token,
            config.twilio_whatsapp_from,
            config.whatsapp_to_number,
            pdf_url,
            caption,
        )
    else:
        telegram.send_document(config.telegram_bot_token, config.telegram_chat_id, filename, pdf_bytes, caption)
