"""Response models of the HTTP API: the contract the browser UI is built against."""

from datetime import datetime

from pydantic import BaseModel

from app.policy.priority import Route
from app.policy.sla import SlaLane
from app.schemas.analysis import (
    Category,
    ManagerError,
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
    budget_usd: float | None  # spending limit of a paid provider; None for the fake
    spent_usd: float | None  # recorded spend across all runs; None for the fake


class Counts(BaseModel):
    total: int
    by_status: dict[TaskStatus, int]
    by_priority: dict[Priority, int]


class Meta(BaseModel):
    as_of: datetime | None  # reference "now" of the dataset; None when nothing is imported
    provider: ProviderInfo
    counts: Counts
    managers: list[str]  # distinct managers from players.csv, for the demo role switcher


class PlayerProfile(BaseModel):
    """Profile columns of players.csv for the player card. Missing or unreadable = None."""

    account_status: str | None = None  # active | limit_set | self_excluded
    brand: str | None = None
    language: str | None = None
    geo: str | None = None
    deposits_30d_usd: float | None = None
    deposits_30d_count: int | None = None
    deposits_prev_30d_usd: float | None = None
    deposits_prev_30d_count: int | None = None
    last_deposit_at: str | None = None
    failed_deposits_7d: int | None = None
    withdrawals_30d_usd: float | None = None
    last_withdrawal_at: str | None = None
    pending_withdrawal_usd: float | None = None
    bonuses_30d_usd: float | None = None
    bonuses_30d_count: int | None = None
    last_login_at: str | None = None
    birthday: str | None = None
    favorite_game: str | None = None


class PlayerOut(BaseModel):
    player_id: str
    display_name: str | None
    manager_id: str | None
    segment: str | None
    # Optional profile columns; an adapter maps its source columns to these names.
    country: str | None = None
    registered_at: str | None = None
    profile: PlayerProfile = PlayerProfile()


class ReasonOut(BaseModel):
    code: str
    text: str


class WinbackOut(BaseModel):
    """A player to win back, decided in code (app.policy.winback), never by the model."""

    player: PlayerOut
    tier: str  # urgent | attention | introduce
    reasons: list[ReasonOut]
    next_action: str
    last_login_days: int | None
    last_contact_days: int | None  # None: the manager never wrote
    deposits_30d_usd: float | None
    deposits_prev_30d_usd: float | None
    favorite_game: str | None
    latest_conversation_id: str | None


class QueueItem(BaseModel):
    task_id: int
    conversation_id: str
    player: PlayerOut
    channel: Channel
    status: TaskStatus
    priority: Priority
    route: Route
    category: Category | None  # None when the analysis failed
    sentiment: Sentiment | None  # the player's tone, for the dossier trend; None when failed
    summary: str | None
    next_action: str | None
    wait_hours: float | None
    awaiting_reply: bool
    # Active work (open / in progress) whose player waits longer than the channel's SLA.
    overdue: bool
    sla_hours: float  # the channel's response SLA under the current thresholds
    sla_lane: SlaLane  # computed by app.policy.sla; escalated work is "specialist" (0013)
    # Alerts for the manager to act personally, e.g. "multi_account" (from reasons "alert.*").
    alerts: list[str]
    requires_review: bool
    quality_flags: list[str]  # mistakes counted by code, e.g. a bonus to a vulnerable player
    manager_errors: list[ManagerError]  # mistakes found by the analysis, with evidence
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
    manager_errors: list[ManagerError] = []
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
    alerts: list[str]
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


# --- oversight: team lead and head of VIP ----------------------------------------------------


class OverviewTotals(BaseModel):
    total: int  # conversations with a work item
    active: int  # open + in progress
    in_progress: int
    critical: int  # active P0
    overdue: int  # active and waiting longer than the channel SLA
    awaiting_reply: int  # active and the player spoke last
    escalated: int  # active and routed away from the manager (RG specialist, security)
    quality_issues: int  # active with a manager-quality flag (e.g. offer to a vulnerable player)
    needs_review: int  # active and the analysis must be checked by a person
    resolved: int
    no_action: int


class ManagerLoad(BaseModel):
    manager_id: str | None  # from players.csv; None when the player has no manager
    total: int
    active: int
    in_progress: int
    critical: int
    overdue: int
    oldest_wait_hours: float | None  # longest wait among active items awaiting a reply
    errors: int  # manager mistakes in all their conversations: code flags + analysis findings


class CategoryCount(BaseModel):
    category: Category | None  # None: the analysis failed
    total: int
    active: int


class ChannelCount(BaseModel):
    channel: Channel
    total: int
    active: int
    overdue: int


class Coverage(BaseModel):
    conversations: int  # imported, whether triaged or not
    in_queue: int  # conversations with a work item (the rest wait for a triage run)
    analysed: int  # successful analyses behind the work items
    failed: int
    simulated: int  # of `analysed`: produced by the offline stand-in, not a model


class Overview(BaseModel):
    as_of: datetime | None
    totals: OverviewTotals
    managers: list[ManagerLoad]
    categories: list[CategoryCount]
    channels: list[ChannelCount]
    routes: dict[Route, int]  # active items per route
    coverage: Coverage
