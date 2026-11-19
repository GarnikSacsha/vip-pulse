"""Format-independent normalization helpers used by every adapter."""

from collections.abc import Callable
from datetime import UTC, datetime

from app.ingestion.report import IngestIssue, IssueLevel
from app.schemas.domain import Channel, Message, SenderRole

_CHANNEL_ALIASES: dict[str, Channel] = {
    "telegram": Channel.TELEGRAM,
    "tg": Channel.TELEGRAM,
    "whatsapp": Channel.WHATSAPP,
    "wa": Channel.WHATSAPP,
    "whats app": Channel.WHATSAPP,
    "email": Channel.EMAIL,
    "e-mail": Channel.EMAIL,
    "mail": Channel.EMAIL,
    "gmail": Channel.EMAIL,
}

_SENDER_ALIASES: dict[str, SenderRole] = {
    "player": SenderRole.PLAYER,
    "client": SenderRole.PLAYER,
    "customer": SenderRole.PLAYER,
    "user": SenderRole.PLAYER,
    "manager": SenderRole.MANAGER,
    "vip_manager": SenderRole.MANAGER,
    "agent": SenderRole.MANAGER,
    "operator": SenderRole.MANAGER,
    "support": SenderRole.MANAGER,
    "system": SenderRole.SYSTEM,
    "bot": SenderRole.SYSTEM,
}


def normalize_channel(raw: object) -> Channel | None:
    """Map a raw channel label to a Channel. None if unknown."""
    key = str(raw or "").strip().lower()
    return _CHANNEL_ALIASES.get(key)


def normalize_sender(raw: object) -> SenderRole | None:
    """Map a raw sender label to a SenderRole. None if unknown."""
    key = str(raw or "").strip().lower()
    return _SENDER_ALIASES.get(key)


def parse_timestamp(raw: object) -> tuple[datetime | None, bool]:
    """Parse ISO-8601 or unix seconds into an aware UTC datetime.

    Returns (value, assumed_utc). `assumed_utc` is True when the source had no
    timezone and UTC was assumed, so the caller can report it.
    """
    if isinstance(raw, int | float) and not isinstance(raw, bool):
        return datetime.fromtimestamp(raw, tz=UTC), False
    text = str(raw or "").strip()
    if not text:
        return None, False
    try:
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None, False
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC), True
    return value.astimezone(UTC), False


def dedupe_messages(
    messages: list[Message], report: Callable[[IngestIssue], None], source: str = "dialogs"
) -> list[Message]:
    """Drop repeated message ids and exact repeats (same sender, time and text)."""
    seen_ids: set[str] = set()
    seen_content: set[tuple[SenderRole, datetime, str]] = set()
    kept: list[Message] = []
    for message in messages:
        fingerprint = (message.sender_role, message.sent_at, message.text)
        if message.message_id in seen_ids:
            reason = "duplicate message id dropped"
        elif fingerprint in seen_content:
            reason = "duplicate message content (same sender, time and text) dropped"
        else:
            seen_ids.add(message.message_id)
            seen_content.add(fingerprint)
            kept.append(message)
            continue
        report(
            IngestIssue(
                level=IssueLevel.WARNING, source=source, ref=message.message_id, reason=reason
            )
        )
    return kept
