"""Спільні штуки: доступ, меню, ліміти ШІ, підсумок дня, досягнення."""

import html

from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import ApplicationHandlerStop, ContextTypes

from bot import db
from bot.config import ALLOWED_USERS, DAILY_AI_LIMIT
from bot.nutrition import ACHIEVEMENTS, GOALS, MEAL_TYPES, progress_bar

BTN_TODAY = "📊 Сьогодні"
BTN_WEEK = "📈 Тиждень"
BTN_WATER = "💧 Вода"
BTN_WEIGHT = "⚖️ Вага"
BTN_SUGGEST = "🍳 Що зʼїсти?"
BTN_ASK = "💬 Спитати коуча"
BTN_ACHIEVEMENTS = "🏆 Досягнення"
BTN_PROFILE = "👤 Профіль"

MAIN_MENU = ReplyKeyboardMarkup(
    [
        [KeyboardButton(BTN_TODAY), KeyboardButton(BTN_WEEK)],
        [KeyboardButton(BTN_WATER), KeyboardButton(BTN_WEIGHT), KeyboardButton(BTN_SUGGEST)],
        [KeyboardButton(BTN_ASK), KeyboardButton(BTN_ACHIEVEMENTS), KeyboardButton(BTN_PROFILE)],
    ],
    resize_keyboard=True,
    input_field_placeholder="Надішли фото їжі або опиши, що зʼїв(ла)",
)


async def access_gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Виконується перед усіма хендлерами: перевіряє доступ і створює користувача."""
    user = update.effective_user
    if user is None:
        return
    if ALLOWED_USERS and user.id not in ALLOWED_USERS:
        if update.effective_message:
            await update.effective_message.reply_text(
                f"🔒 Це приватний бот. Твій Telegram ID: {user.id}"
            )
        raise ApplicationHandlerStop
    db.ensure_user(user.id, user.first_name or "")


async def ai_allowed(update: Update) -> bool:
    if db.use_ai_quota(update.effective_user.id, DAILY_AI_LIMIT):
        return True
    await update.effective_message.reply_text(
        f"⏳ Денний ліміт запитів до ШІ ({DAILY_AI_LIMIT}) вичерпано. Повертайся завтра!\n"
        "Воду, вагу та статистику можна записувати без обмежень."
    )
    return False


def has_profile(user) -> bool:
    return bool(user and user["target_kcal"])


def day_summary(user_id: int, title: str = "Сьогодні") -> str:
    user = db.get_user(user_id)
    day = db.today()
    t = db.day_totals(user_id, day)
    water = db.water_for_day(user_id, day)
    lines = [f"📊 <b>{title}, {day.day:02d}.{day.month:02d}</b>", ""]

    if has_profile(user):
        target = user["target_kcal"]
        left = target - t["kcal"]
        lines += [
            f"🔥 <b>{t['kcal']:.0f}</b> / {target:.0f} ккал",
            progress_bar(t["kcal"], target),
            f"{'✅ Залишилось' if left >= 0 else '⚠️ Перевищено на'}: {abs(left):.0f} ккал",
            "",
            f"🥩 Білки  {t['protein']:.0f}/{user['protein_g']:.0f} г  "
            f"{progress_bar(t['protein'], user['protein_g'], 6)}",
            f"🧈 Жири   {t['fat']:.0f}/{user['fat_g']:.0f} г  "
            f"{progress_bar(t['fat'], user['fat_g'], 6)}",
            f"🍞 Вугл.  {t['carbs']:.0f}/{user['carbs_g']:.0f} г  "
            f"{progress_bar(t['carbs'], user['carbs_g'], 6)}",
            f"💧 Вода   {water}/{user['water_ml']} мл  "
            f"{progress_bar(water, user['water_ml'], 6)}",
        ]
    else:
        lines += [
            f"🔥 <b>{t['kcal']:.0f}</b> ккал",
            f"🥩 Б {t['protein']:.0f} г · 🧈 Ж {t['fat']:.0f} г · 🍞 В {t['carbs']:.0f} г",
            f"💧 Вода: {water} мл",
            "",
            "💡 Заповни /profile, щоб я розрахував твою норму.",
        ]

    s = db.streak(user_id)
    if s:
        lines += ["", f"🔥 Серія: <b>{s}</b> дн. поспіль"]

    meals = db.meals_for_day(user_id, day)
    if meals:
        lines += ["", "<b>Прийоми їжі:</b>"]
        for m in meals:
            emoji = MEAL_TYPES.get(m["meal_type"], "🍽").split()[0]
            lines.append(
                f"{emoji} {m['ts'][11:16]} {html.escape(m['title'] or '')} — {m['kcal']:.0f} ккал"
            )
    return "\n".join(lines)


def coach_context(user_id: int) -> str:
    """Короткий опис користувача і його дня для підказок від ШІ."""
    user = db.get_user(user_id)
    t = db.day_totals(user_id, db.today())
    parts = [f"Зараз {db.now():%H:%M}."]
    if has_profile(user):
        parts.append(
            f"Користувач: {'чоловік' if user['sex'] == 'm' else 'жінка'}, {user['age']} р., "
            f"{user['height_cm']:.0f} см, {user['weight_kg']:.1f} кг, "
            f"ціль: {GOALS[user['goal']]}. Денна норма: {user['target_kcal']:.0f} ккал, "
            f"Б {user['protein_g']:.0f} / Ж {user['fat_g']:.0f} / В {user['carbs_g']:.0f} г."
        )
        parts.append(
            f"Залишок на сьогодні: {user['target_kcal'] - t['kcal']:.0f} ккал, "
            f"Б {user['protein_g'] - t['protein']:.0f} / Ж {user['fat_g'] - t['fat']:.0f} / "
            f"В {user['carbs_g'] - t['carbs']:.0f} г."
        )
    parts.append(
        f"Сьогодні вже зʼїдено: {t['kcal']:.0f} ккал, Б {t['protein']:.0f} / "
        f"Ж {t['fat']:.0f} / В {t['carbs']:.0f} г."
    )
    titles = [m["title"] for m in db.meals_for_day(user_id, db.today())]
    if titles:
        parts.append("Прийоми їжі сьогодні: " + "; ".join(titles) + ".")
    return "\n".join(parts)


def check_achievements(user_id: int, *, health_score: int | None = None,
                       check_target: bool = False) -> list[str]:
    """Перевіряє умови досягнень і повертає коди щойно отриманих."""
    candidates = []
    n = db.meal_count(user_id)
    for threshold, code in [(1, "first_meal"), (10, "meals_10"), (50, "meals_50"),
                            (100, "meals_100")]:
        if n >= threshold:
            candidates.append(code)
    s = db.streak(user_id)
    for threshold, code in [(3, "streak_3"), (7, "streak_7"), (30, "streak_30")]:
        if s >= threshold:
            candidates.append(code)
    if health_score is not None and health_score >= 9:
        candidates.append("healthy_plate")

    user = db.get_user(user_id)
    if has_profile(user):
        if db.water_for_day(user_id, db.today()) >= user["water_ml"]:
            candidates.append("water_goal")
        if check_target:
            kcal = db.day_totals(user_id, db.today())["kcal"]
            if abs(kcal - user["target_kcal"]) <= user["target_kcal"] * 0.1:
                candidates.append("on_target")
    return [code for code in candidates if db.unlock(user_id, code)]


def achievements_text(codes: list[str]) -> str:
    if not codes:
        return ""
    lines = ["", "🎉 <b>Нове досягнення!</b>"]
    for code in codes:
        emoji, name, desc = ACHIEVEMENTS[code]
        lines.append(f"{emoji} <b>{name}</b> — {desc}")
    return "\n".join(lines)
