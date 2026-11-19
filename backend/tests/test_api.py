"""HTTP API over the persisted triage: what the browser UI reads."""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any, ClassVar

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.analysis.llm import FakeProvider, LLMError
from app.analysis.llm.budget import SpendingMeter
from app.db import init_db, make_engine, session_scope
from app.ingestion.adapters import get_adapter
from app.ingestion.pipeline import ingest
from app.ingestion.store import save_bundle
from app.main import create_app
from app.policy.config import PolicyConfig
from app.tasks.service import RUN_LOCK, run_triage

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
        "budget_usd": None,
        "spent_usd": None,
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


# --- writes ---------------------------------------------------------------------------------


def _task_id(client: TestClient, conversation_id: str) -> int:
    return client.get(f"/api/conversations/{conversation_id}").json()["task"]["task_id"]


def test_status_change_is_saved_and_audited(client: TestClient) -> None:
    task_id = _task_id(client, "d-001")
    response = client.patch(
        f"/api/tasks/{task_id}",
        json={"status": "in_progress", "actor": "demo-manager", "note": "Пишу в платёжный отдел"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"
    assert client.get("/api/conversations/d-001").json()["task"]["status"] == "in_progress"

    audit = client.get(f"/api/tasks/{task_id}/audit").json()
    assert [(a["action"], a["before"], a["after"], a["actor"]) for a in audit] == [
        ("status_changed", "open", "in_progress", "demo-manager")
    ]
    assert audit[0]["note"] == "Пишу в платёжный отдел"


def test_invalid_transition_is_409(client: TestClient) -> None:
    task_id = _task_id(client, "d-002")  # no_action
    response = client.patch(f"/api/tasks/{task_id}", json={"status": "resolved"})
    assert response.status_code == 409
    assert response.json() == {"detail": "cannot move a task from no_action to resolved"}


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "deleted"},
        {"status": "open", "note": "x" * 501},
        {"status": "open", "actor": ""},
        {"status": "open", "unexpected": True},
    ],
)
def test_invalid_payload_is_422(client: TestClient, payload: dict) -> None:
    task_id = _task_id(client, "d-001")
    assert client.patch(f"/api/tasks/{task_id}", json=payload).status_code == 422


def test_unknown_task_is_404(client: TestClient) -> None:
    assert client.patch("/api/tasks/999", json={"status": "open"}).status_code == 404
    assert client.get("/api/tasks/999/audit").status_code == 404


def test_triage_can_be_rerun_from_the_api(client: TestClient) -> None:
    body = client.post("/api/triage/run").json()
    assert body == {
        "analysed": 0,
        "reused": 9,
        "failed": 0,
        "created": 0,
        "updated": 9,
        "reopened": 0,
        "spent_usd": 0.0,
        "budget_left_usd": None,
        "budget_exhausted": False,
    }


def test_concurrent_triage_run_is_rejected(client: TestClient) -> None:
    with RUN_LOCK:
        response = client.post("/api/triage/run")
    assert response.status_code == 409
    assert client.post("/api/triage/run").status_code == 200


class MeteredProvider(FakeProvider):
    simulated: ClassVar[bool] = False

    def __init__(self) -> None:
        self.meter = SpendingMeter(limit_usd=1.0)

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> str:
        self.meter.reserve(0.01)
        self.meter.settle(0.01, model="metered:test", cost_usd=0.01)
        return super().complete_json(system, user, schema)


def test_meta_reports_budget_of_a_paid_provider(sample_paths) -> None:
    provider = MeteredProvider()
    app = create_app(engine=_engine(sample_paths, provider), provider=provider)
    with TestClient(app) as c:
        info = c.get("/api/meta").json()["provider"]
    assert info["budget_usd"] == 1.0
    assert info["spent_usd"] == pytest.approx(0.09)
