"""Generic cross-file checks applied to any adapter's output."""

from dataclasses import dataclass
from pathlib import Path

from app.ingestion.base import SourceAdapter
from app.ingestion.report import ImportReport, IngestIssue, IssueLevel
from app.schemas.domain import Conversation, Player


@dataclass
class IngestBundle:
    players: list[Player]
    conversations: list[Conversation]
    report: ImportReport


def ingest(adapter: SourceAdapter, players_path: Path, dialogs_path: Path) -> IngestBundle:
    parsed = adapter.parse(players_path, dialogs_path)
    issues: list[IngestIssue] = list(parsed.issues)

    players: dict[str, Player] = {}
    for player in parsed.players:
        if player.player_id in players:
            issues.append(
                IngestIssue(
                    level=IssueLevel.WARNING,
                    source="players",
                    ref=player.player_id,
                    reason="duplicate player_id, first row kept",
                )
            )
            continue
        players[player.player_id] = player

    conversations: dict[str, Conversation] = {}
    seen_message_ids: set[str] = set()
    for conv in parsed.conversations:
        if conv.conversation_id in conversations:
            reason = "duplicate conversation id, first occurrence kept"
        elif conv.player_id not in players:
            reason = f"unknown player_id {conv.player_id!r}, conversation skipped"
        elif clash := conv.message_ids & seen_message_ids:
            reason = f"message ids already used by another conversation: {sorted(clash)}"
        else:
            conversations[conv.conversation_id] = conv
            seen_message_ids |= conv.message_ids
            continue
        issues.append(
            IngestIssue(
                level=IssueLevel.ERROR, source="dialogs", ref=conv.conversation_id, reason=reason
            )
        )

    report = ImportReport(
        adapter=adapter.name,
        players_read=parsed.players_read,
        players_kept=len(players),
        conversations_read=parsed.conversations_read,
        conversations_kept=len(conversations),
        messages_kept=sum(len(c.messages) for c in conversations.values()),
        issues=issues,
    )
    return IngestBundle(list(players.values()), list(conversations.values()), report)
