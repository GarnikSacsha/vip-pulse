"""Persisted triage and task status changes.

`run_triage` analyses every stored conversation (reusing cached provider answers), applies the
policy and keeps exactly one work item per conversation. The manager owns the status: a re-run
updates the decision but never silently closes or reopens work, except when the player writes
again after the work item was closed.
"""

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.llm.base import LLMProvider
from app.analysis.llm.budget import BudgetExceeded, SpendingMeter, meter_of
from app.analysis.service import analysis_key, analyze_conversation
from app.ingestion.store import load_conversations, load_players
from app.models import AnalysisRow, AuditRow, LLMCallRow, TaskRow
from app.policy.config import PolicyConfig
from app.policy.facts import ConversationFacts, compute_facts, dataset_as_of
from app.schemas.analysis import AnalysisOutcome, LLMAnalysis, Priority, ProcessingStatus
from app.schemas.domain import Conversation, Player, SenderRole
from app.triage import TriageItem, triage

SYSTEM_ACTOR = "system"
# One triage run at a time per process: two parallel runs would double-spend the LLM budget.
RUN_LOCK = threading.Lock()


class RunInProgress(RuntimeError):
    pass


class TaskStatus(StrEnum):
    OPEN = "open"  # needs the manager
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"  # closed by a person
    NO_ACTION = "no_action"  # closed by the policy: nothing to do


# NO_ACTION is never a manual target: only the policy decides that nothing is needed.
TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.OPEN: frozenset({TaskStatus.IN_PROGRESS, TaskStatus.RESOLVED}),
    TaskStatus.IN_PROGRESS: frozenset({TaskStatus.OPEN, TaskStatus.RESOLVED}),
    TaskStatus.RESOLVED: frozenset({TaskStatus.OPEN}),
    TaskStatus.NO_ACTION: frozenset({TaskStatus.OPEN}),
}
CLOSED = frozenset({TaskStatus.RESOLVED, TaskStatus.NO_ACTION})


class InvalidTransition(ValueError):
    pass


@dataclass
class RunSummary:
    analysed: int = 0  # fresh provider answers that passed validation
    reused: int = 0  # served from cache
    failed: int = 0
    created: int = 0
    updated: int = 0
    reopened: int = 0
    spent_usd: float = 0.0  # paid LLM spend of this run
    budget_left_usd: float | None = None  # None: the provider is not metered (fake)
    budget_exhausted: bool = False


def ledger_spent(session: Session) -> float:
    """Total paid LLM spend recorded in this database, across all runs."""
    total = session.scalar(select(func.coalesce(func.sum(LLMCallRow.cost_usd), 0.0)))
    return float(total or 0.0)


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(UTC)


def _audit(
    session: Session,
    task: TaskRow,
    action: str,
    before: str | None,
    after: str | None,
    actor: str,
    at: datetime,
    note: str | None = None,
) -> None:
    session.add(
        AuditRow(
            task_id=task.id,
            at=at,
            actor=actor,
            action=action,
            before=before,
            after=after,
            note=note,
        )
    )


class _CachingAnalyzer:
    """Serves the latest successful analysis with the same input hash; stores every new answer."""

    def __init__(self, session: Session, provider: LLMProvider, summary: RunSummary, at: datetime):
        self.session, self.provider, self.summary, self.at = session, provider, summary, at
        self.meter: SpendingMeter | None = meter_of(provider)
        self.analysis_ids: dict[str, int] = {}
        self._fresh: dict[str, AnalysisOutcome] = {}

    def prefetch(
        self,
        conversations: list[Conversation],
        players: dict[str, Player],
        cfg: PolicyConfig,
        workers: int,
    ) -> None:
        """Analyse every conversation without a cached answer, up to `workers` at a time.

        Only provider calls run in threads; the database is touched from this thread alone.
        """
        as_of = dataset_as_of(conversations)
        todo = []
        for conv in conversations:
            player = players.get(conv.player_id)
            facts = compute_facts(conv, as_of, cfg.sla)
            if self._cached(analysis_key(self.provider, conv, player, facts)) is None:
                todo.append((conv, player, facts))
        if not todo:
            return
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = {
                pool.submit(analyze_conversation, self.provider, conv, player, facts): conv
                for conv, player, facts in todo
            }
            for future in as_completed(futures):
                conv = futures[future]
                self._fresh[conv.conversation_id] = self._store(conv, future.result())

    def _cached(self, key: str) -> AnalysisRow | None:
        return self.session.scalars(
            select(AnalysisRow)
            .where(AnalysisRow.input_hash == key, AnalysisRow.status == ProcessingStatus.OK)
            .order_by(AnalysisRow.id.desc())
            .limit(1)
        ).first()

    def _book_usage(self) -> None:
        """Persist billed calls right away, so a crash mid-run cannot hide spend."""
        if self.meter is None:
            return
        for record in self.meter.drain():
            self.session.add(
                LLMCallRow(
                    at=record.at,
                    model=record.model,
                    input_tokens=record.input_tokens,
                    output_tokens=record.output_tokens,
                    cost_usd=record.cost_usd,
                    estimated=record.estimated,
                    outcome=record.outcome,
                )
            )
            self.summary.spent_usd += record.cost_usd

    def __call__(
        self, conv: Conversation, player: Player | None, facts: ConversationFacts
    ) -> AnalysisOutcome:
        if (fresh := self._fresh.pop(conv.conversation_id, None)) is not None:
            return fresh
        key = analysis_key(self.provider, conv, player, facts)
        cached = self._cached(key)
        if cached is not None:
            self.summary.reused += 1
            self.analysis_ids[conv.conversation_id] = cached.id
            return AnalysisOutcome(
                conversation_id=conv.conversation_id,
                status=ProcessingStatus.OK,
                result=LLMAnalysis.model_validate(cached.result),
                model=cached.model,
                input_hash=cached.input_hash,
                simulated=cached.simulated,
            )

        return self._store(conv, analyze_conversation(self.provider, conv, player, facts))

    def _store(self, conv: Conversation, outcome: AnalysisOutcome) -> AnalysisOutcome:
        self._book_usage()
        if (outcome.error or "").startswith(BudgetExceeded.__name__):
            self.summary.budget_exhausted = True
        row = AnalysisRow(
            conversation_id=conv.conversation_id,
            input_hash=outcome.input_hash or "",
            status=outcome.status.value,
            model=outcome.model,
            simulated=outcome.simulated,
            result=outcome.result.model_dump(mode="json") if outcome.result else None,
            error=outcome.error,
            created_at=self.at,
        )
        self.session.add(row)
        self.session.flush()
        self.analysis_ids[conv.conversation_id] = row.id
        if outcome.status == ProcessingStatus.OK:
            self.summary.analysed += 1
        else:
            self.summary.failed += 1
        return outcome


def _player_wrote_since(conv: Conversation, since: datetime) -> bool:
    return any(m.sender_role == SenderRole.PLAYER and m.sent_at > since for m in conv.messages)


def _apply(
    session: Session,
    item: TriageItem,
    analysis_id: int | None,
    summary: RunSummary,
    at: datetime,
) -> None:
    conv, decision, facts = item.conversation, item.decision, item.facts
    needs_action = decision.priority != Priority.P3
    fields = {
        "analysis_id": analysis_id,
        "priority": decision.priority.value,
        "route": decision.route.value,
        "next_action": decision.next_action,
        "reasons": [r.model_dump() for r in decision.reasons],
        "quality_flags": list(decision.quality_flags),
        "requires_review": decision.requires_human_review,
        "suppress_offers": decision.suppress_offers,
        "awaiting_reply": facts.awaiting_reply,
        "wait_hours": facts.wait_hours,
    }

    task = session.scalars(
        select(TaskRow).where(TaskRow.conversation_id == conv.conversation_id)
    ).first()
    if task is None:
        status = TaskStatus.OPEN if needs_action else TaskStatus.NO_ACTION
        task = TaskRow(
            conversation_id=conv.conversation_id,
            status=status.value,
            seen_last_message_at=conv.last_message_at,
            created_at=at,
            updated_at=at,
            **fields,
        )
        session.add(task)
        summary.created += 1
        return

    status = TaskStatus(task.status)
    reopen = needs_action and (
        status == TaskStatus.NO_ACTION
        or (status == TaskStatus.RESOLVED and _player_wrote_since(conv, task.seen_last_message_at))
    )
    if reopen:
        task.status = TaskStatus.OPEN.value
        task.resolved_at = None
        action = "reopened" if status == TaskStatus.RESOLVED else "opened"
        _audit(session, task, action, status.value, TaskStatus.OPEN.value, SYSTEM_ACTOR, at)
        summary.reopened += 1
    for name, value in fields.items():
        setattr(task, name, value)
    task.seen_last_message_at = conv.last_message_at
    task.updated_at = at
    summary.updated += 1


def run_triage(
    session: Session,
    provider: LLMProvider,
    cfg: PolicyConfig,
    *,
    now: datetime | None = None,
    workers: int = 1,
) -> RunSummary:
    """`workers` bounds parallel provider calls; cached conversations are never re-sent."""
    if not RUN_LOCK.acquire(blocking=False):
        raise RunInProgress("a triage run is already in progress")
    try:
        return _run(session, provider, cfg, _now(now), workers)
    finally:
        RUN_LOCK.release()


def _run(
    session: Session, provider: LLMProvider, cfg: PolicyConfig, at: datetime, workers: int
) -> RunSummary:
    summary = RunSummary()
    meter = meter_of(provider)
    if meter is not None:
        # The cap covers every run recorded in the database, not just this process.
        meter.reset_spent(ledger_spent(session))
    conversations = load_conversations(session)
    if conversations:
        players = load_players(session)
        analyzer = _CachingAnalyzer(session, provider, summary, at)
        analyzer.prefetch(conversations, {p.player_id: p for p in players}, cfg, workers)
        items = triage(conversations, players, provider, cfg, analyzer=analyzer)
        for item in items:
            conversation_id = item.conversation.conversation_id
            _apply(session, item, analyzer.analysis_ids.get(conversation_id), summary, at)
        session.commit()
    if meter is not None:
        summary.budget_left_usd = meter.remaining_usd
    return summary


def change_status(
    session: Session,
    task_id: int,
    target: TaskStatus,
    *,
    actor: str,
    note: str | None = None,
    now: datetime | None = None,
) -> TaskRow:
    at = _now(now)
    task = session.get(TaskRow, task_id)
    if task is None:
        raise LookupError(f"task {task_id} not found")
    current = TaskStatus(task.status)
    if target not in TRANSITIONS[current]:
        raise InvalidTransition(f"cannot move a task from {current.value} to {target.value}")
    task.status = target.value
    task.updated_at = at
    task.resolved_at = at if target == TaskStatus.RESOLVED else None
    _audit(session, task, "status_changed", current.value, target.value, actor, at, note)
    session.commit()
    return task
