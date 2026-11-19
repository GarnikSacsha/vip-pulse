from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.db import init_db, make_engine, session_scope

SAMPLE_DIR = Path(__file__).resolve().parents[2] / "data" / "sample"


@pytest.fixture
def sample_paths() -> tuple[Path, Path]:
    return SAMPLE_DIR / "players.csv", SAMPLE_DIR / "dialogs.json"


@pytest.fixture
def session() -> Iterator[Session]:
    engine = make_engine("sqlite://")
    init_db(engine)
    yield from session_scope(engine)
    engine.dispose()
