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
        "country": "DE",
        "registered_at": "2023-04-11",
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


# --- oversight: overdue flag, manager filter, overview aggregates ---------------------------


def test_queue_marks_overdue_only_active_items_past_their_sla(client: TestClient) -> None:
    items = {i["conversation_id"]: i for i in client.get("/api/queue").json()}
    assert {c for c, i in items.items() if i["overdue"]} == {"d-001"}
    # d-003 waits 73 h but needs no action (closing message): not overdue work.
    assert items["d-003"]["awaiting_reply"] is True
    assert items["d-003"]["overdue"] is False
    # d-009 is email: 5.75 h is inside its 8 h SLA.
    assert items["d-009"]["overdue"] is False


def test_queue_filters_by_manager_and_overdue(client: TestClient) -> None:
    mine = client.get("/api/queue", params={"manager": "mgr-02"}).json()
    assert {i["conversation_id"] for i in mine} == {"d-003", "d-004", "d-006", "d-009"}
    late = client.get("/api/queue", params={"overdue": "true"}).json()
    assert [i["conversation_id"] for i in late] == ["d-001"]


def test_overview_totals(client: TestClient) -> None:
    body = client.get("/api/overview").json()
    assert body["as_of"] == "2026-11-12T13:00:00Z"
    assert body["totals"] == {
        "total": 9,
        "active": 5,
        "in_progress": 0,
        "critical": 3,
        "overdue": 1,
        "awaiting_reply": 4,
        "escalated": 2,
        "quality_issues": 1,
        "needs_review": 2,
        "resolved": 0,
        "no_action": 4,
    }


def test_overview_workload_by_manager(client: TestClient) -> None:
    managers = client.get("/api/overview").json()["managers"]
    assert managers == [
        {
            "manager_id": "mgr-01",
            "total": 5,
            "active": 3,
            "in_progress": 0,
            "critical": 1,
            "overdue": 1,
            "oldest_wait_hours": 27.0,
        },
        {
            "manager_id": "mgr-02",
            "total": 4,
            "active": 2,
            "in_progress": 0,
            "critical": 2,
            "overdue": 0,
            "oldest_wait_hours": 5.75,
        },
    ]


def test_overview_breakdowns_and_coverage(client: TestClient) -> None:
    body = client.get("/api/overview").json()
    categories = {c["category"]: (c["total"], c["active"]) for c in body["categories"]}
    assert categories == {
        "withdrawal": (1, 1),
        "account": (1, 1),
        "responsible_gaming": (1, 1),
        "verification": (1, 1),
        "other": (2, 1),
        "general": (1, 0),
        "deposit": (1, 0),
        "technical": (1, 0),
    }
    # Most active first, then by volume.
    assert [c["category"] for c in body["categories"]][-1] in {"general", "deposit", "technical"}
    channels = {c["channel"]: (c["total"], c["active"], c["overdue"]) for c in body["channels"]}
    assert channels == {"telegram": (3, 3, 1), "email": (4, 1, 0), "whatsapp": (2, 1, 0)}
    assert body["routes"] == {"manager": 3, "rg_specialist": 1, "security": 1}
    assert body["coverage"] == {
        "conversations": 9,
        "in_queue": 9,
        "analysed": 9,
        "failed": 0,
        "simulated": 9,
    }


def test_overview_numbers_match_the_queue(client: TestClient) -> None:
    body = client.get("/api/overview").json()
    active = client.get("/api/queue", params={"status": ["open", "in_progress"]}).json()
    assert body["totals"]["active"] == len(active)
    assert sum(m["active"] for m in body["managers"]) == len(active)
    assert sum(c["active"] for c in body["categories"]) == len(active)
    assert sum(body["routes"].values()) == len(active)


def test_overview_counts_failed_analyses(sample_paths) -> None:
    with TestClient(create_app(engine=_engine(sample_paths, BrokenProvider()))) as c:
        body = c.get("/api/overview").json()
    assert body["coverage"] == {
        "conversations": 9,
        "in_queue": 9,
        "analysed": 0,
        "failed": 9,
        "simulated": 0,
    }
    assert {cat["category"] for cat in body["categories"]} == {None}


def test_overview_of_an_empty_database() -> None:
    engine = make_engine("sqlite://")
    init_db(engine)
    with TestClient(create_app(engine=engine)) as c:
        body = c.get("/api/overview").json()
    assert body["as_of"] is None
    assert body["totals"]["total"] == 0
    assert body["managers"] == [] and body["categories"] == [] and body["channels"] == []


def _sla_reason(item: dict) -> bool:
    return any(r["code"] in {"sla.breached", "sla.money_critical"} for r in item["reasons"])


def test_overdue_follows_the_decision_that_set_the_priority(sample_paths) -> None:
    # The API runs with a looser SLA than the triage that set the priorities (e.g. thresholds
    # edited, CLI re-run, API not restarted). "Overdue" must agree with the priority reasons.
    loose = CFG.model_copy(
        update={
            "sla": CFG.sla.model_copy(update={"response_hours": 48, "channel_response_hours": {}})
        }
    )
    with TestClient(create_app(engine=_engine(sample_paths), policy=loose)) as c:
        items = c.get("/api/queue").json()
    assert {i["conversation_id"] for i in items if i["overdue"]} == {"d-001"}
    for item in items:
        active = item["status"] in {"open", "in_progress"}
        assert item["overdue"] == (active and _sla_reason(item)), item["conversation_id"]


def test_coverage_counts_imported_conversations_not_yet_triaged(sample_paths) -> None:
    engine = make_engine("sqlite://")
    init_db(engine)
    for session in session_scope(engine):
        save_bundle(session, ingest(get_adapter("sample_v1"), *sample_paths))
    with TestClient(create_app(engine=engine)) as c:
        coverage = c.get("/api/overview").json()["coverage"]
    assert (coverage["conversations"], coverage["in_queue"]) == (9, 0)


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


# --- SLA lanes (team lead board, pulse indicator) -------------------------------------------


def test_queue_items_carry_sla_hours_and_lane(client: TestClient) -> None:
    items = {i["conversation_id"]: i for i in client.get("/api/queue").json()}
    assert items["d-009"]["sla_hours"] == 8.0  # email override
    assert items["d-001"]["sla_hours"] == 4.0
    assert items["d-001"]["sla_lane"] == "breached"
    assert items["d-003"]["sla_lane"] == "ok"  # waits, but needs no action
    for item in items.values():
        assert (item["sla_lane"] == "breached") == item["overdue"], item["conversation_id"]


# --- player dossier ---------------------------------------------------------------------------


def test_queue_filters_by_player_and_carries_dossier_fields(client: TestClient) -> None:
    items = client.get("/api/queue", params={"player": "p-001"}).json()
    assert {i["conversation_id"] for i in items} == {"d-001", "d-010"}
    player = items[0]["player"]
    assert player["country"] == "DE"
    assert player["registered_at"] == "2023-04-11"
    assert items[0]["sentiment"] in {"positive", "neutral", "negative", "mixed"}


def test_failed_analysis_has_no_sentiment(sample_paths) -> None:
    with TestClient(create_app(engine=_engine(sample_paths, BrokenProvider()))) as c:
        items = c.get("/api/queue").json()
    assert {i["sentiment"] for i in items} == {None}


def test_queue_and_task_expose_alerts(client: TestClient) -> None:
    items = client.get("/api/queue").json()
    assert all(i["alerts"] == [] for i in items)  # the sample has no such case
    detail = client.get("/api/conversations/d-001").json()
    assert detail["task"]["alerts"] == []


def test_winback_lists_candidates_and_filters_by_manager(client: TestClient) -> None:
    body = client.get("/api/winback").json()
    assert isinstance(body, list)
    for item in body:
        assert item["tier"] in {"urgent", "attention", "introduce"}
        assert item["reasons"]
    mine = client.get("/api/winback", params={"manager": "mgr-02"}).json()
    assert all(i["player"]["manager_id"] == "mgr-02" for i in mine)
