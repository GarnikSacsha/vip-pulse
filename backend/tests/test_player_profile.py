"""The player card shows every profile column the source has. Invented fixtures only."""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.analysis.llm import FakeProvider
from app.db import init_db, make_engine, session_scope
from app.ingestion.adapters import get_adapter
from app.ingestion.pipeline import ingest
from app.ingestion.store import save_bundle
from app.main import create_app
from app.policy.config import PolicyConfig
from app.tasks.service import run_triage

FIXTURE = Path(__file__).parent / "fixtures" / "task_v1"
NOW = datetime(2026, 1, 12, 9, tzinfo=UTC)


def _client(adapter: str, players: Path, dialogs: Path) -> TestClient:
    engine = make_engine("sqlite://")
    init_db(engine)
    for session in session_scope(engine):
        save_bundle(session, ingest(get_adapter(adapter), players, dialogs))
        run_triage(session, FakeProvider(), PolicyConfig.load(), now=NOW)
    return TestClient(create_app(engine=engine))


@pytest.fixture
def task_client() -> Iterator[TestClient]:
    with _client("task_v1", FIXTURE / "players.csv", FIXTURE / "dialogs.json") as c:
        yield c


def _player(client: TestClient, player_id: str) -> dict:
    (item,) = client.get("/api/queue", params={"player": player_id}).json()
    return item["player"]


def test_profile_carries_every_task_column(task_client: TestClient) -> None:
    profile = _player(task_client, "T1")["profile"]
    assert profile == {
        "account_status": "active",
        "brand": "ACME",
        "language": "ru",
        "geo": "CIS",
        "deposits_30d_usd": 1000.0,
        "deposits_30d_count": 5,
        "deposits_prev_30d_usd": 900.0,
        "deposits_prev_30d_count": 4,
        "last_deposit_at": "2026-01-10",
        "failed_deposits_7d": 0,
        "withdrawals_30d_usd": 0.0,
        "last_withdrawal_at": None,  # empty in the file: shown as «—», never invented
        "pending_withdrawal_usd": 0.0,
        "bonuses_30d_usd": 0.0,
        "bonuses_30d_count": 0,
        "last_login_at": "2026-01-10",
        "birthday": "1990-01-01",
        "favorite_game": "Demo Slot",
        "deposits_change_pct": 11.1,
        "deposit_drop": False,
    }


def test_restricted_status_reaches_the_card(task_client: TestClient) -> None:
    assert _player(task_client, "T2")["profile"]["account_status"] == "self_excluded"


def test_a_format_without_these_columns_gives_empty_values(sample_paths) -> None:
    with _client("sample_v1", *sample_paths) as client:
        profile = _player(client, "p-002")["profile"]
    assert set(profile.values()) == {None}


def test_deposit_change_and_drop_use_the_threshold() -> None:
    from app.api.queue import _profile

    cfg = PolicyConfig.load()
    drop = _profile({"deposits_30d_usd": "100", "deposits_prev_30d_usd": "1000"}, cfg)
    assert drop.deposits_change_pct == -90.0
    assert drop.deposit_drop is True  # below deposit_drop_share of the previous 30 days
    rise = _profile({"deposits_30d_usd": "1000", "deposits_prev_30d_usd": "900"}, cfg)
    assert rise.deposits_change_pct == 11.1
    assert rise.deposit_drop is False
    assert _profile({"deposits_30d_usd": "5"}, cfg).deposits_change_pct is None
