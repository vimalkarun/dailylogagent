import os
from dataclasses import dataclass
from typing import Optional

VALID_PROVIDERS = ("anthropic", "gemini")
VALID_CIRCULAR_DELIVERY_MODES = ("summary", "raw")
VALID_NOTIFICATION_CHANNELS = ("telegram", "whatsapp")

# Twilio's public, shared WhatsApp Sandbox number - the default "from" until
# a real Twilio WhatsApp Sender is configured.
DEFAULT_TWILIO_WHATSAPP_FROM = "+14155238886"


@dataclass
class Config:
    base_url: str
    user_id: str
    password: str
    notification_channel: str
    telegram_bot_token: Optional[str]
    telegram_chat_id: Optional[str]
    twilio_account_sid: Optional[str]
    twilio_auth_token: Optional[str]
    twilio_whatsapp_from: str
    whatsapp_to_numbers: list[str]
    ai_provider: str
    anthropic_api_key: Optional[str]
    anthropic_model: str
    gemini_api_key: Optional[str]
    gemini_model: str
    target_date: Optional[str]
    circular_delivery_mode: str


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _parse_number_list(raw: str) -> list[str]:
    return [n.strip() for n in raw.split(",") if n.strip()]


def load_config() -> Config:
    ai_provider = (os.environ.get("AI_PROVIDER") or "anthropic").strip().lower()
    if ai_provider not in VALID_PROVIDERS:
        raise RuntimeError(f"AI_PROVIDER must be one of {VALID_PROVIDERS}, got {ai_provider!r}")

    circular_delivery_mode = (os.environ.get("CIRCULAR_DELIVERY_MODE") or "summary").strip().lower()
    if circular_delivery_mode not in VALID_CIRCULAR_DELIVERY_MODES:
        raise RuntimeError(
            f"CIRCULAR_DELIVERY_MODE must be one of {VALID_CIRCULAR_DELIVERY_MODES}, got {circular_delivery_mode!r}"
        )

    notification_channel = (os.environ.get("NOTIFICATION_CHANNEL") or "telegram").strip().lower()
    if notification_channel not in VALID_NOTIFICATION_CHANNELS:
        raise RuntimeError(
            f"NOTIFICATION_CHANNEL must be one of {VALID_NOTIFICATION_CHANNELS}, got {notification_channel!r}"
        )
    is_telegram = notification_channel == "telegram"
    is_whatsapp = notification_channel == "whatsapp"

    whatsapp_to_numbers = _parse_number_list(os.environ.get("WHATSAPP_TO_NUMBER") or "")
    if is_whatsapp and not whatsapp_to_numbers:
        raise RuntimeError("Missing required environment variable: WHATSAPP_TO_NUMBER")

    return Config(
        base_url=os.environ.get("SCHOOL_BASE_URL") or "https://entab.online/HISSJR",
        user_id=_require("SCHOOL_USER_ID"),
        password=_require("SCHOOL_PASSWORD"),
        notification_channel=notification_channel,
        telegram_bot_token=_require("TELEGRAM_BOT_TOKEN") if is_telegram else os.environ.get("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=_require("TELEGRAM_CHAT_ID") if is_telegram else os.environ.get("TELEGRAM_CHAT_ID"),
        twilio_account_sid=_require("TWILIO_ACCOUNT_SID") if is_whatsapp else os.environ.get("TWILIO_ACCOUNT_SID"),
        twilio_auth_token=_require("TWILIO_AUTH_TOKEN") if is_whatsapp else os.environ.get("TWILIO_AUTH_TOKEN"),
        twilio_whatsapp_from=os.environ.get("TWILIO_WHATSAPP_FROM") or DEFAULT_TWILIO_WHATSAPP_FROM,
        whatsapp_to_numbers=whatsapp_to_numbers,
        ai_provider=ai_provider,
        anthropic_api_key=_require("ANTHROPIC_API_KEY") if ai_provider == "anthropic" else os.environ.get("ANTHROPIC_API_KEY"),
        anthropic_model=os.environ.get("ANTHROPIC_MODEL") or "claude-haiku-4-5-20251001",
        gemini_api_key=_require("GEMINI_API_KEY") if ai_provider == "gemini" else os.environ.get("GEMINI_API_KEY"),
        gemini_model=os.environ.get("GEMINI_MODEL") or "gemini-2.5-flash",
        target_date=os.environ.get("TARGET_DATE"),
        circular_delivery_mode=circular_delivery_mode,
    )
