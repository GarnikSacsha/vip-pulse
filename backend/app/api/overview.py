"""Oversight aggregates for the team lead and the head of VIP.

Everything is computed from the same work queue the managers see, so a number on an oversight
screen always matches the list behind it. Nothing is estimated or hard-coded.
"""

from collections import Counter, defaultdict
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.api.deps import get_policy
from app.api.queue import ACTIVE, SessionDep, _as_of, list_queue
from app.api.schemas import (
    CategoryCount,
    ChannelCount,
    Coverage,
    ManagerLoad,
    Overview,
    OverviewTotals,
    QueueItem,
)
from app.models import AnalysisRow, ConversationRow, TaskRow
from app.policy.config import PolicyConfig
from app.policy.priority import Route
from app.schemas.analysis import Priority, ProcessingStatus
from app.tasks.service import TaskStatus

router = APIRouter(prefix="/api", tags=["oversight"])


def _active(item: QueueItem) -> bool:
    return item.status in ACTIVE


def _totals(items: list[QueueItem]) -> OverviewTotals:
    active = [i for i in items if _active(i)]
    return OverviewTotals(
        total=len(items),
        active=len(active),
        in_progress=sum(i.status == TaskStatus.IN_PROGRESS for i in items),
        critical=sum(i.priority == Priority.P0 for i in active),
        overdue=sum(i.overdue for i in active),
        awaiting_reply=sum(i.awaiting_reply for i in active),
        escalated=sum(i.route != Route.MANAGER for i in active),
        # Mistakes are about how a contact went, so closed conversations count too.
        quality_issues=sum(bool(i.quality_flags or i.manager_errors) for i in items),
        needs_review=sum(i.requires_review for i in active),
        resolved=sum(i.status == TaskStatus.RESOLVED for i in items),
        no_action=sum(i.status == TaskStatus.NO_ACTION for i in items),
    )


def _managers(items: list[QueueItem]) -> list[ManagerLoad]:
    groups: dict[str | None, list[QueueItem]] = defaultdict(list)
    for item in items:
        groups[item.player.manager_id].append(item)
    loads = []
    for manager_id, group in groups.items():
        active = [i for i in group if _active(i)]
        waits = [i.wait_hours for i in active if i.awaiting_reply and i.wait_hours is not None]
        loads.append(
            ManagerLoad(
                manager_id=manager_id,
                total=len(group),
                active=len(active),
                in_progress=sum(i.status == TaskStatus.IN_PROGRESS for i in group),
                critical=sum(i.priority == Priority.P0 for i in active),
                overdue=sum(i.overdue for i in active),
                oldest_wait_hours=max(waits) if waits else None,
                errors=sum(len(i.quality_flags) + len(i.manager_errors) for i in group),
            )
        )
    # Players without a manager last: they are the gap the lead must close.
    return sorted(loads, key=lambda m: (m.manager_id is None, m.manager_id or ""))


def _categories(items: list[QueueItem]) -> list[CategoryCount]:
    total = Counter(i.category for i in items)
    active = Counter(i.category for i in items if _active(i))
    counts = [CategoryCount(category=c, total=n, active=active[c]) for c, n in total.items()]
    return sorted(counts, key=lambda c: (-c.active, -c.total, c.category or "~"))


def _channels(items: list[QueueItem]) -> list[ChannelCount]:
    groups: dict[str, list[QueueItem]] = defaultdict(list)
    for item in items:
        groups[item.channel].append(item)
    counts = [
        ChannelCount(
            channel=channel,
            total=len(group),
            active=sum(_active(i) for i in group),
            overdue=sum(i.overdue for i in group),
        )
        for channel, group in groups.items()
    ]
    return sorted(counts, key=lambda c: (-c.active, -c.total, c.channel))


@router.get("/overview", response_model=Overview)
def overview(session: SessionDep, policy: Annotated[PolicyConfig, Depends(get_policy)]) -> Overview:
    items = list_queue(session, policy=policy)
    statuses = dict(
        session.execute(
            select(AnalysisRow.status, func.count())
            .join(TaskRow, TaskRow.analysis_id == AnalysisRow.id)
            .group_by(AnalysisRow.status)
        ).all()
    )
    simulated = session.scalar(
        select(func.count())
        .select_from(TaskRow)
        .join(AnalysisRow, TaskRow.analysis_id == AnalysisRow.id)
        .where(AnalysisRow.simulated.is_(True), AnalysisRow.status == ProcessingStatus.OK.value)
    )
    routes = dict.fromkeys(Route, 0)
    for item in items:
        if _active(item):
            routes[item.route] += 1
    return Overview(
        as_of=_as_of(session),
        totals=_totals(items),
        managers=_managers(items),
        categories=_categories(items),
        channels=_channels(items),
        routes=routes,
        coverage=Coverage(
            conversations=session.scalar(select(func.count()).select_from(ConversationRow)) or 0,
            in_queue=len(items),
            analysed=statuses.get(ProcessingStatus.OK.value, 0),
            failed=statuses.get(ProcessingStatus.FAILED.value, 0),
            simulated=simulated or 0,
        ),
    )
