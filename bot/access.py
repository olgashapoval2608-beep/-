"""Приватний доступ: власник, запрошення за посиланням і підтвердження кнопкою."""

import functools
import html
import logging
import secrets

from telegram import BotCommand, BotCommandScopeChat, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import ApplicationHandlerStop, ContextTypes

from bot import db
from bot.config import ALLOWED_USERS, OWNER_ID, PUBLIC_MODE

logger = logging.getLogger(__name__)

INVITE_PREFIX = "inv_"

OWNER_COMMANDS = [
    ("invite", "🔗 Створити запрошення"),
    ("users", "👥 Хто має доступ"),
]


def is_owner(user_id: int) -> bool:
    return bool(OWNER_ID) and user_id == OWNER_ID


def is_allowed(user_id: int) -> bool:
    return PUBLIC_MODE or is_owner(user_id) or user_id in ALLOWED_USERS or db.has_access(user_id)


def _who(user) -> str:
    name = html.escape(user.full_name or "без імені")
    return f"{name} (@{html.escape(user.username)})" if user.username else name


async def access_gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Виконується перед усіма хендлерами: пускає лише власника і запрошених."""
    user = update.effective_user
    if user is None:
        return
    msg = update.effective_message

    if not OWNER_ID and not PUBLIC_MODE:
        if msg:
            await msg.reply_text(
                "⚙️ Бот ще не налаштований.\n"
                f"Твій Telegram ID: {user.id}\n"
                "Впиши його в OWNER_ID у файлі .env і перезапусти бота."
            )
        raise ApplicationHandlerStop

    if not is_allowed(user.id):
        text = msg.text if msg and msg.text else ""
        if text.startswith(f"/start {INVITE_PREFIX}"):
            code = text.split(maxsplit=1)[1][len(INVITE_PREFIX):]
            if db.use_invite(code, user.id):
                db.grant_access(user.id, user.full_name, user.username)
                await _notify_owner(context, f"✅ За запрошенням приєднався(лась): {_who(user)}")
                # далі запускається звичайний /start
            else:
                await msg.reply_text("😔 Запрошення недійсне або вже використане. "
                                     "Попроси в того, хто тобі його дав, нове.")
                raise ApplicationHandlerStop
        else:
            await _deny(update, context)
            raise ApplicationHandlerStop

    db.ensure_user(user.id, user.first_name or "")


async def _deny(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if update.callback_query:
        await update.callback_query.answer("🔒 Приватний бот", show_alert=True)
        return
    if update.effective_message:
        await update.effective_message.reply_text(
            "🔒 Це приватний бот. Доступ лише за запрошенням власника.\n"
            "Запит власнику надіслано — якщо тебе підтвердять, прийде повідомлення."
        )
    if db.add_access_request(user.id, user.full_name, user.username):
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Дати доступ", callback_data=f"acc:ok:{user.id}"),
            InlineKeyboardButton("🚫 Ні", callback_data=f"acc:no:{user.id}"),
        ]])
        await _notify_owner(context, f"🔔 Хтось хоче користуватися ботом:\n{_who(user)}\nID: {user.id}",
                            kb)


async def _notify_owner(context: ContextTypes.DEFAULT_TYPE, text: str,
                        kb: InlineKeyboardMarkup | None = None) -> None:
    if not OWNER_ID:
        return
    try:
        await context.bot.send_message(OWNER_ID, text, parse_mode=ParseMode.HTML, reply_markup=kb)
    except TelegramError:
        logger.warning("Could not notify owner (has the owner pressed /start?)")


def _owner_only(func):
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not is_owner(update.effective_user.id):
            if update.callback_query:
                await update.callback_query.answer("Лише для власника", show_alert=True)
            else:
                await update.effective_message.reply_text("Ця команда лише для власника бота 🙂")
            return
        await func(update, context)
    return wrapper


@_owner_only
async def invite_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    code = secrets.token_urlsafe(9)
    db.create_invite(code)
    link = f"https://t.me/{context.bot.username}?start={INVITE_PREFIX}{code}"
    await update.message.reply_text(
        "🔗 <b>Одноразове запрошення</b> (діє 7 днів):\n\n"
        f"<code>{link}</code>\n\n"
        "Перешли це посилання людині. Після першого переходу воно перестане працювати.",
        parse_mode=ParseMode.HTML, disable_web_page_preview=True,
    )


@_owner_only
async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rows = db.access_list()
    lines = [f"👑 Власник: ти (ID {OWNER_ID})"]
    if ALLOWED_USERS:
        lines.append("📄 З файлу .env: " + ", ".join(str(i) for i in sorted(ALLOWED_USERS)))
    if not rows:
        lines.append("\nЗапрошених поки немає. Створи запрошення: /invite")
        await update.message.reply_text("\n".join(lines))
        return
    lines.append(f"\n👥 Мають доступ ({len(rows)}):")
    buttons = []
    for r in rows:
        who = r["name"] + (f" (@{r['username']})" if r["username"] else "")
        lines.append(f"• {who} — ID {r['user_id']}")
        buttons.append([InlineKeyboardButton(f"🚫 Забрати доступ: {r['name'][:20]}",
                                             callback_data=f"acc:rm:{r['user_id']}")])
    await update.message.reply_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))


@_owner_only
async def on_access_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    _, action, uid = q.data.split(":")
    user_id = int(uid)
    if action == "ok":
        req = db.conn().execute("SELECT * FROM access_requests WHERE user_id = ?",
                                (user_id,)).fetchone()
        db.grant_access(user_id, req["name"] if req else str(user_id),
                        req["username"] if req else None)
        await q.answer("Доступ надано")
        await q.edit_message_text(q.message.text + "\n\n✅ Доступ надано")
        try:
            await context.bot.send_message(user_id, "🎉 Тобі надали доступ до бота! Натисни /start")
        except TelegramError:
            pass
    elif action == "no":
        await q.answer("Відхилено")
        await q.edit_message_text(q.message.text + "\n\n🚫 Відхилено")
    elif action == "rm":
        db.revoke_access(user_id)
        await q.answer("Доступ забрано")
        await q.message.reply_text(f"🚫 Доступ для ID {user_id} забрано.")


async def setup_owner_commands(app, commands: list[tuple[str, str]]) -> None:
    """Показує власнику в меню команд ще й /invite та /users."""
    if not OWNER_ID:
        return
    try:
        await app.bot.set_my_commands([BotCommand(c, d) for c, d in commands + OWNER_COMMANDS],
                                      scope=BotCommandScopeChat(OWNER_ID))
    except TelegramError:
        logger.info("Owner commands will appear after the owner presses /start")
