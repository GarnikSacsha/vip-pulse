"""Response models of the HTTP API: the contract the browser UI is built against."""

from datetime import datetime

from pydantic import BaseModel

from app.policy.priority import Route
from app.schemas.analysis import (
    Category,
    Priority,
    ProcessingStatus,
    SafetyFlag,
    Sentiment,
    Urgency,
)
from app.schemas.domain import Channel, SenderRole
from app.tasks.service import TaskStatus


class ProviderInfo(BaseModel):
    name: str
    model: str
    simulated: bool
    label: str  # shown next to every AI-derived value in the UI


class Counts(BaseModel):
    total: int
    by_status: dict[TaskStatus, int]
    by_priority: dict[Priority, int]


class Meta(BaseModel):
    as_of: datetime | None  # reference "now" of the dataset; None when nothing is imported
    provider: ProviderInfo
    counts: Counts


class PlayerOut(BaseModel):
    player_id: str
    display_name: str | None
    manager_id: str | None
    segment: str | None


class ReasonOut(BaseModel):
    code: str
    text: str


class QueueItem(BaseModel):
    task_id: int
    conversation_id: str
    player: PlayerOut
    channel: Channel
    status: TaskStatus
    priority: Priority
    route: Route
    category: Category | None  # None when the analysis failed
    summary: str | None
    next_action: str | None
    wait_hours: float | None
    awaiting_reply: bool
    requires_review: bool
    quality_flags: list[str]
    reasons: list[ReasonOut]
    last_message_at: datetime
    simulated: bool


class MessageOut(BaseModel):
    message_id: str
    sender_role: SenderRole
    sent_at: datetime
    text: str
    is_evidence: bool  # cited by the analysis
    is_pending: bool  # player message still waiting for an answer


class AnalysisOut(BaseModel):
    status: ProcessingStatus
    category: Category | None = None
    sentiment: Sentiment | None = None
    urgency: Urgency | None = None
    summary: str | None = None
    confidence: float | None = None
    safety_flag: SafetyFlag | None = None
    needs_escalation: bool | None = None
    model: str | None = None
    simulated: bool
    label: str
    # Public text only: raw provider errors stay on the server.
    message: str | None = None


class TaskOut(BaseModel):
    task_id: int
    status: TaskStatus
    priority: Priority
    route: Route
    next_action: str | None
    reasons: list[ReasonOut]
    quality_flags: list[str]
    requires_review: bool
    suppress_offers: bool
    updated_at: datetime
    resolved_at: datetime | None


class FactsOut(BaseModel):
    as_of: datetime
    awaiting_reply: bool
    wait_hours: float | None
    response_sla_hours: float
    sla_breached: bool
    median_response_minutes: float | None


class ConversationDetail(BaseModel):
    conversation_id: str
    channel: Channel
    player: PlayerOut
    messages: list[MessageOut]
    analysis: AnalysisOut | None
    task: TaskOut | None
    facts: FactsOut
