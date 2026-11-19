"""Database tables for imported source data.

Analyses, tasks and audit events are added in later stages.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, String, Text
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
