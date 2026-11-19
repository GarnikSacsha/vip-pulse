"""LLM providers behind one small interface, so the model can be swapped by config."""

from app.analysis.llm.base import LLMError, LLMProvider
from app.analysis.llm.budget import Pricing, SpendingMeter
from app.analysis.llm.fake import FakeProvider
from app.analysis.llm.gemini import GeminiProvider
from app.config import Settings

__all__ = ["FakeProvider", "GeminiProvider", "LLMError", "LLMProvider", "get_provider"]


def get_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "fake":
        return FakeProvider()
    key = settings.gemini_api_key.get_secret_value() if settings.gemini_api_key else ""
    if not key:
        raise LLMError("LLM_PROVIDER=gemini needs GEMINI_API_KEY in backend/.env")
    return GeminiProvider(
        api_key=key,
        model=settings.gemini_model,
        meter=SpendingMeter(limit_usd=settings.llm_budget_usd),
        pricing=Pricing(
            input_per_million=settings.gemini_price_input_per_m,
            output_per_million=settings.gemini_price_output_per_m,
        ),
        max_output_tokens=settings.gemini_max_output_tokens,
        thinking_budget=settings.gemini_thinking_budget,
    )
