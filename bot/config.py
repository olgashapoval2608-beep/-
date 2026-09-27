"""Налаштування бота зі змінних оточення (.env)."""

import os
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
# "gemini" — безкоштовний тариф Google; "claude" — платний Anthropic Claude.
AI_PROVIDER = os.environ.get("AI_PROVIDER", "gemini").strip().lower()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5")
DB_PATH = os.environ.get("DB_PATH", "data/bot.db")
TIMEZONE = ZoneInfo(os.environ.get("TIMEZONE", "Europe/Kyiv"))

# Скільки запитів до ШІ (фото, текст, поради) може зробити один користувач за день.
DAILY_AI_LIMIT = int(os.environ.get("DAILY_AI_LIMIT", "40"))

# Telegram ID через кому. Якщо порожньо — ботом може користуватися будь-хто.
ALLOWED_USERS = {
    int(x) for x in os.environ.get("ALLOWED_USERS", "").replace(" ", "").split(",") if x
}

# Час щоденних нагадувань (години за TIMEZONE).
LUNCH_REMINDER_HOUR = int(os.environ.get("LUNCH_REMINDER_HOUR", "14"))
EVENING_SUMMARY_HOUR = int(os.environ.get("EVENING_SUMMARY_HOUR", "21"))
