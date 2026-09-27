"""Точка входу: python -m bot.main"""

import logging

from telegram import BotCommand, Update
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, ContextTypes,
                          MessageHandler, TypeHandler, filters)

from bot import db, handlers as h
from bot.common import access_gate
from bot.config import TELEGRAM_BOT_TOKEN
from bot.profile import build_profile_handler

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

COMMANDS = [
    ("today", "📊 Підсумок дня"),
    ("week", "📈 Графік за тиждень"),
    ("water", "💧 Трекер води"),
    ("weight", "⚖️ Записати вагу"),
    ("suggest", "🍳 Що зʼїсти?"),
    ("ask", "💬 Питання дієтологу"),
    ("achievements", "🏆 Досягнення"),
    ("undo", "↩️ Видалити останній запис"),
    ("export", "📒 Експорт у CSV"),
    ("reminders", "🔔 Нагадування"),
    ("profile", "👤 Профіль і норма"),
    ("help", "❓ Допомога"),
]


async def post_init(app: Application) -> None:
    await app.bot.set_my_commands([BotCommand(c, d) for c, d in COMMANDS])


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Unhandled error", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text("😔 Щось пішло не так. Спробуй ще раз.")


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise SystemExit("Не задано TELEGRAM_BOT_TOKEN (див. .env.example)")
    db.conn()

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()
    app.add_handler(TypeHandler(Update, access_gate), group=-1)

    app.add_handler(build_profile_handler())
    app.add_handler(CommandHandler("start", h.start))
    app.add_handler(CommandHandler("help", h.help_cmd))
    app.add_handler(CommandHandler("today", h.today_cmd))
    app.add_handler(CommandHandler("week", h.week_cmd))
    app.add_handler(CommandHandler("water", h.water_cmd))
    app.add_handler(CommandHandler("weight", h.weight_cmd))
    app.add_handler(CommandHandler("suggest", h.suggest_cmd))
    app.add_handler(CommandHandler("ask", h.ask_cmd))
    app.add_handler(CommandHandler("achievements", h.achievements_cmd))
    app.add_handler(CommandHandler("undo", h.undo_cmd))
    app.add_handler(CommandHandler("export", h.export_cmd))
    app.add_handler(CommandHandler("reminders", h.reminders_cmd))

    app.add_handler(CallbackQueryHandler(h.on_meal_button, pattern=r"^m:"))
    app.add_handler(CallbackQueryHandler(h.on_water_button, pattern=r"^w:"))
    app.add_handler(CallbackQueryHandler(h.undo_cmd, pattern=r"^undo$"))

    app.add_handler(MessageHandler(filters.PHOTO, h.on_photo))
    app.add_handler(MessageHandler(filters.Document.IMAGE, h.on_image_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, h.on_text))

    app.add_error_handler(on_error)
    h.schedule_jobs(app)

    logger.info("Bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
