"""Анкета профілю: стать, вік, зріст, вага, активність, ціль → денна норма."""

import warnings

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.warnings import PTBUserWarning
from telegram.ext import (CallbackQueryHandler, CommandHandler, ContextTypes,
                          ConversationHandler, MessageHandler, filters)

from bot import db
from bot.common import BTN_PROFILE, MAIN_MENU, achievements_text, has_profile
from bot.nutrition import ACTIVITY, GOALS, SEX, calc_targets

# Анкета йде в одному чаті, тож per_message не потрібен.
warnings.filterwarnings("ignore", message=".*per_message", category=PTBUserWarning)

SEX_STATE, AGE, HEIGHT, WEIGHT, ACTIVITY_STATE, GOAL = range(6)


def profile_text(user) -> str:
    return (
        "👤 <b>Твій профіль</b>\n\n"
        f"{SEX[user['sex']]}, {user['age']} р., {user['height_cm']:.0f} см, "
        f"{user['weight_kg']:.1f} кг\n"
        f"🏃 {ACTIVITY[user['activity']][0]}\n"
        f"🎯 {GOALS[user['goal']]}\n\n"
        f"🔥 Норма: <b>{user['target_kcal']:.0f} ккал</b>/день\n"
        f"🥩 Білки {user['protein_g']:.0f} г · 🧈 Жири {user['fat_g']:.0f} г · "
        f"🍞 Вуглеводи {user['carbs_g']:.0f} г\n"
        f"💧 Вода {user['water_ml']} мл\n"
        f"🔔 Нагадування: {'увімкнені' if user['reminders'] else 'вимкнені'} (/reminders)"
    )


async def show_or_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = db.get_user(update.effective_user.id)
    if has_profile(user):
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✏️ Заповнити заново",
                                                         callback_data="profile:edit")]])
        await update.message.reply_text(profile_text(user), parse_mode=ParseMode.HTML,
                                        reply_markup=kb)
        return ConversationHandler.END
    return await ask_sex(update, context)


async def ask_sex(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("👨 Чоловік", callback_data="sex:m"),
        InlineKeyboardButton("👩 Жінка", callback_data="sex:f"),
    ]])
    await update.effective_message.reply_text(
        "📝 Налаштуймо профіль — це 6 коротких питань.\n(/cancel — скасувати)\n\n"
        "Твоя стать?", reply_markup=kb)
    return SEX_STATE


async def got_sex(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    context.user_data["p_sex"] = q.data.split(":")[1]
    await q.edit_message_text(f"Стать: {SEX[context.user_data['p_sex']]}")
    await q.message.reply_text("Скільки тобі років?")
    return AGE


async def _number(update: Update, lo: float, hi: float) -> float | None:
    try:
        value = float(update.message.text.replace(",", ".").strip())
    except ValueError:
        value = None
    if value is None or not lo <= value <= hi:
        await update.message.reply_text(f"Введи число від {lo:g} до {hi:g} 🙂")
        return None
    return value


async def got_age(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    value = await _number(update, 12, 100)
    if value is None:
        return AGE
    context.user_data["p_age"] = int(value)
    await update.message.reply_text("Твій зріст у сантиметрах?")
    return HEIGHT


async def got_height(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    value = await _number(update, 120, 230)
    if value is None:
        return HEIGHT
    context.user_data["p_height"] = value
    await update.message.reply_text("Твоя вага в кілограмах? (наприклад, 64.5)")
    return WEIGHT


async def got_weight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    value = await _number(update, 30, 300)
    if value is None:
        return WEIGHT
    context.user_data["p_weight"] = value
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton(label, callback_data=f"act:{code}")]
         for code, (label, _) in ACTIVITY.items()]
    )
    await update.message.reply_text("Який у тебе рівень активності?", reply_markup=kb)
    return ACTIVITY_STATE


async def got_activity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    context.user_data["p_activity"] = q.data.split(":")[1]
    await q.edit_message_text(f"Активність: {ACTIVITY[context.user_data['p_activity']][0]}")
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton(label, callback_data=f"goal:{code}")]
         for code, label in GOALS.items()]
    )
    await q.message.reply_text("Яка твоя ціль?", reply_markup=kb)
    return GOAL


async def got_goal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    ud = context.user_data
    goal = q.data.split(":")[1]
    targets = calc_targets(ud["p_sex"], ud["p_age"], ud["p_height"], ud["p_weight"],
                           ud["p_activity"], goal)
    user_id = update.effective_user.id
    db.update_user(
        user_id, sex=ud["p_sex"], age=ud["p_age"], height_cm=ud["p_height"],
        weight_kg=ud["p_weight"], activity=ud["p_activity"], goal=goal,
        target_kcal=targets["target_kcal"], protein_g=targets["protein_g"],
        fat_g=targets["fat_g"], carbs_g=targets["carbs_g"], water_ml=targets["water_ml"],
    )
    db.add_weight(user_id, ud["p_weight"])
    new = [c for c in ("profile_done", "weight_logged") if db.unlock(user_id, c)]

    await q.edit_message_text(f"Ціль: {GOALS[goal]}")
    await q.message.reply_text(
        "✅ Готово!\n\n"
        f"Базовий обмін: {targets['bmr']} ккал\n"
        f"З урахуванням активності: {targets['tdee']} ккал\n\n"
        + profile_text(db.get_user(user_id))
        + "\n\n📸 Тепер надсилай фото їжі — і я все порахую!"
        + achievements_text(new),
        parse_mode=ParseMode.HTML,
        reply_markup=MAIN_MENU,
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text("Скасовано 👌", reply_markup=MAIN_MENU)
    return ConversationHandler.END


def build_profile_handler() -> ConversationHandler:
    text = filters.TEXT & ~filters.COMMAND
    return ConversationHandler(
        entry_points=[
            CommandHandler("profile", show_or_start),
            MessageHandler(filters.Text([BTN_PROFILE]), show_or_start),
            CallbackQueryHandler(ask_sex, pattern="^profile:edit$"),
        ],
        states={
            SEX_STATE: [CallbackQueryHandler(got_sex, pattern="^sex:")],
            AGE: [MessageHandler(text, got_age)],
            HEIGHT: [MessageHandler(text, got_height)],
            WEIGHT: [MessageHandler(text, got_weight)],
            ACTIVITY_STATE: [CallbackQueryHandler(got_activity, pattern="^act:")],
            GOAL: [CallbackQueryHandler(got_goal, pattern="^goal:")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
