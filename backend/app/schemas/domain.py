"""Normalized domain model.

Source files (players.csv / dialogs.json) are mapped into these models by an
ingestion adapter, so the rest of the system never depends on the raw format.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationInfo, field_validator


class Channel(StrEnum):
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    OTHER = "other"


class SenderRole(StrEnum):
    PLAYER = "player"
    MANAGER = "manager"
    SYSTEM = "system"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)


class Player(_Strict):
    player_id: str = Field(min_length=1)
    display_name: str | None = None
    manager_id: str | None = None
    segment: str | None = None
    # Anything else from the source row is kept, untyped, for display only.
    attributes: dict[str, Any] = Field(default_factory=dict)


class Message(_Strict):
    message_id: str = Field(min_length=1)
    conversation_id: str = Field(min_length=1)
    sender_role: SenderRole
    sent_at: AwareDatetime
    text: str


class Conversation(_Strict):
    conversation_id: str = Field(min_length=1)
    player_id: str = Field(min_length=1)
    channel: Channel
    messages: tuple[Message, ...] = Field(min_length=1)

    @field_validator("messages")
    @classmethod
    def _sorted_and_owned(
        cls, messages: tuple[Message, ...], info: ValidationInfo
    ) -> tuple[Message, ...]:
        conversation_id = info.data.get("conversation_id")
        for message in messages:
            if conversation_id and message.conversation_id != conversation_id:
                raise ValueError(
                    f"message {message.message_id} belongs to {message.conversation_id}, "
                    f"not {conversation_id}"
                )
        return tuple(sorted(messages, key=lambda m: (m.sent_at, m.message_id)))

    @property
    def message_ids(self) -> frozenset[str]:
        return frozenset(m.message_id for m in self.messages)

    @property
    def last_message_at(self) -> datetime:
        return self.messages[-1].sent_at
