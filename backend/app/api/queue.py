"""Read endpoints: dataset meta, the work queue and one conversation in detail."""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.analysis.llm import LLMProvider
from app.analysis.llm.budget import meter_of
from app.api.deps import get_policy, get_provider, get_session
from app.api.schemas import (
    AnalysisOut,
    ConversationDetail,
    Counts,
    FactsOut,
    MessageOut,
    Meta,
    PlayerOut,
    PlayerProfile,
    ProviderInfo,
    QueueItem,
    ReasonOut,
    RuleErrorOut,
)
from app.api.tasks import alerts_of
from app.api.tasks import task_out as to_task_out
from app.ingestion.store import load_conversation, to_domain
from app.models import AnalysisRow, ConversationRow, PlayerRow, TaskRow
from app.policy.config import PolicyConfig
from app.policy.facts import compute_facts, late_replies
from app.policy.priority import LABEL_MODEL, LABEL_SIMULATED, Route
from app.policy.sla import ReplyState, reply_state, sla_lane
from app.schemas.analysis import ManagerError, Priority, ProcessingStatus
from app.schemas.domain import Conversation, SenderRole
from app.tasks.service import TaskStatus, ledger_spent

router = APIRouter(prefix="/api", tags=["queue"])

SessionDep = Annotated[Session, Depends(get_session)]
FAILED_ANALYSIS_MESSAGE = "Автоматический разбор не выполнен. Проверьте переписку вручную."


def _label(simulated: bool) -> str:
    return LABEL_SIMULATED if simulated else LABEL_MODEL


def _as_of(session: Session) -> datetime | None:
    return session.scalar(select(func.max(ConversationRow.last_message_at)))


def _player(row: PlayerRow) -> PlayerOut:
    return PlayerOut(
        player_id=row.player_id,
        display_name=row.display_name,
        manager_id=row.manager_id,
        segment=row.segment,
        country=row.attributes.get("country") if row.attributes else None,
        registered_at=row.attributes.get("registered_at") if row.attributes else None,
        profile=_profile(row.attributes or {}),
    )


def _profile(attrs: dict[str, Any]) -> PlayerProfile:
    """Typed profile from the attributes an adapter kept. A value that does not parse is None."""
    values: dict[str, Any] = {}
    for name, field in PlayerProfile.model_fields.items():
        raw = attrs.get(name)
        text = str(raw).strip() if raw is not None else ""
        if not text:
            continue
        if field.annotation == float | None:
            values[name] = _to_number(text)
        elif field.annotation == int | None:
            number = _to_number(text)
            values[name] = int(number) if number is not None and number.is_integer() else None
        else:
            values[name] = text
    return PlayerProfile(**values)


def _to_number(text: str) -> float | None:
    try:
        return float(text.replace(" ", "").replace(",", "."))
    except ValueError:
        return None


def _result(analysis: AnalysisRow | None) -> dict[str, Any]:
    if analysis is None or analysis.status != ProcessingStatus.OK or not analysis.result:
        return {}
    return analysis.result


@router.get("/meta", response_model=Meta)
def meta(session: SessionDep, provider: Annotated[LLMProvider, Depends(get_provider)]) -> Meta:
    by_status = dict.fromkeys(TaskStatus, 0)
    by_priority = dict.fromkeys(Priority, 0)
    rows = session.execute(
        select(TaskRow.status, TaskRow.priority, func.count()).group_by(
            TaskRow.status, TaskRow.priority
        )
    )
    for status, priority, count in rows:
        by_status[TaskStatus(status)] += count
        by_priority[Priority(priority)] += count
    meter = meter_of(provider)
    return Meta(
        as_of=_as_of(session),
        provider=ProviderInfo(
            name=provider.name,
            model=provider.model,
            simulated=provider.simulated,
            label=_label(provider.simulated),
            budget_usd=meter.limit_usd if meter else None,
            spent_usd=ledger_spent(session) if meter else None,
        ),
        counts=Counts(total=sum(by_status.values()), by_status=by_status, by_priority=by_priority),
        managers=list(
            session.scalars(
                select(PlayerRow.manager_id)
                .where(PlayerRow.manager_id.is_not(None))
                .distinct()
                .order_by(PlayerRow.manager_id)
            )
        ),
    )


@router.get("/queue", response_model=list[QueueItem])
def queue(
    session: SessionDep,
    policy: Annotated[PolicyConfig, Depends(get_policy)],
    status: Annotated[list[TaskStatus] | None, Query()] = None,
    priority: Annotated[list[Priority] | None, Query()] = None,
    route: Annotated[list[Route] | None, Query()] = None,
    manager: Annotated[list[str] | None, Query(max_length=64)] = None,
    player: Annotated[list[str] | None, Query(max_length=64)] = None,
    overdue: bool | None = None,
) -> list[QueueItem]:
    return list_queue(
        session,
        policy=policy,
        status=status,
        priority=priority,
        route=route,
        manager=manager,
        player=player,
        overdue=overdue,
    )


ACTIVE = frozenset({TaskStatus.OPEN, TaskStatus.IN_PROGRESS})


# Reasons the policy gives when the player waits past the SLA. Reading them, instead of comparing
# the stored wait with today's thresholds, keeps "overdue" in step with the priority it explains.
SLA_BREACH_REASONS = frozenset({"sla.breached", "sla.money_critical"})


def task_reply_state(task: TaskRow) -> ReplyState:
    """Who owes the next message: the one source for waits, lanes and overdue counts (0017)."""
    return reply_state(
        awaiting_reply=task.awaiting_reply,
        reply_needed=not any(r.get("code") == "sla.no_reply_needed" for r in task.reasons),
        escalated=task.route != Route.MANAGER,
    )


def is_overdue(task: TaskRow) -> bool:
    """Active work where the manager owes a reply past the channel's SLA («Горит»).

    Escalated cases are counted in «У специалиста», not here.
    """
    return (
        TaskStatus(task.status) in ACTIVE
        and task_reply_state(task) == ReplyState.MANAGER
        and any(r.get("code") in SLA_BREACH_REASONS for r in task.reasons)
    )


def _manager_errors(result: dict[str, Any]) -> list[ManagerError]:
    """Mistakes stored with the analysis. Older analyses (before prompt v4) have none."""
    return [ManagerError.model_validate(e) for e in result.get("manager_errors") or []]


def _rule_errors(
    conv: Conversation, task: TaskRow, late: bool, policy: PolicyConfig
) -> list[RuleErrorOut]:
    """Mistakes code counts: late answers in the history, and a player waiting past the SLA now."""
    found = [
        RuleErrorOut(
            code="late_reply",
            evidence_message_ids=[r.player_message_id, r.manager_message_id],
            hours=r.hours,
        )
        for r in late_replies(conv, policy.sla)
    ]
    if late:
        human = [m for m in conv.messages if m.sender_role != SenderRole.SYSTEM]
        pending = []
        for m in reversed(human):
            if m.sender_role != SenderRole.PLAYER:
                break
            pending.append(m.message_id)
        if pending:
            found.append(
                RuleErrorOut(
                    code="waiting_past_sla",
                    evidence_message_ids=[pending[-1]],
                    hours=round(task.wait_hours or 0.0, 1),
                )
            )
    return found


def list_queue(
    session: Session,
    *,
    policy: PolicyConfig,
    status: list[TaskStatus] | None = None,
    priority: list[Priority] | None = None,
    route: list[Route] | None = None,
    manager: list[str] | None = None,
    player: list[str] | None = None,
    overdue: bool | None = None,
) -> list[QueueItem]:
    """The work queue, shared by the API, the oversight views and the CLI."""
    sla = policy.sla
    query = (
        select(TaskRow, ConversationRow, PlayerRow, AnalysisRow)
        .join(ConversationRow, ConversationRow.conversation_id == TaskRow.conversation_id)
        .join(PlayerRow, PlayerRow.player_id == ConversationRow.player_id)
        .outerjoin(AnalysisRow, AnalysisRow.id == TaskRow.analysis_id)
        .options(selectinload(ConversationRow.messages))
    )
    if status:
        query = query.where(TaskRow.status.in_([s.value for s in status]))
    if priority:
        query = query.where(TaskRow.priority.in_([p.value for p in priority]))
    if route:
        query = query.where(TaskRow.route.in_([r.value for r in route]))
    if manager:
        query = query.where(PlayerRow.manager_id.in_(manager))
    if player:
        query = query.where(PlayerRow.player_id.in_(player))
    # Most urgent first; within a priority, the longest wait first.
    query = query.order_by(
        TaskRow.priority, TaskRow.wait_hours.desc().nulls_last(), TaskRow.conversation_id
    )

    items = []
    for task, conv, player, analysis in session.execute(query):
        late = is_overdue(task)
        if overdue is not None and late != overdue:
            continue
        result = _result(analysis)
        sla_hours = sla.response_hours_for(conv.channel)
        state = task_reply_state(task)
        waiting = state in (ReplyState.MANAGER, ReplyState.SPECIALIST)
        items.append(
            QueueItem(
                task_id=task.id,
                conversation_id=conv.conversation_id,
                player=_player(player),
                channel=conv.channel,
                status=task.status,
                priority=task.priority,
                route=task.route,
                category=result.get("category"),
                sentiment=result.get("sentiment"),
                summary=result.get("summary"),
                next_action=task.next_action,
                wait_hours=task.wait_hours if waiting else None,
                awaiting_reply=waiting,
                reply_state=state,
                overdue=late,
                sla_hours=sla_hours,
                sla_lane=sla_lane(
                    active=TaskStatus(task.status) in ACTIVE,
                    awaiting_reply=task.awaiting_reply,
                    wait_hours=task.wait_hours,
                    sla_hours=sla_hours,
                    breached=late,
                    at_risk_share=sla.at_risk_share,
                    reply_needed=not any(
                        r.get("code") == "sla.no_reply_needed" for r in task.reasons
                    ),
                    escalated=task.route != Route.MANAGER,
                ),
                alerts=alerts_of(task),
                requires_review=task.requires_review,
                quality_flags=task.quality_flags,
                manager_errors=_manager_errors(result),
                rule_errors=_rule_errors(to_domain(conv), task, late, policy),
                reasons=[ReasonOut(**r) for r in task.reasons],
                last_message_at=conv.last_message_at,
                simulated=bool(analysis and analysis.simulated),
            )
        )
    return items


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def conversation_detail(
    conversation_id: str,
    session: SessionDep,
    policy: Annotated[PolicyConfig, Depends(get_policy)],
) -> ConversationDetail:
    conv = load_conversation(session, conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    player = session.get(PlayerRow, conv.player_id)
    assert player is not None  # enforced by the foreign key
    task = session.scalars(
        select(TaskRow).where(TaskRow.conversation_id == conversation_id)
    ).first()
    analysis = session.get(AnalysisRow, task.analysis_id) if task and task.analysis_id else None

    as_of = _as_of(session) or conv.last_message_at
    facts = compute_facts(conv, as_of, policy.sla)
    result = _result(analysis)
    errors = _manager_errors(result)
    evidence = set(result.get("evidence_message_ids", []))
    evidence.update(i for e in errors for i in e.evidence_message_ids)
    state = task_reply_state(task) if task is not None else None
    owed = facts.awaiting_reply if state is None else state != ReplyState.NO_REPLY_NEEDED
    pending = set(facts.pending_message_ids) if owed else set()

    analysis_out = None
    if analysis is not None:
        ok = analysis.status == ProcessingStatus.OK
        analysis_out = AnalysisOut(
            status=analysis.status,
            category=result.get("category"),
            sentiment=result.get("sentiment"),
            urgency=result.get("urgency"),
            summary=result.get("summary"),
            confidence=result.get("confidence"),
            safety_flag=result.get("safety_flag"),
            needs_escalation=result.get("needs_escalation"),
            manager_errors=errors,
            model=analysis.model,
            simulated=analysis.simulated,
            label=_label(analysis.simulated),
            message=None if ok else FAILED_ANALYSIS_MESSAGE,
        )

    task_out = to_task_out(task) if task is not None else None

    return ConversationDetail(
        conversation_id=conv.conversation_id,
        channel=conv.channel,
        player=_player(player),
        messages=[
            MessageOut(
                message_id=m.message_id,
                sender_role=m.sender_role,
                sent_at=m.sent_at,
                text=m.text,
                is_evidence=m.message_id in evidence,
                is_pending=m.message_id in pending,
            )
            for m in conv.messages
        ],
        analysis=analysis_out,
        task=task_out,
        facts=FactsOut(
            as_of=facts.as_of,
            awaiting_reply=facts.awaiting_reply and owed,
            wait_hours=facts.wait_hours if owed else None,
            response_sla_hours=facts.response_sla_hours,
            sla_breached=facts.sla_breached and owed,
            reply_state=state,
            raw_wait_hours=facts.wait_hours,
            median_response_minutes=facts.median_response_minutes,
        ),
    )
