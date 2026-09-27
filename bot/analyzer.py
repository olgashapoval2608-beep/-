"""Усі звернення до ШІ (Gemini або Claude): фото, текст, поради, питання коучу."""

import base64
import html
import logging

import httpx
from pydantic import BaseModel, Field

from bot.config import AI_PROVIDER, CLAUDE_MODEL, GEMINI_MODEL

logger = logging.getLogger(__name__)

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
    """Помилка, текст якої можна показати користувачу."""


RATE_LIMIT_MSG = "Забагато запитів до ШІ. Зачекай хвилинку і спробуй ще раз."
SERVICE_MSG = "Сервіс ШІ тимчасово недоступний. Спробуй пізніше."


# --- Google Gemini (безкоштовний тариф) -----------------------------------------

_gemini_client = None


def _gemini():
    global _gemini_client
    if _gemini_client is None:
        from google import genai
        _gemini_client = genai.Client()  # ключ береться з GEMINI_API_KEY
    return _gemini_client


async def _gemini_call(system: str, parts: list, schema: type[BaseModel] | None):
    from google.genai import errors, types

    config = types.GenerateContentConfig(
        system_instruction=system,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    if schema is not None:
        config.response_mime_type = "application/json"
        config.response_schema = schema
    try:
        return await _gemini().aio.models.generate_content(
            model=GEMINI_MODEL, contents=parts, config=config)
    except errors.APIError as e:
        if e.code == 429:
            raise AnalysisError(RATE_LIMIT_MSG) from e
        if e.code == 404:
            logger.error("Gemini model %s not found", GEMINI_MODEL)
            raise AnalysisError(f"Модель {GEMINI_MODEL} недоступна — зміни GEMINI_MODEL у .env") from e
        logger.exception("Gemini API error %s", e.code)
        raise AnalysisError(SERVICE_MSG) from e
    except httpx.HTTPError as e:
        logger.exception("Gemini connection error")
        raise AnalysisError(SERVICE_MSG) from e


async def _gemini_analyze(image: tuple[bytes, str] | None, text: str) -> MealAnalysis:
    from google.genai import types

    parts: list = []
    if image:
        parts.append(types.Part.from_bytes(data=image[0], mime_type=image[1]))
    parts.append(text)
    response = await _gemini_call(ANALYSIS_PROMPT, parts, MealAnalysis)
    if isinstance(response.parsed, MealAnalysis):
        return response.parsed
    try:
        return MealAnalysis.model_validate_json(response.text or "")
    except ValueError as e:
        raise AnalysisError("Не вдалося розібрати відповідь ШІ. Спробуй ще раз.") from e


async def _gemini_chat(system: str, prompt: str) -> str:
    response = await _gemini_call(system, [prompt], None)
    text = (response.text or "").strip()
    if not text:
        raise AnalysisError("ШІ не зміг відповісти на це питання.")
    return text


# --- Anthropic Claude (платний, точніший) ---------------------------------------

_claude_client = None


def _claude():
    global _claude_client
    if _claude_client is None:
        import anthropic
        _claude_client = anthropic.AsyncAnthropic()  # ключ береться з ANTHROPIC_API_KEY
    return _claude_client


def _claude_kwargs(effort: str) -> dict:
    kwargs: dict = {}
    # Haiku 4.5 не підтримує adaptive thinking і effort.
    if not CLAUDE_MODEL.startswith("claude-haiku"):
        kwargs["thinking"] = {"type": "adaptive"}
        kwargs["output_config"] = {"effort": effort}
    if CLAUDE_MODEL in FALLBACK_MODELS:
        kwargs["betas"] = ["server-side-fallback-2026-07-01"]
        kwargs["fallbacks"] = "default"
    return kwargs


async def _claude_request(method: str, **params):
    import anthropic

    try:
        response = await getattr(_claude().beta.messages, method)(
            model=CLAUDE_MODEL, max_tokens=16000, **params)
    except anthropic.RateLimitError as e:
        raise AnalysisError(RATE_LIMIT_MSG) from e
    except anthropic.APIStatusError as e:
        logger.exception("Anthropic API error: %s", e.status_code)
        raise AnalysisError(SERVICE_MSG) from e
    except anthropic.APIConnectionError as e:
        logger.exception("Anthropic connection error")
        raise AnalysisError(SERVICE_MSG) from e
    if response.stop_reason == "refusal":
        raise AnalysisError("ШІ відмовився це обробляти.")
    return response


async def _claude_analyze(image: tuple[bytes, str] | None, text: str) -> MealAnalysis:
    content: list[dict] = []
    if image:
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": image[1],
            "data": base64.standard_b64encode(image[0]).decode("utf-8")}})
    content.append({"type": "text", "text": text})
    response = await _claude_request(
        "parse", system=ANALYSIS_PROMPT, output_format=MealAnalysis,
        messages=[{"role": "user", "content": content}], **_claude_kwargs("medium"))
    if response.parsed_output is None:
        raise AnalysisError("Не вдалося отримати відповідь від ШІ.")
    return response.parsed_output


async def _claude_chat(system: str, prompt: str) -> str:
    response = await _claude_request(
        "create", system=system, messages=[{"role": "user", "content": prompt}],
        **_claude_kwargs("low"))
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    if not text:
        raise AnalysisError("ШІ не зміг відповісти на це питання.")
    return text


# --- публічні функції ------------------------------------------------------------

def _analyze(image: tuple[bytes, str] | None, text: str):
    if AI_PROVIDER == "claude":
        return _claude_analyze(image, text)
    return _gemini_analyze(image, text)


def _chat(system: str, prompt: str):
    if AI_PROVIDER == "claude":
        return _claude_chat(system, prompt)
    return _gemini_chat(system, prompt)


async def analyze_photo(image_bytes: bytes, caption: str | None = None,
                        media_type: str = "image/jpeg") -> MealAnalysis:
    text = "Проаналізуй їжу на фото."
    if caption:
        text += f"\nПідпис користувача (використай як уточнення): {caption}"
    return await _analyze((image_bytes, media_type), text)


async def analyze_text(description: str) -> MealAnalysis:
    return await _analyze(None, f"Користувач описав, що зʼїв:\n{description}")


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
