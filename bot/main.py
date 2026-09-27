"""Telegram-бот для розрахунку калорій по фото."""

import html
import logging
import os

import anthropic
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

load_dotenv()

from bot.analyzer import AnalysisError, analyze_photo, format_analysis  # noqa: E402

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

WELCOME = (
    "👋 Привіт! Я рахую калорії по фото.\n\n"
    "📸 Надішли фото своєї страви — я визначу продукти, орієнтовну вагу, "
    "калорії та БЖВ.\n"
    "✍️ Можеш додати підпис до фото для точності, наприклад: «гречка 200 г, курка 150 г».\n\n"
    "⚠️ Це приблизна оцінка, а не лабораторний аналіз."
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(WELCOME)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    await context.bot.send_chat_action(message.chat_id, ChatAction.TYPING)
    status = await message.reply_text("🔍 Аналізую фото...")

    photo = message.photo[-1]  # найбільша роздільна здатність
    file = await photo.get_file()
    image_bytes = bytes(await file.download_as_bytearray())

    try:
        analysis = await analyze_photo(image_bytes, message.caption)
        text = format_analysis(analysis)
    except AnalysisError as e:
        text = f"😔 {html.escape(str(e))}"
    except anthropic.RateLimitError:
        text = "⏳ Забагато запитів. Спробуй за хвилину."
    except anthropic.APIStatusError as e:
        logger.exception("Anthropic API error: %s", e.status_code)
        text = "😔 Помилка сервісу аналізу. Спробуй пізніше."
    except anthropic.APIConnectionError:
        logger.exception("Anthropic connection error")
        text = "😔 Немає зʼєднання з сервісом аналізу. Спробуй пізніше."

    await status.edit_text(text, parse_mode=ParseMode.HTML)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Надішли, будь ласка, зображення як фото (не як файл) 📸")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Надішли фото їжі, і я порахую калорії 📸")


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("Не задано TELEGRAM_BOT_TOKEN (див. .env.example)")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler(["start", "help"], start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.IMAGE, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
