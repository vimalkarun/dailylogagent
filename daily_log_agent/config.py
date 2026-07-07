import os
from dataclasses import dataclass
from typing import Optional

VALID_PROVIDERS = ("anthropic", "gemini")
VALID_CIRCULAR_DELIVERY_MODES = ("summary", "raw")


@dataclass
class Config:
    base_url: str
    user_id: str
    password: str
    telegram_bot_token: str
    telegram_chat_id: str
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


def load_config() -> Config:
    ai_provider = (os.environ.get("AI_PROVIDER") or "anthropic").strip().lower()
    if ai_provider not in VALID_PROVIDERS:
        raise RuntimeError(f"AI_PROVIDER must be one of {VALID_PROVIDERS}, got {ai_provider!r}")

    circular_delivery_mode = (os.environ.get("CIRCULAR_DELIVERY_MODE") or "summary").strip().lower()
    if circular_delivery_mode not in VALID_CIRCULAR_DELIVERY_MODES:
        raise RuntimeError(
            f"CIRCULAR_DELIVERY_MODE must be one of {VALID_CIRCULAR_DELIVERY_MODES}, got {circular_delivery_mode!r}"
        )

    return Config(
        base_url=os.environ.get("SCHOOL_BASE_URL") or "https://entab.online/HISSJR",
        user_id=_require("SCHOOL_USER_ID"),
        password=_require("SCHOOL_PASSWORD"),
        telegram_bot_token=_require("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=_require("TELEGRAM_CHAT_ID"),
        ai_provider=ai_provider,
        anthropic_api_key=_require("ANTHROPIC_API_KEY") if ai_provider == "anthropic" else os.environ.get("ANTHROPIC_API_KEY"),
        anthropic_model=os.environ.get("ANTHROPIC_MODEL") or "claude-haiku-4-5-20251001",
        gemini_api_key=_require("GEMINI_API_KEY") if ai_provider == "gemini" else os.environ.get("GEMINI_API_KEY"),
        gemini_model=os.environ.get("GEMINI_MODEL") or "gemini-2.5-flash",
        target_date=os.environ.get("TARGET_DATE"),
        circular_delivery_mode=circular_delivery_mode,
    )
