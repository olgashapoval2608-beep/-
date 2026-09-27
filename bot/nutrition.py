"""Розрахунок норм, прогрес-бари, «скільки це бігу» та досягнення."""

SEX = {"m": "Чоловік", "f": "Жінка"}

ACTIVITY = {
    "min": ("Мінімальна (сидяча робота)", 1.2),
    "low": ("Легка (1–3 тренування/тиждень)", 1.375),
    "mid": ("Середня (3–5 тренувань)", 1.55),
    "high": ("Висока (6–7 тренувань)", 1.725),
    "max": ("Дуже висока (спорт / фізична праця)", 1.9),
}

GOALS = {
    "lose": "📉 Схуднути",
    "keep": "⚖️ Тримати вагу",
    "gain": "📈 Набрати масу",
}

MEAL_TYPES = {
    "breakfast": "🌅 Сніданок",
    "lunch": "🍲 Обід",
    "snack": "🍎 Перекус",
    "dinner": "🌙 Вечеря",
}

# code -> (емодзі, назва, опис)
ACHIEVEMENTS = {
    "first_meal": ("🥇", "Перший крок", "Записати перший прийом їжі"),
    "meals_10": ("🔟", "Десятка", "Записати 10 прийомів їжі"),
    "meals_50": ("🍱", "Гурман", "Записати 50 прийомів їжі"),
    "meals_100": ("💯", "Сотня", "Записати 100 прийомів їжі"),
    "streak_3": ("🔥", "Розігрів", "3 дні поспіль із записами"),
    "streak_7": ("⚡", "Тиждень сили", "7 днів поспіль із записами"),
    "streak_30": ("👑", "Залізна воля", "30 днів поспіль із записами"),
    "water_goal": ("💧", "Водяник", "Виконати норму води за день"),
    "on_target": ("🎯", "Снайпер", "Закрити день у межах ±10% від норми"),
    "healthy_plate": ("🥗", "Здорова тарілка", "Отримати оцінку 9+ за корисність"),
    "weight_logged": ("⚖️", "На вагах", "Вперше записати свою вагу"),
    "profile_done": ("📝", "Знайомство", "Заповнити профіль"),
}


def calc_targets(sex: str, age: int, height_cm: float, weight_kg: float,
                 activity: str, goal: str) -> dict:
    """Формула Міффліна–Сан Жеора + поправка на ціль."""
    bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + (5 if sex == "m" else -161)
    tdee = bmr * ACTIVITY[activity][1]
    if goal == "lose":
        kcal = max(tdee * 0.85, 1500 if sex == "m" else 1200)
        protein_per_kg = 1.8
    elif goal == "gain":
        kcal = tdee * 1.1
        protein_per_kg = 1.8
    else:
        kcal = tdee
        protein_per_kg = 1.5
    protein = protein_per_kg * weight_kg
    fat = kcal * 0.28 / 9
    carbs = max((kcal - protein * 4 - fat * 9) / 4, 0)
    return {
        "target_kcal": round(kcal),
        "protein_g": round(protein),
        "fat_g": round(fat),
        "carbs_g": round(carbs),
        "water_ml": int(round(weight_kg * 30 / 250) * 250),
        "bmr": round(bmr),
        "tdee": round(tdee),
    }


def progress_bar(value: float, target: float, width: int = 10) -> str:
    if target <= 0:
        return ""
    ratio = value / target
    filled = min(int(round(ratio * width)), width)
    bar = "▓" * filled + "░" * (width - filled)
    return f"{bar} {ratio * 100:.0f}%"


def meal_type_for_hour(hour: int) -> str:
    if hour < 11:
        return "breakfast"
    if hour < 16:
        return "lunch"
    if hour < 18:
        return "snack"
    return "dinner"


def exercise_equivalents(kcal: float, weight_kg: float | None) -> str:
    """Скільки хвилин активності «спалює» ці калорії (формула MET)."""
    kg = weight_kg or 70
    activities = [("🚶", "ходьби", 3.5), ("🏃", "бігу", 9.8), ("🚴", "велосипеда", 7.5)]
    parts = []
    for emoji, name, met in activities:
        per_min = met * 3.5 * kg / 200
        parts.append(f"{emoji} {kcal / per_min:.0f} хв {name}")
    return " · ".join(parts)


def health_emoji(score: int) -> str:
    if score >= 8:
        return "🟢"
    if score >= 5:
        return "🟡"
    return "🔴"
