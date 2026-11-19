"""Persisted triage: analyses are cached, every conversation gets one work item, and the
manager's status survives re-runs unless the player writes again."""

import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.llm import FakeProvider, LLMError
from app.analysis.llm.budget import SpendingMeter
from app.db import init_db, make_engine, session_scope
from app.ingestion.adapters import get_adapter
from app.ingestion.pipeline import IngestBundle, ingest
from app.ingestion.store import save_bundle
from app.models import AnalysisRow, AuditRow, LLMCallRow, RunLeaseRow, TaskRow
from app.policy.config import PolicyConfig
from app.schemas.domain import Message, SenderRole
from app.tasks import service
from app.tasks.service import (
    InvalidTransition,
    RunInProgress,
    TaskStatus,
    change_status,
    run_triage,
)

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


# --- paid providers: spend ledger and budget ----------------------------------------------


class MeteredProvider(FakeProvider):
    """Bills a flat $0.10 per call against its meter, like a paid model would."""

    simulated: ClassVar[bool] = False

    def __init__(self, limit_usd: float) -> None:
        self.meter = SpendingMeter(limit_usd=limit_usd)
        self.calls = 0

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> str:
        self.meter.reserve(0.10)
        self.calls += 1
        self.meter.settle(0.10, model="metered:test", input_tokens=100, cost_usd=0.10)
        return super().complete_json(system, user, schema)


def test_paid_calls_are_written_to_the_ledger(loaded: Session) -> None:
    summary = run_triage(loaded, MeteredProvider(limit_usd=5.0), CFG, now=NOW)
    calls = loaded.scalars(select(LLMCallRow)).all()
    assert len(calls) == 9
    assert all(c.model == "metered:test" and c.cost_usd == pytest.approx(0.10) for c in calls)
    assert summary.spent_usd == pytest.approx(0.90)
    assert summary.budget_left_usd == pytest.approx(4.10)
    assert summary.budget_exhausted is False


def test_exhausted_budget_fails_the_rest_without_calls(loaded: Session) -> None:
    provider = MeteredProvider(limit_usd=0.45)
    summary = run_triage(loaded, provider, CFG, now=NOW)
    assert provider.calls == 4
    assert (summary.analysed, summary.failed) == (4, 5)
    assert summary.budget_exhausted is True
    failed = loaded.scalars(select(AnalysisRow).where(AnalysisRow.status == "failed")).all()
    assert all("BudgetExceeded" in (a.error or "") for a in failed)
    assert len(_tasks(loaded)) == 9  # the queue is still complete, failed items go to review


def test_budget_counts_spend_of_earlier_runs_and_processes(loaded: Session) -> None:
    run_triage(loaded, MeteredProvider(limit_usd=0.45), CFG, now=NOW)
    fresh = MeteredProvider(limit_usd=0.45)  # e.g. after an API restart
    summary = run_triage(loaded, fresh, CFG, now=NOW)
    assert fresh.calls == 0
    assert summary.budget_left_usd == pytest.approx(0.05)


def test_unmetered_provider_reports_no_budget(loaded: Session) -> None:
    summary = run_triage(loaded, FakeProvider(), CFG, now=NOW)
    assert (summary.spent_usd, summary.budget_left_usd, summary.budget_exhausted) == (
        0.0,
        None,
        False,
    )
    assert loaded.scalars(select(LLMCallRow)).all() == []


# --- bounded concurrency -------------------------------------------------------------------


class SlowProvider(FakeProvider):
    """Records how many calls overlap, to prove parallelism and its upper bound."""

    def __init__(self) -> None:
        self.in_flight = 0
        self.max_in_flight = 0
        self.calls = 0
        self._lock = threading.Lock()

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> str:
        with self._lock:
            self.calls += 1
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
        time.sleep(0.05)
        with self._lock:
            self.in_flight -= 1
        return super().complete_json(system, user, schema)


def test_fresh_analyses_run_in_parallel_up_to_the_limit(loaded: Session) -> None:
    provider = SlowProvider()
    summary = run_triage(loaded, provider, CFG, now=NOW, workers=3)
    assert provider.calls == 9
    assert 2 <= provider.max_in_flight <= 3
    assert summary.analysed == 9


def test_parallel_run_gives_the_same_queue_as_sequential(
    session: Session, bundle: IngestBundle, sample_paths
) -> None:
    save_bundle(session, bundle)
    run_triage(session, FakeProvider(), CFG, now=NOW, workers=1)
    sequential = {c: (t.priority, t.route, t.status) for c, t in _tasks(session).items()}

    engine = make_engine("sqlite://")
    init_db(engine)
    for other in session_scope(engine):
        save_bundle(other, bundle)
        run_triage(other, SlowProvider(), CFG, now=NOW, workers=4)
        parallel = {c: (t.priority, t.route, t.status) for c, t in _tasks(other).items()}
    assert parallel == sequential


def test_cached_conversations_are_not_sent_to_the_pool(loaded: Session) -> None:
    run_triage(loaded, FakeProvider(), CFG, now=NOW)
    provider = SlowProvider()
    summary = run_triage(loaded, provider, CFG, now=NOW, workers=4)
    assert provider.calls == 0
    assert summary.reused == 9


# --- review fixes: durable ledger, cross-process lease, cancellation ------------------------


def test_spend_survives_a_crash_later_in_the_run(
    loaded: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("bug after analysis")

    monkeypatch.setattr(service, "_apply", boom)
    with pytest.raises(RuntimeError):
        run_triage(loaded, MeteredProvider(limit_usd=5.0), CFG, now=NOW)
    loaded.rollback()
    assert len(loaded.scalars(select(LLMCallRow)).all()) == 9
    assert service.ledger_spent(loaded) == pytest.approx(0.90)


def test_run_held_by_another_process_is_rejected(loaded: Session) -> None:
    loaded.add(RunLeaseRow(id=1, holder="pid-other", started_at=datetime.now(UTC)))
    loaded.commit()
    with pytest.raises(RunInProgress):
        run_triage(loaded, FakeProvider(), CFG, now=NOW)


def test_stale_lease_of_a_dead_process_is_taken_over(loaded: Session) -> None:
    started = datetime.now(UTC) - timedelta(hours=2)
    loaded.add(RunLeaseRow(id=1, holder="pid-dead", started_at=started))
    loaded.commit()
    assert run_triage(loaded, FakeProvider(), CFG, now=NOW).analysed == 9
    assert loaded.scalars(select(RunLeaseRow)).all() == []  # released after the run


def test_error_during_parallel_stage_cancels_queued_calls(
    loaded: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(self: Any, conv: Any, outcome: Any) -> Any:
        raise KeyboardInterrupt

    monkeypatch.setattr(service._CachingAnalyzer, "_store", boom)
    provider = SlowProvider()
    with pytest.raises(KeyboardInterrupt):
        run_triage(loaded, provider, CFG, now=NOW, workers=1)
    assert provider.calls <= 2


def test_unsaved_spend_of_an_earlier_crash_is_saved_next_run(loaded: Session) -> None:
    provider = MeteredProvider(limit_usd=5.0)
    provider.meter.settle(0.0, model="metered:test", cost_usd=0.20)  # booked, never saved
    summary = run_triage(loaded, provider, CFG, now=NOW)
    assert service.ledger_spent(loaded) == pytest.approx(1.10)
    assert summary.spent_usd == pytest.approx(0.90)
