"""Application settings loaded from environment / backend/.env."""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./vip_pulse.db"
    llm_provider: Literal["fake", "gemini"] = "fake"
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-2.5-flash"
    # Paid-tier list prices of gemini-2.5-flash, USD per 1M tokens (checked 2026-11-19).
    # Change them together with GEMINI_MODEL.
    gemini_price_input_per_m: float = 0.30
    gemini_price_output_per_m: float = 2.50
    gemini_max_output_tokens: int = 2048
    gemini_thinking_budget: int = 0
    # Hard cap on total paid LLM spend, across all runs recorded in the database.
    llm_budget_usd: float = 1.0
    # Parallel LLM calls per triage run (keep low on the free tier: its rate limit is per minute).
    llm_concurrency: int = 4
    policy_path: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
