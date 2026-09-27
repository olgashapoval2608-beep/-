"""Усі звернення до Claude API: фото, текстовий опис, поради, питання коучу."""

import base64
import html

import anthropic
from pydantic import BaseModel, Field

from bot.config import CLAUDE_MODEL

# Моделі, для яких вмикаємо серверний fallback при відмові (refusal).
FALLBACK_MODELS = {"claude-opus-5", "claude-fable-5-1"}

ANALYSIS_PROMPT = """Ти — дієтолог-нутриціолог у Telegram-боті для підрахунку калорій.
Визнач кожну страву або продукт, оціни вагу порції в грамах (орієнтуйся на розмір
тарілки, приборів, упаковки або на опис користувача) і розрахуй калорії та БЖВ.
Враховуй приховані калорії: олію для смаження, соуси, цукор у напоях.
Пиши українською, дружньо і коротко. Оціни корисність прийому їжі від 1 до 10.
fun_fact — один цікавий або кумедний факт про цю їжу (1 речення).
Якщо їжі немає — поверни порожній список items і поясни це в verdict."""

COACH_PROMPT = """Ти — дружній дієтолог-коуч у Telegram-боті. Відповідай українською,
коротко (до 150 слів), по суті, з кількома доречними емодзі. Не став медичних
діагнозів; при серйозних проблемах зі здоровʼям радь звернутися до лікаря.
Не використовуй Markdown-розмітку (зірочки, решітки) — лише звичайний текст."""


class FoodItem(BaseModel):
    name: str = Field(description="Назва страви або продукту українською")
    weight_g: float = Field(description="Орієнтовна вага порції в грамах")
    calories: float = Field(description="Калорії, ккал")
    protein_g: float
    fat_g: float
    carbs_g: float


class MealAnalysis(BaseModel):
    title: str = Field(description="Коротка назва прийому їжі, 2-5 слів")
    items: list[FoodItem]
    health_score: int = Field(description="Корисність від 1 до 10")
    confidence: str = Field(description="Впевненість оцінки: висока, середня або низька")
    verdict: str = Field(description="Коротка оцінка і порада, 1-2 речення")
    fun_fact: str = Field(description="Цікавий факт про цю їжу, 1 речення")

    @property
    def totals(self) -> dict:
        return {
            "kcal": sum(i.calories for i in self.items),
            "protein": sum(i.protein_g for i in self.items),
            "fat": sum(i.fat_g for i in self.items),
            "carbs": sum(i.carbs_g for i in self.items),
        }


class AnalysisError(Exception):
    pass


client = anthropic.AsyncAnthropic()


def _model_kwargs(effort: str) -> dict:
    kwargs: dict = {}
    # Haiku 4.5 не підтримує adaptive thinking і effort.
    if not CLAUDE_MODEL.startswith("claude-haiku"):
        kwargs["thinking"] = {"type": "adaptive"}
        kwargs["output_config"] = {"effort": effort}
    if CLAUDE_MODEL in FALLBACK_MODELS:
        kwargs["betas"] = ["server-side-fallback-2026-07-01"]
        kwargs["fallbacks"] = "default"
    return kwargs


async def _analyze(content: list[dict]) -> MealAnalysis:
    response = await client.beta.messages.parse(
        model=CLAUDE_MODEL,
        max_tokens=16000,
        system=ANALYSIS_PROMPT,
        output_format=MealAnalysis,
        messages=[{"role": "user", "content": content}],
        **_model_kwargs("medium"),
    )
    if response.stop_reason == "refusal":
        raise AnalysisError("Модель відмовилась це аналізувати.")
    if response.parsed_output is None:
        raise AnalysisError("Не вдалося отримати відповідь від моделі.")
    return response.parsed_output


async def analyze_photo(image_bytes: bytes, caption: str | None = None,
                        media_type: str = "image/jpeg") -> MealAnalysis:
    image_data = base64.standard_b64encode(image_bytes).decode("utf-8")
    text = "Проаналізуй їжу на фото."
    if caption:
        text += f"\nПідпис користувача (використай як уточнення): {caption}"
    return await _analyze([
        {"type": "image",
         "source": {"type": "base64", "media_type": media_type, "data": image_data}},
        {"type": "text", "text": text},
    ])


async def analyze_text(description: str) -> MealAnalysis:
    return await _analyze([
        {"type": "text", "text": f"Користувач описав, що зʼїв:\n{description}"},
    ])


async def _chat(system: str, prompt: str) -> str:
    response = await client.beta.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=16000,
        system=system,
        messages=[{"role": "user", "content": prompt}],
        **_model_kwargs("low"),
    )
    if response.stop_reason == "refusal":
        raise AnalysisError("Модель відмовилась відповідати на це питання.")
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    if not text:
        raise AnalysisError("Не вдалося отримати відповідь від моделі.")
    return text


async def suggest_meal(context: str) -> str:
    return await _chat(
        COACH_PROMPT,
        f"{context}\n\nЗапропонуй 3 варіанти, що зʼїсти зараз, щоб вписатися в залишок "
        "калорій і БЖВ. Для кожного — назва, приблизні ккал і чому це хороший вибір.",
    )


async def ask_coach(question: str, context: str) -> str:
    return await _chat(COACH_PROMPT, f"{context}\n\nПитання користувача: {question}")


def format_analysis(a: MealAnalysis, multiplier: float = 1.0,
                    weight_kg: float | None = None) -> str:
    from bot.nutrition import exercise_equivalents, health_emoji

    if not a.items:
        return f"🤔 Не бачу тут їжі.\n{html.escape(a.verdict)}"

    lines = [f"🍽 <b>{html.escape(a.title)}</b>"]
    if multiplier != 1:
        lines[0] += f"  <i>(×{multiplier:g} порції)</i>"
    lines.append("")
    for item in a.items:
        m = multiplier
        lines.append(
            f"• <b>{html.escape(item.name)}</b> (~{item.weight_g * m:.0f} г) — "
            f"{item.calories * m:.0f} ккал\n"
            f"   Б {item.protein_g * m:.1f} · Ж {item.fat_g * m:.1f} · В {item.carbs_g * m:.1f}"
        )
    t = {k: v * multiplier for k, v in a.totals.items()}
    lines += [
        "",
        f"🔥 <b>Разом: {t['kcal']:.0f} ккал</b>",
        f"🥩 Б {t['protein']:.0f} г · 🧈 Ж {t['fat']:.0f} г · 🍞 В {t['carbs']:.0f} г",
        "",
        f"{health_emoji(a.health_score)} Корисність: <b>{a.health_score}/10</b>"
        f" · впевненість: {html.escape(a.confidence)}",
        f"💪 Щоб спалити: {exercise_equivalents(t['kcal'], weight_kg)}",
        "",
        f"💬 {html.escape(a.verdict)}",
        f"🤓 <i>{html.escape(a.fun_fact)}</i>",
    ]
    return "\n".join(lines)
