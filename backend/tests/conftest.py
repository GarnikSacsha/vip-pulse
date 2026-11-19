from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import init_db, make_engine, session_scope

SAMPLE_DIR = Path(__file__).resolve().parents[2] / "data" / "sample"


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Never read backend/.env in tests: it may switch on a paid provider with a real key."""
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    for name in (
        "LLM_PROVIDER",
        "GEMINI_API_KEY",
        "GEMINI_MODEL",
        "DATABASE_URL",
        "LLM_BUDGET_USD",
    ):
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def sample_paths() -> tuple[Path, Path]:
    return SAMPLE_DIR / "players.csv", SAMPLE_DIR / "dialogs.json"


@pytest.fixture
def session() -> Iterator[Session]:
    engine = make_engine("sqlite://")
    init_db(engine)
    yield from session_scope(engine)
    engine.dispose()
