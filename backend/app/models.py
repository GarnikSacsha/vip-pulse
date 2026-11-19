"""Database tables: imported source data, cached analyses, work items and their audit trail."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, UTCDateTime


class PlayerRow(Base):
    __tablename__ = "players"

    player_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(200))
    manager_id: Mapped[str | None] = mapped_column(String(64), index=True)
    segment: Mapped[str | None] = mapped_column(String(64))
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    conversations: Mapped[list["ConversationRow"]] = relationship(back_populates="player")


class ConversationRow(Base):
    __tablename__ = "conversations"

    conversation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    player_id: Mapped[str] = mapped_column(ForeignKey("players.player_id"), index=True)
    channel: Mapped[str] = mapped_column(String(16))
    last_message_at: Mapped[datetime] = mapped_column(UTCDateTime())

    player: Mapped[PlayerRow] = relationship(back_populates="conversations")
    messages: Mapped[list["MessageRow"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="(MessageRow.sent_at, MessageRow.message_id)",
    )


class MessageRow(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_conversation_sent", "conversation_id", "sent_at"),)

    message_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.conversation_id"))
    sender_role: Mapped[str] = mapped_column(String(16))
    sent_at: Mapped[datetime] = mapped_column(UTCDateTime())
    text: Mapped[str] = mapped_column(Text)

    conversation: Mapped[ConversationRow] = relationship(back_populates="messages")


class AnalysisRow(Base):
    """One provider answer for one conversation input. Reused while the input hash is unchanged."""

    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.conversation_id"))
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16))
    model: Mapped[str | None] = mapped_column(String(100))
    simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())


class TaskRow(Base):
    """The work item for one conversation: the latest policy decision plus the manager's status."""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.conversation_id"), unique=True
    )
    analysis_id: Mapped[int | None] = mapped_column(ForeignKey("analyses.id"))
    status: Mapped[str] = mapped_column(String(16), index=True)
    priority: Mapped[str] = mapped_column(String(2), index=True)
    route: Mapped[str] = mapped_column(String(16))
    next_action: Mapped[str | None] = mapped_column(Text)
    reasons: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    quality_flags: Mapped[list[str]] = mapped_column(JSON, default=list)
    requires_review: Mapped[bool] = mapped_column(Boolean, default=False)
    suppress_offers: Mapped[bool] = mapped_column(Boolean, default=False)
    awaiting_reply: Mapped[bool] = mapped_column(Boolean, default=False)
    wait_hours: Mapped[float | None] = mapped_column(Float)
    # Last message seen when the decision was made: a newer player message reopens the task.
    seen_last_message_at: Mapped[datetime] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime())
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class AuditRow(Base):
    """Append-only record of every status change, by a person or by the system."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    at: Mapped[datetime] = mapped_column(UTCDateTime())
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(32))
    before: Mapped[str | None] = mapped_column(String(32))
    after: Mapped[str | None] = mapped_column(String(32))
    note: Mapped[str | None] = mapped_column(Text)


class LLMCallRow(Base):
    """One billed call to a paid model. The sum of `cost_usd` is checked against LLM_BUDGET_USD."""

    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(UTCDateTime())
    model: Mapped[str] = mapped_column(String(100))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    estimated: Mapped[bool] = mapped_column(Boolean, default=False)
    outcome: Mapped[str] = mapped_column(String(32))


class RunLeaseRow(Base):
    """At most one triage run per database, across processes (CLI and API share the budget).

    A lease older than `LEASE_TTL` (app.tasks.service) is left by a crashed process: taken over.
    """

    __tablename__ = "run_lease"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # always 1
    holder: Mapped[str] = mapped_column(String(100))
    started_at: Mapped[datetime] = mapped_column(UTCDateTime())
