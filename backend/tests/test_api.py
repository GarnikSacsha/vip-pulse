"""HTTP API over the persisted triage: what the browser UI reads."""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any, ClassVar

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.analysis.llm import FakeProvider, LLMError
from app.db import init_db, make_engine, session_scope
from app.ingestion.adapters import get_adapter
from app.ingestion.pipeline import ingest
from app.ingestion.store import save_bundle
from app.main import create_app
from app.policy.config import PolicyConfig
from app.tasks.service import run_triage

CFG = PolicyConfig.load()
NOW = datetime(2026, 11, 19, 9, 0, tzinfo=UTC)


class BrokenProvider:
    name: ClassVar[str] = "broken"
    model: ClassVar[str] = "none"
    simulated: ClassVar[bool] = False

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> str:
        raise LLMError("secret-upstream-detail 500 at https://internal")


def _engine(sample_paths, provider=None) -> Engine:
    engine = make_engine("sqlite://")
    init_db(engine)
    for session in session_scope(engine):
        save_bundle(session, ingest(get_adapter("sample_v1"), *sample_paths))
        run_triage(session, provider or FakeProvider(), CFG, now=NOW)
    return engine


@pytest.fixture
def client(sample_paths) -> Iterator[TestClient]:
    with TestClient(create_app(engine=_engine(sample_paths))) as c:
        yield c


def test_meta_reports_provider_and_counts(client: TestClient) -> None:
    body = client.get("/api/meta").json()
    assert body["as_of"] == "2026-11-12T13:00:00Z"
    assert body["provider"] == {
        "name": "fake",
        "model": "heuristic-v1",
        "simulated": True,
        "label": "эвристика fake, без модели",
    }
    assert body["counts"]["total"] == 9
    assert body["counts"]["by_status"] == {
        "open": 5,
        "in_progress": 0,
        "resolved": 0,
        "no_action": 4,
    }
    assert body["counts"]["by_priority"] == {"P0": 3, "P1": 1, "P2": 1, "P3": 4}


def test_queue_is_sorted_by_priority_then_wait(client: TestClient) -> None:
    items = client.get("/api/queue").json()
    assert [i["conversation_id"] for i in items[:3]] == ["d-001", "d-009", "d-004"]
    assert [i["priority"] for i in items] == sorted(i["priority"] for i in items)
    first = items[0]
    assert first["player"] == {
        "player_id": "p-001",
        "display_name": "Demo Player 001",
        "manager_id": "mgr-01",
        "segment": "platinum",
    }
    assert first["category"] == "withdrawal"
    assert first["status"] == "open"
    assert first["channel"] == "telegram"
    assert first["wait_hours"] == 27
    assert first["simulated"] is True
    assert first["reasons"][0]["code"] == "sla.money_critical"


def test_queue_filters(client: TestClient) -> None:
    active = client.get("/api/queue", params={"status": ["open", "in_progress"]}).json()
    assert {i["conversation_id"] for i in active} == {"d-001", "d-004", "d-005", "d-007", "d-009"}
    p0 = client.get("/api/queue", params={"priority": "P0"}).json()
    assert {i["conversation_id"] for i in p0} == {"d-001", "d-004", "d-009"}
    rg = client.get("/api/queue", params={"route": "rg_specialist"}).json()
    assert [i["conversation_id"] for i in rg] == ["d-004"]


def test_queue_rejects_unknown_filter_values(client: TestClient) -> None:
    assert client.get("/api/queue", params={"status": "deleted"}).status_code == 422
    assert client.get("/api/queue", params={"priority": "P9"}).status_code == 422


def test_conversation_detail_marks_evidence(client: TestClient) -> None:
    body = client.get("/api/conversations/d-001").json()
    assert body["conversation_id"] == "d-001"
    assert [m["message_id"] for m in body["messages"]] == ["m-001-1", "m-001-2", "m-001-3"]
    assert [m["is_evidence"] for m in body["messages"]] == [True, False, False]
    assert [m["is_pending"] for m in body["messages"]] == [False, False, True]
    assert body["messages"][0]["sent_at"] == "2026-11-10T09:00:00Z"
    assert body["analysis"]["category"] == "withdrawal"
    assert body["analysis"]["simulated"] is True
    assert body["analysis"]["status"] == "ok"
    assert body["task"]["priority"] == "P0"
    assert body["task"]["status"] == "open"
    assert body["facts"]["response_sla_hours"] == 4
    assert body["player"]["player_id"] == "p-001"


def test_unknown_conversation_is_404(client: TestClient) -> None:
    response = client.get("/api/conversations/nope")
    assert response.status_code == 404
    assert response.json() == {"detail": "conversation not found"}


def test_failed_analysis_does_not_leak_provider_errors(sample_paths) -> None:
    with TestClient(create_app(engine=_engine(sample_paths, BrokenProvider()))) as c:
        body = c.get("/api/conversations/d-001").json()
        assert body["analysis"]["status"] == "failed"
        assert body["analysis"]["category"] is None
        assert "secret-upstream-detail" not in str(body)
        assert body["task"]["requires_review"] is True
        queue = c.get("/api/queue").json()
        assert "secret-upstream-detail" not in str(queue)


def test_empty_database_gives_empty_queue() -> None:
    engine = make_engine("sqlite://")
    init_db(engine)
    with TestClient(create_app(engine=engine)) as c:
        assert c.get("/api/queue").json() == []
        meta = c.get("/api/meta").json()
        assert meta["as_of"] is None
        assert meta["counts"]["total"] == 0
