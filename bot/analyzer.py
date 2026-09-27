"""Оцінка калорійності їжі на фото через Claude API."""

import base64
import html

import anthropic
from pydantic import BaseModel, Field

MODEL = "claude-opus-5"

SYSTEM_PROMPT = """Ти — дієтолог-нутриціолог. Користувач надсилає фото їжі.
Визнач кожну страву або продукт на фото, оціни вагу порції в грамах
(орієнтуйся на розмір тарілки, столових приборів, упаковки) і розрахуй
калорії та БЖВ (білки, жири, вуглеводи) для кожної позиції.
Назви страв пиши українською. Якщо на фото немає їжі — поверни порожній
список items і поясни це в comment. Якщо користувач додав підпис до фото
(наприклад, вагу або склад), використовуй його як уточнення."""


class FoodItem(BaseModel):
    name: str = Field(description="Назва страви або продукту українською")
    weight_g: float = Field(description="Орієнтовна вага порції в грамах")
    calories: float = Field(description="Калорії, ккал")
    protein_g: float
    fat_g: float
    carbs_g: float


class MealAnalysis(BaseModel):
    items: list[FoodItem]
    confidence: str = Field(description="Впевненість оцінки: висока, середня або низька")
    comment: str = Field(description="Коротка порада або пояснення українською")


class AnalysisError(Exception):
    pass


client = anthropic.AsyncAnthropic()


async def analyze_photo(image_bytes: bytes, caption: str | None = None) -> MealAnalysis:
    image_data = base64.standard_b64encode(image_bytes).decode("utf-8")
    text = "Проаналізуй їжу на фото."
    if caption:
        text += f"\nПідпис користувача: {caption}"

    response = await client.beta.messages.parse(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        thinking={"type": "adaptive"},
        output_config={"effort": "medium"},
        output_format=MealAnalysis,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_data,
                        },
                    },
                    {"type": "text", "text": text},
                ],
            }
        ],
    )

    if response.stop_reason == "refusal":
        raise AnalysisError("Модель відмовилась аналізувати це фото.")
    if response.stop_reason == "max_tokens" or response.parsed_output is None:
        raise AnalysisError("Не вдалося отримати відповідь від моделі.")
    return response.parsed_output


def format_analysis(analysis: MealAnalysis) -> str:
    if not analysis.items:
        return f"🤔 Не бачу їжі на фото.\n{html.escape(analysis.comment)}"

    lines = ["🍽 <b>Результат аналізу</b>\n"]
    for item in analysis.items:
        lines.append(
            f"• <b>{html.escape(item.name)}</b> (~{item.weight_g:.0f} г): {item.calories:.0f} ккал\n"
            f"  Б {item.protein_g:.1f} / Ж {item.fat_g:.1f} / В {item.carbs_g:.1f} г"
        )

    total_cal = sum(i.calories for i in analysis.items)
    total_p = sum(i.protein_g for i in analysis.items)
    total_f = sum(i.fat_g for i in analysis.items)
    total_c = sum(i.carbs_g for i in analysis.items)
    lines.append(
        f"\n🔥 <b>Разом: {total_cal:.0f} ккал</b>\n"
        f"Б {total_p:.1f} г / Ж {total_f:.1f} г / В {total_c:.1f} г"
    )
    lines.append(f"\n📊 Впевненість: {html.escape(analysis.confidence)}")
    if analysis.comment:
        lines.append(f"💡 {html.escape(analysis.comment)}")
    return "\n".join(lines)
