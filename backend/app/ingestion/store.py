"""Idempotent persistence of an IngestBundle, and loading it back as domain objects."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ingestion.pipeline import IngestBundle
from app.models import ConversationRow, MessageRow, PlayerRow
from app.schemas.domain import Channel, Conversation, Message, Player, SenderRole


@dataclass
class StoreResult:
    players_created: int = 0
    players_updated: int = 0
    conversations_created: int = 0
    conversations_updated: int = 0


def save_bundle(session: Session, bundle: IngestBundle) -> StoreResult:
    """Upsert by source id: importing the same files twice creates no duplicates."""
    result = StoreResult()
    for player in bundle.players:
        row = session.get(PlayerRow, player.player_id)
        if row is None:
            row = PlayerRow(player_id=player.player_id)
            session.add(row)
            result.players_created += 1
        else:
            result.players_updated += 1
        row.display_name = player.display_name
        row.manager_id = player.manager_id
        row.segment = player.segment
        row.attributes = dict(player.attributes)

    for conv in bundle.conversations:
        row = session.get(ConversationRow, conv.conversation_id)
        if row is None:
            row = ConversationRow(conversation_id=conv.conversation_id)
            session.add(row)
            result.conversations_created += 1
        else:
            result.conversations_updated += 1
        row.player_id = conv.player_id
        row.channel = conv.channel.value
        row.last_message_at = conv.last_message_at
        # Messages are owned by the conversation: sync by id, drop ones no longer in source.
        existing = {m.message_id: m for m in row.messages}
        synced: list[MessageRow] = []
        for m in conv.messages:
            msg_row = existing.get(m.message_id) or MessageRow(message_id=m.message_id)
            msg_row.sender_role = m.sender_role.value
            msg_row.sent_at = m.sent_at
            msg_row.text = m.text
            synced.append(msg_row)
        row.messages = synced
        session.flush()
    session.commit()
    return result


def load_players(session: Session) -> list[Player]:
    rows = session.scalars(select(PlayerRow).order_by(PlayerRow.player_id))
    return [
        Player(
            player_id=r.player_id,
            display_name=r.display_name,
            manager_id=r.manager_id,
            segment=r.segment,
            attributes=r.attributes or {},
        )
        for r in rows
    ]


def load_conversations(session: Session) -> list[Conversation]:
    rows = session.scalars(
        select(ConversationRow)
        .options(selectinload(ConversationRow.messages))
        .order_by(ConversationRow.conversation_id)
    )
    return [
        Conversation(
            conversation_id=r.conversation_id,
            player_id=r.player_id,
            channel=Channel(r.channel),
            messages=tuple(
                Message(
                    message_id=m.message_id,
                    conversation_id=r.conversation_id,
                    sender_role=SenderRole(m.sender_role),
                    sent_at=m.sent_at,
                    text=m.text,
                )
                for m in r.messages
            ),
        )
        for r in rows
    ]
