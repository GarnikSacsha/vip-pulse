"""Tests use code defaults, never the developer's backend/.env (it may hold a real key)."""

from app.config import Settings, get_settings


def test_tests_never_read_the_local_env_file() -> None:
    assert get_settings().llm_provider == "fake"
    assert Settings().gemini_api_key is None


def test_defaults_target_a_model_open_to_new_users() -> None:
    # gemini-2.5-flash answers HTTP 404 "no longer available to new users" (2026-11-19).
    s = Settings()
    assert s.gemini_model == "gemini-3.8-flash"
    assert (s.gemini_price_input_per_m, s.gemini_price_output_per_m) == (0.75, 3.75)
