"""Facts about a conversation that code can compute exactly, without an LLM."""

from collections.abc import Iterable
from datetime import datetime
from statistics import median

from pydantic import BaseModel, ConfigDict

from app.policy.config import SlaConfig
from app.schemas.domain import Conversation, SenderRole


class ConversationFacts(BaseModel):
    model_config = ConfigDict(frozen=True)

    conversation_id: str
    as_of: datetime
    last_message_at: datetime
    last_sender: SenderRole
    awaiting_reply: bool  # the player spoke last and nobody answered yet
    pending_since: datetime | None  # first unanswered player message
    pending_message_ids: tuple[str, ...]
    wait_hours: float | None
    response_sla_hours: float
    sla_breached: bool
    player_messages: int
    manager_messages: int
    median_response_minutes: float | None  # manager reaction time across the conversation


def dataset_as_of(conversations: Iterable[Conversation]) -> datetime:
    """Reference "now" for a historical dataset: the latest message in it.

    Using the wall clock would mark every old demo conversation as overdue.
    """
    return max(c.last_message_at for c in conversations)


def compute_facts(conv: Conversation, as_of: datetime, sla: SlaConfig) -> ConversationFacts:
    human = [m for m in conv.messages if m.sender_role != SenderRole.SYSTEM]
    last = human[-1] if human else conv.messages[-1]

    pending = []
    for message in reversed(human):
        if message.sender_role != SenderRole.PLAYER:
            break
        pending.append(message)
    pending.reverse()

    response_minutes: list[float] = []
    waiting_from: datetime | None = None
    for message in human:
        if message.sender_role == SenderRole.PLAYER:
            waiting_from = waiting_from or message.sent_at
        elif waiting_from is not None:
            response_minutes.append((message.sent_at - waiting_from).total_seconds() / 60)
            waiting_from = None

    sla_hours = sla.response_hours_for(conv.channel)
    pending_since = pending[0].sent_at if pending else None
    wait_hours = (as_of - pending_since).total_seconds() / 3600 if pending_since else None

    return ConversationFacts(
        conversation_id=conv.conversation_id,
        as_of=as_of,
        last_message_at=conv.last_message_at,
        last_sender=last.sender_role,
        awaiting_reply=bool(pending),
        pending_since=pending_since,
        pending_message_ids=tuple(m.message_id for m in pending),
        wait_hours=round(wait_hours, 2) if wait_hours is not None else None,
        response_sla_hours=sla_hours,
        sla_breached=wait_hours is not None and wait_hours > sla_hours,
        player_messages=sum(m.sender_role == SenderRole.PLAYER for m in human),
        manager_messages=sum(m.sender_role == SenderRole.MANAGER for m in human),
        median_response_minutes=round(median(response_minutes), 1) if response_minutes else None,
    )


class LateReply(BaseModel):
    """A manager reply that came later than the channel's SLA. Counted by code, not the model."""

    model_config = ConfigDict(frozen=True)

    player_message_id: str  # the first player message the manager was late on
    manager_message_id: str
    hours: float


def late_replies(conv: Conversation, sla: SlaConfig) -> list[LateReply]:
    """Every manager answer given after the channel's SLA, in any conversation (closed too)."""
    limit = sla.response_hours_for(conv.channel)
    found: list[LateReply] = []
    waiting = None
    for message in conv.messages:
        if message.sender_role == SenderRole.PLAYER:
            waiting = waiting or message
        elif message.sender_role == SenderRole.MANAGER and waiting is not None:
            hours = (message.sent_at - waiting.sent_at).total_seconds() / 3600
            if hours > limit:
                found.append(
                    LateReply(
                        player_message_id=waiting.message_id,
                        manager_message_id=message.message_id,
                        hours=round(hours, 1),
                    )
                )
            waiting = None
    return found
