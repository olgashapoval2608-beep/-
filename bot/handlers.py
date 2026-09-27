"""Основні хендлери: фото/текст їжі, статистика, вода, вага, коуч, нагадування."""

import csv
import html
import io
import json
import logging
from datetime import time as dtime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Update
from telegram.constants import ChatAction, ParseMode
from telegram.error import Forbidden
from telegram.ext import ContextTypes

from bot import charts, db
from bot.analyzer import (AnalysisError, MealAnalysis, analyze_photo, analyze_text,
                          ask_coach, format_analysis, suggest_meal)
from bot.common import (BTN_ACHIEVEMENTS, BTN_ASK, BTN_SUGGEST, BTN_TODAY, BTN_WATER,
                        BTN_WEEK, BTN_WEIGHT, MAIN_MENU, achievements_text, ai_allowed,
                        check_achievements, coach_context, day_summary, has_profile)
from bot.config import EVENING_SUMMARY_HOUR, LUNCH_REMINDER_HOUR, TIMEZONE
from bot.nutrition import ACHIEVEMENTS, MEAL_TYPES, calc_targets, meal_type_for_hour, progress_bar

logger = logging.getLogger(__name__)

MULTIPLIERS = [0.5, 1.0, 1.5, 2.0]
MAX_IMAGE_BYTES = 5 * 1024 * 1024
SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}

HELP = (
    "🤖 <b>Що я вмію</b>\n\n"
    "📸 <b>Фото їжі</b> — розпізнаю страви, вагу, калорії, БЖВ і корисність\n"
    "✍️ <b>Текст</b> — «2 яйця, тост з авокадо і капучино» теж порахую\n"
    "⚖️ Після аналізу обери розмір порції (½, ×1.5, ×2) і натисни «Записати»\n\n"
    "/today — підсумок дня з прогрес-барами\n"
    "/week — графік калорій за тиждень\n"
    "/water — трекер води 💧\n"
    "/weight 64.5 — записати вагу і побачити динаміку\n"
    "/suggest — що зʼїсти, щоб вписатися в норму\n"
    "/ask питання — спитати ШІ-дієтолога\n"
    "/achievements — твої досягнення 🏆\n"
    "/undo — видалити останній запис\n"
    "/export — вивантажити щоденник у CSV\n"
    "/reminders — увімкнути/вимкнути нагадування\n"
    "/profile — профіль і денна норма\n\n"
    "⚠️ Оцінка за фото приблизна, це не медична порада."
)


# --- базові команди ----------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    name = html.escape(update.effective_user.first_name or "")
    await update.message.reply_text(
        f"👋 Привіт, {name}! Я — твій кишеньковий дієтолог.\n\n"
        "📸 Надішли фото страви — і за кілька секунд отримаєш калорії, БЖВ, "
        "оцінку корисності та цікавий факт.\n\n" + HELP,
        parse_mode=ParseMode.HTML,
        reply_markup=MAIN_MENU,
    )
    if not has_profile(db.get_user(update.effective_user.id)):
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("📝 Налаштувати профіль",
                                                         callback_data="profile:edit")]])
        await update.message.reply_text(
            "Щоб я розрахував твою денну норму калорій, заповни короткий профіль 👇",
            reply_markup=kb,
        )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP, parse_mode=ParseMode.HTML, reply_markup=MAIN_MENU)


# --- аналіз їжі --------------------------------------------------------------

def _meal_keyboard(key: str, mult: float) -> InlineKeyboardMarkup:
    sizes = [
        InlineKeyboardButton(("• " if m == mult else "") + ("½" if m == 0.5 else f"×{m:g}"),
                             callback_data=f"m:{key}:{m:g}")
        for m in MULTIPLIERS
    ]
    return InlineKeyboardMarkup([
        sizes,
        [InlineKeyboardButton("✅ Записати", callback_data=f"m:{key}:ok"),
         InlineKeyboardButton("❌ Не записувати", callback_data=f"m:{key}:no")],
    ])


async def _run_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE, coro) -> None:
    status = await update.message.reply_text("🔍 Аналізую...")
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    try:
        analysis: MealAnalysis = await coro
    except AnalysisError as e:
        await status.edit_text(f"😔 {html.escape(str(e))}")
        return

    user = db.get_user(update.effective_user.id)
    text = format_analysis(analysis, weight_kg=user["weight_kg"])
    if not analysis.items:
        await status.edit_text(text, parse_mode=ParseMode.HTML)
        return

    pending = context.user_data.setdefault("pending", {})
    context.user_data["pending_seq"] = context.user_data.get("pending_seq", 0) + 1
    key = str(context.user_data["pending_seq"])
    pending[key] = {"analysis": analysis.model_dump(), "mult": 1.0}
    for old in list(pending)[:-20]:  # не тримаємо в памʼяті старі аналізи
        pending.pop(old)
    await status.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=_meal_keyboard(key, 1.0))


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ai_allowed(update):
        return
    file = await update.message.photo[-1].get_file()
    data = bytes(await file.download_as_bytearray())
    await _run_analysis(update, context, analyze_photo(data, update.message.caption))


async def on_image_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    doc = update.message.document
    if doc.mime_type not in SUPPORTED_IMAGE_TYPES:
        await update.message.reply_text("Підтримую JPG, PNG, WEBP і GIF 🖼")
        return
    if doc.file_size and doc.file_size > MAX_IMAGE_BYTES:
        await update.message.reply_text("Файл завеликий (макс. 5 МБ). Надішли як фото 📸")
        return
    if not await ai_allowed(update):
        return
    file = await doc.get_file()
    data = bytes(await file.download_as_bytearray())
    await _run_analysis(update, context,
                        analyze_photo(data, update.message.caption, doc.mime_type))


async def on_meal_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    _, key, action = q.data.split(":")
    entry = context.user_data.get("pending", {}).get(key)
    if entry is None:
        await q.answer("Цей аналіз застарів — надішли фото ще раз", show_alert=True)
        await q.edit_message_reply_markup(None)
        return
    analysis = MealAnalysis.model_validate(entry["analysis"])
    user_id = update.effective_user.id
    user = db.get_user(user_id)

    if action == "no":
        context.user_data["pending"].pop(key)
        await q.answer("Не записано")
        await q.edit_message_reply_markup(None)
        return

    if action != "ok":
        entry["mult"] = float(action)
        await q.answer(f"Порція ×{entry['mult']:g}")
        await q.edit_message_text(
            format_analysis(analysis, entry["mult"], user["weight_kg"]),
            parse_mode=ParseMode.HTML, reply_markup=_meal_keyboard(key, entry["mult"]),
        )
        return

    mult = entry["mult"]
    context.user_data["pending"].pop(key)
    t = {k: v * mult for k, v in analysis.totals.items()}
    items = [{**i.model_dump(), "weight_g": i.weight_g * mult, "calories": i.calories * mult}
             for i in analysis.items]
    meal_type = meal_type_for_hour(db.now().hour)
    db.add_meal(user_id, meal_type, analysis.title, items, t["kcal"], t["protein"], t["fat"],
                t["carbs"], analysis.health_score)
    await q.answer("Записано ✅")
    await q.edit_message_text(
        format_analysis(analysis, mult, user["weight_kg"])
        + f"\n\n✅ <b>Записано</b> як {MEAL_TYPES[meal_type]}",
        parse_mode=ParseMode.HTML,
    )

    day = db.day_totals(user_id, db.today())
    if has_profile(user):
        left = user["target_kcal"] - day["kcal"]
        progress = (
            f"📊 Сьогодні: <b>{day['kcal']:.0f}</b> / {user['target_kcal']:.0f} ккал\n"
            f"{progress_bar(day['kcal'], user['target_kcal'])}\n"
            + (f"Залишилось {left:.0f} ккал 👍" if left >= 0
               else f"⚠️ Норму перевищено на {-left:.0f} ккал")
        )
    else:
        progress = f"📊 Сьогодні: <b>{day['kcal']:.0f}</b> ккал"
    new = check_achievements(user_id, health_score=analysis.health_score)
    await q.message.reply_text(progress + achievements_text(new), parse_mode=ParseMode.HTML)


# --- статистика --------------------------------------------------------------

def _today_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("💧 +250 мл", callback_data="w:250"),
        InlineKeyboardButton("↩️ Видалити останнє", callback_data="undo"),
    ]])


async def today_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    new = check_achievements(user_id, check_target=db.now().hour >= 20)
    await update.message.reply_text(day_summary(user_id) + achievements_text(new),
                                    parse_mode=ParseMode.HTML, reply_markup=_today_keyboard())


async def week_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    days = db.daily_kcal(user_id, 7)
    logged = [(d, v) for d, v in days if v > 0]
    if not logged:
        await update.message.reply_text("За останній тиждень ще немає записів. Надішли фото їжі 📸")
        return
    target = user["target_kcal"] if has_profile(user) else None
    avg = sum(v for _, v in logged) / len(logged)
    best = max(logged, key=lambda x: x[1])
    caption = ["📈 <b>Тиждень</b>", f"Середнє: <b>{avg:.0f}</b> ккал/день",
               f"Днів із записами: {len(logged)}/7"]
    if target:
        on_target = sum(1 for _, v in logged if abs(v - target) <= target * 0.1)
        caption.append(f"🎯 У межах норми (±10%): {on_target} дн.")
        caption.append(f"Баланс за тиждень: {sum(v - target for _, v in logged):+.0f} ккал")
    caption.append(f"🔝 Найбільше: {best[1]:.0f} ккал ({best[0].day:02d}.{best[0].month:02d})")
    caption.append(f"🔥 Серія: {db.streak(user_id)} дн.")
    await update.message.reply_photo(charts.week_chart(days, target),
                                     caption="\n".join(caption), parse_mode=ParseMode.HTML)


async def achievements_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    got = db.achievements(update.effective_user.id)
    lines = [f"🏆 <b>Досягнення: {len(got)}/{len(ACHIEVEMENTS)}</b>", ""]
    for code, (emoji, name, desc) in ACHIEVEMENTS.items():
        if code in got:
            lines.append(f"{emoji} <b>{name}</b> — {desc}")
        else:
            lines.append(f"🔒 <i>{name}</i> — {desc}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def undo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    row = db.delete_last_meal(update.effective_user.id)
    text = (f"🗑 Видалено: {html.escape(row['title'] or '')} ({row['kcal']:.0f} ккал)"
            if row else "Немає записів для видалення")
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(text)
    else:
        await update.message.reply_text(text)


async def export_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    meals = db.all_meals(update.effective_user.id)
    if not meals:
        await update.message.reply_text("Щоденник поки порожній 📭")
        return
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Дата", "Час", "Прийом", "Страва", "Склад", "Ккал", "Білки", "Жири",
                "Вуглеводи", "Корисність"])
    for m in meals:
        items = ", ".join(f"{i['name']} {i['weight_g']:.0f}г" for i in json.loads(m["items_json"]))
        w.writerow([m["day"], m["ts"][11:16], MEAL_TYPES.get(m["meal_type"], ""), m["title"],
                    items, f"{m['kcal']:.0f}", f"{m['protein_g']:.1f}", f"{m['fat_g']:.1f}",
                    f"{m['carbs_g']:.1f}", m["health_score"]])
    data = io.BytesIO(buf.getvalue().encode("utf-8-sig"))  # utf-8-sig — щоб Excel не ламав кирилицю
    await update.message.reply_document(InputFile(data, filename="food_diary.csv"),
                                        caption=f"📒 Твій щоденник. Записів: {len(meals)}")


# --- вода --------------------------------------------------------------------

def _water_text(user_id: int) -> str:
    user = db.get_user(user_id)
    ml = db.water_for_day(user_id, db.today())
    goal = user["water_ml"] or 2000
    glasses = "💧" * min(ml // 250, 12) or "—"
    return (f"💧 <b>Вода сьогодні: {ml} / {goal} мл</b>\n{progress_bar(ml, goal)}\n"
            f"{glasses}")


def _water_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("+150", callback_data="w:150"),
        InlineKeyboardButton("+250 🥛", callback_data="w:250"),
        InlineKeyboardButton("+500 🍶", callback_data="w:500"),
        InlineKeyboardButton("−250", callback_data="w:-250"),
    ]])


async def water_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(_water_text(update.effective_user.id),
                                    parse_mode=ParseMode.HTML, reply_markup=_water_keyboard())


async def on_water_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    user_id = update.effective_user.id
    ml = int(q.data.split(":")[1])
    if ml < 0:
        ml = -min(-ml, db.water_for_day(user_id, db.today()))
    if ml:
        db.add_water(user_id, ml)
    await q.answer(f"{ml:+d} мл 💧")
    new = check_achievements(user_id)
    text = _water_text(user_id) + achievements_text(new)
    if q.message.text and q.message.text.startswith("💧 Вода сьогодні"):
        await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=_water_keyboard())
    else:
        await q.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=_water_keyboard())


# --- вага --------------------------------------------------------------------

async def _log_weight(update: Update, kg: float) -> None:
    user_id = update.effective_user.id
    history_before = db.weight_history(user_id)
    db.add_weight(user_id, kg)
    user = db.get_user(user_id)
    lines = [f"⚖️ Записано: <b>{kg:.1f} кг</b>"]
    previous = [w for d, w in history_before if d != db.today()]
    if previous:
        lines.append(f"Від минулого запису: {kg - previous[-1]:+.1f} кг")
        lines.append(f"Від першого запису: {kg - history_before[0][1]:+.1f} кг")
    if has_profile(user):
        t = calc_targets(user["sex"], user["age"], user["height_cm"], kg, user["activity"],
                         user["goal"])
        db.update_user(user_id, weight_kg=kg, target_kcal=t["target_kcal"],
                       protein_g=t["protein_g"], fat_g=t["fat_g"], carbs_g=t["carbs_g"],
                       water_ml=t["water_ml"])
        lines.append(f"🔄 Норму оновлено: {t['target_kcal']} ккал/день")
    else:
        db.update_user(user_id, weight_kg=kg)
    if db.unlock(user_id, "weight_logged"):
        lines.append(achievements_text(["weight_logged"]))
    history = db.weight_history(user_id)
    if len(history) >= 2:
        await update.message.reply_photo(charts.weight_chart(history), caption="\n".join(lines),
                                         parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


def _parse_kg(text: str) -> float | None:
    try:
        kg = float(text.replace(",", ".").replace("кг", "").strip())
    except ValueError:
        return None
    return kg if 30 <= kg <= 300 else None


async def weight_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    kg = _parse_kg(" ".join(context.args)) if context.args else None
    if kg is None:
        context.user_data["await"] = "weight"
        await update.message.reply_text("⚖️ Надішли свою вагу в кг, наприклад: 64.5")
        return
    await _log_weight(update, kg)


# --- ШІ-коуч -----------------------------------------------------------------

async def _coach_reply(update: Update, coro) -> None:
    await update.effective_chat.send_action(ChatAction.TYPING)
    try:
        text = await coro
    except AnalysisError as e:
        text = f"😔 {e}"
    await update.message.reply_text(text)


async def suggest_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ai_allowed(update):
        return
    await update.message.reply_text("🤔 Підбираю варіанти...")
    await _coach_reply(update, suggest_meal(coach_context(update.effective_user.id)))


async def ask_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    question = " ".join(context.args) if context.args else ""
    if not question:
        context.user_data["await"] = "ask"
        await update.message.reply_text(
            "💬 Постав питання дієтологу. Наприклад:\n"
            "• Чи можна їсти після 18:00?\n• Скільки білка в сирі?\n• Чим замінити солодке?")
        return
    await _ask(update, question)


async def _ask(update: Update, question: str) -> None:
    if not await ai_allowed(update):
        return
    await _coach_reply(update, ask_coach(question, coach_context(update.effective_user.id)))


# --- текст -------------------------------------------------------------------

MENU_ROUTES = {
    BTN_TODAY: today_cmd,
    BTN_WEEK: week_cmd,
    BTN_WATER: water_cmd,
    BTN_SUGGEST: suggest_cmd,
    BTN_ACHIEVEMENTS: achievements_cmd,
}


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()
    context.args = []
    if text in MENU_ROUTES:
        context.user_data.pop("await", None)
        await MENU_ROUTES[text](update, context)
        return
    if text == BTN_WEIGHT:
        await weight_cmd(update, context)
        return
    if text == BTN_ASK:
        await ask_cmd(update, context)
        return

    waiting = context.user_data.pop("await", None)
    if waiting == "weight":
        kg = _parse_kg(text)
        if kg is None:
            context.user_data["await"] = "weight"
            await update.message.reply_text("Введи вагу числом від 30 до 300, наприклад 64.5")
            return
        await _log_weight(update, kg)
        return
    if waiting == "ask":
        await _ask(update, text)
        return

    if len(text) < 3:
        await update.message.reply_text("Надішли фото їжі або опиши, що зʼїв(ла) 📸")
        return
    if not await ai_allowed(update):
        return
    await _run_analysis(update, context, analyze_text(text))


# --- нагадування -------------------------------------------------------------

async def reminders_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = db.get_user(update.effective_user.id)
    new_value = 0 if user["reminders"] else 1
    db.update_user(user["user_id"], reminders=new_value)
    await update.message.reply_text(
        f"🔔 Нагадування увімкнено: о {LUNCH_REMINDER_HOUR}:00 (якщо ще нічого не записано) "
        f"і підсумок дня о {EVENING_SUMMARY_HOUR}:00."
        if new_value else "🔕 Нагадування вимкнено."
    )


async def _send_safe(context: ContextTypes.DEFAULT_TYPE, user_id: int, text: str) -> None:
    try:
        await context.bot.send_message(user_id, text, parse_mode=ParseMode.HTML)
    except Forbidden:  # користувач заблокував бота
        db.update_user(user_id, reminders=0)


async def lunch_reminder_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    for user in db.users_with_reminders():
        if not db.meals_for_day(user["user_id"], db.today()):
            await _send_safe(context, user["user_id"],
                             "🍽 Не забудь записати, що ти сьогодні їв(ла)! Просто надішли фото 📸")


async def evening_summary_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    for user in db.users_with_reminders():
        user_id = user["user_id"]
        if not db.meals_for_day(user_id, db.today()):
            continue
        new = check_achievements(user_id, check_target=True)
        text = "🌙 <b>Підсумок дня</b>\n\n" + day_summary(user_id) + achievements_text(new)
        if has_profile(user) and db.water_for_day(user_id, db.today()) < user["water_ml"]:
            text += "\n\n💧 Ще встигнеш випити склянку води!"
        await _send_safe(context, user_id, text)


def schedule_jobs(app) -> None:
    app.job_queue.run_daily(lunch_reminder_job, dtime(LUNCH_REMINDER_HOUR, tzinfo=TIMEZONE))
    app.job_queue.run_daily(evening_summary_job, dtime(EVENING_SUMMARY_HOUR, tzinfo=TIMEZONE))
