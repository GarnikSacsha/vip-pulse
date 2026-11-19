"""Adapter for the synthetic `sample_v1` format in data/sample/.

players.csv: player_id, display_name, manager_id, segment, + any extra columns
dialogs.json: {"dialogs": [{dialog_id, player_id, channel,
                            messages: [{id, sender, timestamp, text}]}]}
"""

import csv
import json
from pathlib import Path
from typing import Any, ClassVar

from pydantic import ValidationError

from app.ingestion.base import ParsedSource
from app.ingestion.normalize import (
    dedupe_messages,
    normalize_channel,
    normalize_sender,
    parse_timestamp,
)
from app.ingestion.report import IngestIssue, IssueLevel
from app.schemas.domain import Channel, Conversation, Message, Player

_PLAYER_FIELDS = ("player_id", "display_name", "manager_id", "segment")


def _clean(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


class SampleV1Adapter:
    name: ClassVar[str] = "sample_v1"

    def parse(self, players_path: Path, dialogs_path: Path) -> ParsedSource:
        out = ParsedSource()
        self._parse_players(players_path, out)
        self._parse_dialogs(dialogs_path, out)
        return out

    def _issue(self, out: ParsedSource, level: IssueLevel, source: str, ref: str, reason: str):
        out.issues.append(IngestIssue(level=level, source=source, ref=ref, reason=reason))

    def _parse_players(self, path: Path, out: ParsedSource) -> None:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row_no, row in enumerate(csv.DictReader(handle), start=2):  # 1 = header
                out.players_read += 1
                player_id = _clean(row.get("player_id"))
                if not player_id:
                    self._issue(
                        out, IssueLevel.ERROR, "players", f"row {row_no}", "missing player_id"
                    )
                    continue
                extra = {k: v for k, v in row.items() if k and k not in _PLAYER_FIELDS and v}
                out.players.append(
                    Player(
                        player_id=player_id,
                        display_name=_clean(row.get("display_name")),
                        manager_id=_clean(row.get("manager_id")),
                        segment=_clean(row.get("segment")),
                        attributes=extra,
                    )
                )

    def _parse_dialogs(self, path: Path, out: ParsedSource) -> None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            self._issue(out, IssueLevel.ERROR, "dialogs", path.name, f"invalid JSON: {exc}")
            return
        dialogs = payload.get("dialogs") if isinstance(payload, dict) else payload
        if not isinstance(dialogs, list):
            self._issue(
                out,
                IssueLevel.ERROR,
                "dialogs",
                path.name,
                "expected a list of dialogs or {'dialogs': [...]}",
            )
            return
        for index, raw in enumerate(dialogs):
            out.conversations_read += 1
            conversation = self._parse_dialog(raw, index, out)
            if conversation is not None:
                out.conversations.append(conversation)

    def _parse_dialog(self, raw: Any, index: int, out: ParsedSource) -> Conversation | None:
        if not isinstance(raw, dict):
            self._issue(out, IssueLevel.ERROR, "dialogs", f"#{index}", "dialog is not an object")
            return None
        dialog_id = str(raw.get("dialog_id") or "").strip()
        ref = dialog_id or f"#{index}"
        player_id = str(raw.get("player_id") or "").strip()
        if not dialog_id or not player_id:
            self._issue(out, IssueLevel.ERROR, "dialogs", ref, "missing dialog_id or player_id")
            return None

        channel = normalize_channel(raw.get("channel"))
        if channel is None:
            self._issue(
                out,
                IssueLevel.WARNING,
                "dialogs",
                ref,
                f"unknown channel {raw.get('channel')!r}, stored as 'other'",
            )
            channel = Channel.OTHER

        messages: list[Message] = []
        for msg_index, msg in enumerate(raw.get("messages") or []):
            message = self._parse_message(msg, dialog_id, f"{ref}/#{msg_index}", out)
            if message is not None:
                messages.append(message)
        messages = dedupe_messages(messages, out.issues.append)
        if not messages:
            self._issue(out, IssueLevel.ERROR, "dialogs", ref, "no valid messages")
            return None
        return Conversation(
            conversation_id=dialog_id,
            player_id=player_id,
            channel=channel,
            messages=tuple(messages),
        )

    def _parse_message(
        self, raw: Any, dialog_id: str, ref: str, out: ParsedSource
    ) -> Message | None:
        if not isinstance(raw, dict):
            self._issue(out, IssueLevel.ERROR, "dialogs", ref, "message is not an object")
            return None
        message_id = str(raw.get("id") or "").strip()
        ref = message_id or ref
        sender = normalize_sender(raw.get("sender"))
        if sender is None:
            self._issue(
                out,
                IssueLevel.ERROR,
                "dialogs",
                ref,
                f"unknown sender {raw.get('sender')!r}, message skipped",
            )
            return None
        sent_at, assumed_utc = parse_timestamp(raw.get("timestamp"))
        if sent_at is None:
            self._issue(
                out,
                IssueLevel.ERROR,
                "dialogs",
                ref,
                f"unparseable timestamp {raw.get('timestamp')!r}, message skipped",
            )
            return None
        if assumed_utc:
            self._issue(
                out, IssueLevel.WARNING, "dialogs", ref, "timestamp without timezone, assumed UTC"
            )
        try:
            return Message(
                message_id=message_id,
                conversation_id=dialog_id,
                sender_role=sender,
                sent_at=sent_at,
                text=str(raw.get("text") or ""),
            )
        except ValidationError as exc:
            self._issue(
                out, IssueLevel.ERROR, "dialogs", ref, f"invalid message: {exc.errors()[0]['msg']}"
            )
            return None
