"""Persisted triage: analyses are cached, every conversation gets one work item, and the
manager's status survives re-runs unless the player writes again."""

from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.llm import FakeProvider, LLMError
from app.ingestion.adapters import get_adapter
from app.ingestion.pipeline import IngestBundle, ingest
from app.ingestion.store import save_bundle
from app.models import AnalysisRow, AuditRow, TaskRow
from app.policy.config import PolicyConfig
from app.schemas.domain import Message, SenderRole
from app.tasks.service import InvalidTransition, TaskStatus, change_status, run_triage

CFG = PolicyConfig.load()
NOW = datetime(2026, 11, 19, 9, 0, tzinfo=UTC)


class CountingProvider(FakeProvider):
    def __init__(self) -> None:
        self.calls = 0

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> str:
        self.calls += 1
        return super().complete_json(system, user, schema)


class BrokenProvider:
    name: ClassVar[str] = "broken"
    model: ClassVar[str] = "none"
    simulated: ClassVar[bool] = False

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> str:
        raise LLMError("provider unavailable")


@pytest.fixture
def bundle(sample_paths) -> IngestBundle:
    return ingest(get_adapter("sample_v1"), *sample_paths)


@pytest.fixture
def loaded(session: Session, bundle: IngestBundle) -> Session:
    save_bundle(session, bundle)
    return session


def _tasks(session: Session) -> dict[str, TaskRow]:
    return {t.conversation_id: t for t in session.scalars(select(TaskRow))}


def test_first_run_creates_one_task_per_conversation(loaded: Session) -> None:
    summary = run_triage(loaded, FakeProvider(), CFG, now=NOW)

    tasks = _tasks(loaded)
    assert len(tasks) == 9
    assert (summary.analysed, summary.reused, summary.failed) == (9, 0, 0)
    assert summary.created == 9
    open_ids = {cid for cid, t in tasks.items() if t.status == TaskStatus.OPEN}
    assert open_ids == {"d-001", "d-004", "d-005", "d-007", "d-009"}  # P0-P2 need action
    assert tasks["d-002"].status == TaskStatus.NO_ACTION
    assert tasks["d-001"].priority == "P0"
    assert tasks["d-004"].route == "rg_specialist"
    assert tasks["d-004"].quality_flags == ["offer_to_vulnerable_player"]
    assert tasks["d-001"].reasons[0]["code"] == "sla.money_critical"


def test_second_run_reuses_cached_analyses(loaded: Session) -> None:
    provider = CountingProvider()
    run_triage(loaded, provider, CFG, now=NOW)
    assert provider.calls == 9

    summary = run_triage(loaded, provider, CFG, now=NOW)
    assert provider.calls == 9  # nothing changed, nothing re-sent to the provider
    assert (summary.analysed, summary.reused, summary.created) == (0, 9, 0)
    assert len(loaded.scalars(select(AnalysisRow)).all()) == 9


def test_failed_analysis_is_stored_and_retried_next_run(loaded: Session) -> None:
    summary = run_triage(loaded, BrokenProvider(), CFG, now=NOW)
    assert summary.failed == 9
    failed = loaded.scalars(select(AnalysisRow)).all()
    assert all(a.status == "failed" and "provider unavailable" in (a.error or "") for a in failed)
    assert all(t.requires_review for t in _tasks(loaded).values())

    provider = CountingProvider()
    summary = run_triage(loaded, provider, CFG, now=NOW)
    assert provider.calls == 9  # failures are never served from cache
    assert summary.failed == 0


def test_status_changes_are_audited(loaded: Session) -> None:
    run_triage(loaded, FakeProvider(), CFG, now=NOW)
    task = _tasks(loaded)["d-001"]

    change_status(loaded, task.id, TaskStatus.IN_PROGRESS, actor="demo-manager", now=NOW)
    change_status(
        loaded, task.id, TaskStatus.RESOLVED, actor="demo-manager", note="Выплата ушла", now=NOW
    )

    assert task.status == TaskStatus.RESOLVED
    assert task.resolved_at == NOW
    audit = loaded.scalars(select(AuditRow).where(AuditRow.task_id == task.id)).all()
    assert [(a.action, a.before, a.after) for a in audit] == [
        ("status_changed", "open", "in_progress"),
        ("status_changed", "in_progress", "resolved"),
    ]
    assert audit[-1].actor == "demo-manager"
    assert audit[-1].note == "Выплата ушла"


@pytest.mark.parametrize(
    ("start", "target"),
    [
        (TaskStatus.RESOLVED, TaskStatus.IN_PROGRESS),
        (TaskStatus.NO_ACTION, TaskStatus.RESOLVED),
        (TaskStatus.OPEN, TaskStatus.NO_ACTION),
    ],
)
def test_invalid_transitions_are_rejected(loaded: Session, start, target) -> None:
    run_triage(loaded, FakeProvider(), CFG, now=NOW)
    task = _tasks(loaded)["d-001"]
    task.status = start
    with pytest.raises(InvalidTransition):
        change_status(loaded, task.id, target, actor="demo-manager", now=NOW)
    assert task.status == start


def test_unknown_task_is_rejected(loaded: Session) -> None:
    with pytest.raises(LookupError):
        change_status(loaded, 999, TaskStatus.RESOLVED, actor="demo-manager", now=NOW)


def test_resolved_task_survives_rerun(loaded: Session) -> None:
    run_triage(loaded, FakeProvider(), CFG, now=NOW)
    task = _tasks(loaded)["d-001"]
    change_status(loaded, task.id, TaskStatus.RESOLVED, actor="demo-manager", now=NOW)

    run_triage(loaded, FakeProvider(), CFG, now=NOW + timedelta(hours=1))
    assert _tasks(loaded)["d-001"].status == TaskStatus.RESOLVED


def test_new_player_message_reopens_resolved_task(loaded: Session, bundle: IngestBundle) -> None:
    run_triage(loaded, FakeProvider(), CFG, now=NOW)
    task = _tasks(loaded)["d-001"]
    change_status(loaded, task.id, TaskStatus.RESOLVED, actor="demo-manager", now=NOW)

    d001 = next(c for c in bundle.conversations if c.conversation_id == "d-001")
    follow_up = Message(
        message_id="m-001-4",
        conversation_id="d-001",
        sender_role=SenderRole.PLAYER,
        sent_at=d001.last_message_at + timedelta(days=2),
        text="Деньги так и не пришли, где вывод?",
    )
    updated = d001.model_copy(update={"messages": (*d001.messages, follow_up)})
    others = [c for c in bundle.conversations if c.conversation_id != "d-001"]
    save_bundle(loaded, IngestBundle(bundle.players, [*others, updated], bundle.report))

    summary = run_triage(loaded, FakeProvider(), CFG, now=NOW + timedelta(days=2))
    task = _tasks(loaded)["d-001"]
    assert task.status == TaskStatus.OPEN
    assert summary.reopened == 1
    last = loaded.scalars(select(AuditRow).order_by(AuditRow.id.desc())).first()
    assert last is not None
    assert (last.action, last.actor, last.before, last.after) == (
        "reopened",
        "system",
        "resolved",
        "open",
    )
