"""LLM providers behind one small interface, so the model can be swapped by config."""

from app.analysis.llm.base import LLMError, LLMProvider
from app.analysis.llm.fake import FakeProvider
from app.config import Settings

__all__ = ["FakeProvider", "LLMError", "LLMProvider", "get_provider"]


def get_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "fake":
        return FakeProvider()
    raise LLMError(
        f"LLM provider {settings.llm_provider!r} is not implemented yet "
        "(Gemini adapter is planned for stage 2); use LLM_PROVIDER=fake"
    )
