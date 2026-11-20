"""Write endpoints: task status changes with audit, and re-running triage."""

from dataclasses import asdict
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.llm import LLMProvider
from app.api.deps import get_policy, get_provider, get_session, require_json
from app.api.schemas import ReasonOut, TaskOut
from app.config import get_settings
from app.models import AuditRow, TaskRow
from app.policy.config import PolicyConfig
from app.tasks.service import (
    InvalidTransition,
    RunInProgress,
    TaskStatus,
    change_status,
    run_triage,
)

router = APIRouter(prefix="/api", tags=["tasks"])

SessionDep = Annotated[Session, Depends(get_session)]


class StatusChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: TaskStatus
    # No authentication in the MVP: the actor is a demo role chosen in the UI, not an identity.
    actor: str = Field(default="demo-manager", min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=500)


class AuditOut(BaseModel):
    at: datetime
    actor: str
    action: str
    before: str | None
    after: str | None
    note: str | None


class RunSummaryOut(BaseModel):
    analysed: int
    reused: int
    failed: int
    created: int
    updated: int
    reopened: int
    spent_usd: float  # paid LLM spend of this run
    budget_left_usd: float | None  # None when the provider is not metered (fake)
    budget_exhausted: bool  # some conversations were not analysed: spending limit reached


def alerts_of(task: TaskRow) -> list[str]:
    """Alert names from the stored reasons ("alert.multi_account" -> "multi_account")."""
    return [
        r["code"].removeprefix("alert.")
        for r in task.reasons
        if r.get("code", "").startswith("alert.")
    ]


def task_out(task: TaskRow) -> TaskOut:
    return TaskOut(
        task_id=task.id,
        status=task.status,
        priority=task.priority,
        route=task.route,
        next_action=task.next_action,
        reasons=[ReasonOut(**r) for r in task.reasons],
        quality_flags=task.quality_flags,
        alerts=alerts_of(task),
        requires_review=task.requires_review,
        suppress_offers=task.suppress_offers,
        updated_at=task.updated_at,
        resolved_at=task.resolved_at,
    )


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def update_task(task_id: int, change: StatusChange, session: SessionDep) -> TaskOut:
    try:
        task = change_status(session, task_id, change.status, actor=change.actor, note=change.note)
    except LookupError:
        raise HTTPException(status_code=404, detail="task not found") from None
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return task_out(task)


@router.get("/tasks/{task_id}/audit", response_model=list[AuditOut])
def task_audit(task_id: int, session: SessionDep) -> list[AuditOut]:
    if session.get(TaskRow, task_id) is None:
        raise HTTPException(status_code=404, detail="task not found")
    rows = session.scalars(
        select(AuditRow).where(AuditRow.task_id == task_id).order_by(AuditRow.id)
    )
    return [
        AuditOut(
            at=r.at, actor=r.actor, action=r.action, before=r.before, after=r.after, note=r.note
        )
        for r in rows
    ]


@router.post("/triage/run", response_model=RunSummaryOut, dependencies=[Depends(require_json)])
def rerun_triage(
    session: SessionDep,
    provider: Annotated[LLMProvider, Depends(get_provider)],
    policy: Annotated[PolicyConfig, Depends(get_policy)],
) -> RunSummaryOut:
    # Cached analyses are reused, so a re-run only calls the provider for changed conversations.
    try:
        summary = run_triage(session, provider, policy, workers=get_settings().llm_concurrency)
    except RunInProgress as exc:
        raise HTTPException(status_code=409, detail="triage is already running") from exc
    return RunSummaryOut(**asdict(summary))
