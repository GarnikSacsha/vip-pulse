"""Adapter contract. One adapter per source file format."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from app.ingestion.report import IngestIssue
from app.schemas.domain import Conversation, Player


@dataclass
class ParsedSource:
    """What an adapter extracted, before cross-file checks."""

    players: list[Player] = field(default_factory=list)
    conversations: list[Conversation] = field(default_factory=list)
    issues: list[IngestIssue] = field(default_factory=list)
    players_read: int = 0
    conversations_read: int = 0


class SourceAdapter(Protocol):
    name: str

    def parse(self, players_path: Path, dialogs_path: Path) -> ParsedSource:
        """Parse both files. Must not raise on bad records: report them as issues."""
        ...
