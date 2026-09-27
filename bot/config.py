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

# Telegram ID власника. Лише власник може давати доступ іншим (/invite, /users).
# Поки не задано, бот нікого не обслуговує і лише підказує твій ID.
OWNER_ID = int(os.environ.get("OWNER_ID", "0").strip() or 0)

# Додаткові Telegram ID через кому, яким доступ дозволено завжди.
ALLOWED_USERS = {
    int(x) for x in os.environ.get("ALLOWED_USERS", "").replace(" ", "").split(",") if x
}

# true — ботом може користуватися будь-хто (не рекомендується: ліміти ШІ спільні).
PUBLIC_MODE = os.environ.get("PUBLIC_MODE", "false").strip().lower() in ("1", "true", "yes")

# Час щоденних нагадувань (години за TIMEZONE).
LUNCH_REMINDER_HOUR = int(os.environ.get("LUNCH_REMINDER_HOUR", "14"))
EVENING_SUMMARY_HOUR = int(os.environ.get("EVENING_SUMMARY_HOUR", "21"))
