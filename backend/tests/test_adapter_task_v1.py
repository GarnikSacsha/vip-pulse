"""Adapter for the format of the task files (data/input/). Tested on an invented fixture only:
the real files are internal and never enter tests or Git."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.cli import main
from app.ingestion.adapters import get_adapter
from app.ingestion.pipeline import ingest

FIXTURE = Path(__file__).parent / "fixtures" / "task_v1"
PATHS = (FIXTURE / "players.csv", FIXTURE / "dialogs.json")


@pytest.fixture
def bundle():
    return ingest(get_adapter("task_v1"), *PATHS)


def test_counts_and_no_errors(bundle) -> None:
    report = bundle.report
    assert (report.players_kept, report.conversations_kept, report.messages_kept) == (2, 2, 4)
    assert report.errors == []


def test_players_map_manager_and_status(bundle) -> None:
    players = {p.player_id: p for p in bundle.players}
    t1 = players["T1"]
    assert t1.manager_id == "Ольга"
    assert t1.segment == "VIP"
    assert t1.display_name is None
    assert t1.attributes["account_status"] == "active"
    assert t1.attributes["country"] == "CIS"  # geo is the only location column
    assert t1.attributes["registered_at"] == "2025-01-01"  # vip_since: start of the relationship
    assert players["T2"].attributes["account_status"] == "self_excluded"


def test_messages_get_stable_ids_in_file_order(bundle) -> None:
    conv = next(c for c in bundle.conversations if c.conversation_id == "X1")
    assert [m.message_id for m in conv.messages] == ["X1-1", "X1-2", "X1-3"]
    assert [m.sender_role.value for m in conv.messages] == ["player", "manager", "player"]
    assert conv.messages[0].sent_at == datetime(2026, 1, 10, 9, 0, tzinfo=UTC)


def test_missing_timezone_is_reported_once_per_file(bundle) -> None:
    warnings = [i for i in bundle.report.warnings if "timezone" in i.reason]
    assert len(warnings) == 1
    assert "4 timestamps" in warnings[0].reason


def test_reimport_keeps_the_same_ids() -> None:
    first = ingest(get_adapter("task_v1"), *PATHS)
    second = ingest(get_adapter("task_v1"), *PATHS)
    ids = lambda b: [m.message_id for c in b.conversations for m in c.messages]  # noqa: E731
    assert ids(first) == ids(second)


def test_cli_imports_and_triages_the_task_format(tmp_path: Path, capsys) -> None:
    db = f"sqlite:///{(tmp_path / 't.db').as_posix()}"
    args = [
        "import",
        "--adapter",
        "task_v1",
        "--players",
        str(PATHS[0]),
        "--dialogs",
        str(PATHS[1]),
    ]
    assert main([*args, "--database-url", db]) == 0
    assert main(["triage", "--database-url", db]) == 0
    out = capsys.readouterr().out
    assert "X1" in out and "X2" in out
