import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class Config:
    base_url: str
    user_id: str
    password: str
    telegram_bot_token: str
    telegram_chat_id: str
    anthropic_api_key: str
    anthropic_model: str
    target_date: Optional[str]


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def load_config() -> Config:
    return Config(
        base_url=os.environ.get("SCHOOL_BASE_URL", "https://entab.online/HISSJR"),
        user_id=_require("SCHOOL_USER_ID"),
        password=_require("SCHOOL_PASSWORD"),
        telegram_bot_token=_require("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=_require("TELEGRAM_CHAT_ID"),
        anthropic_api_key=_require("ANTHROPIC_API_KEY"),
        anthropic_model=os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
        target_date=os.environ.get("TARGET_DATE"),
    )
