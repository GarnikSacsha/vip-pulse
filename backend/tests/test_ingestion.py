import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.cli import main
from app.ingestion.adapters import get_adapter
from app.ingestion.normalize import normalize_channel, normalize_sender, parse_timestamp
from app.ingestion.pipeline import ingest
from app.ingestion.report import IssueLevel
from app.ingestion.store import load_conversations, load_players, save_bundle
from app.schemas.domain import Channel, SenderRole


def _sample_bundle(sample_paths):
    return ingest(get_adapter("sample_v1"), *sample_paths)


def _reasons(report, ref: str) -> list[str]:
    return [i.reason for i in report.issues if i.ref == ref]


def test_sample_counts(sample_paths) -> None:
    report = _sample_bundle(sample_paths).report
    assert report.players_read == 10
    assert report.players_kept == 8
    assert report.conversations_read == 11
    assert report.conversations_kept == 9  # d-008 unknown player, second d-001 duplicate
    assert report.messages_kept == 18


def test_bad_records_are_reported_not_raised(sample_paths) -> None:
    report = _sample_bundle(sample_paths).report
    assert any("missing player_id" in i.reason for i in report.errors)
    assert "duplicate player_id, first row kept" in _reasons(report, "p-002")
    assert any("unknown player_id" in r for r in _reasons(report, "d-008"))
    assert any("duplicate conversation id" in r for r in _reasons(report, "d-001"))
    assert any("unparseable timestamp" in r for r in _reasons(report, "m-009-2"))
    assert any("unknown sender" in r for r in _reasons(report, "m-009-3"))


def test_duplicate_messages_are_dropped(sample_paths) -> None:
    bundle = _sample_bundle(sample_paths)
    d006 = next(c for c in bundle.conversations if c.conversation_id == "d-006")
    assert [m.message_id for m in d006.messages] == ["m-006-1", "m-006-3"]
    reasons = _reasons(bundle.report, "m-006-1") + _reasons(bundle.report, "m-006-2")
    assert "duplicate message id dropped" in reasons
    assert any("duplicate message content" in r for r in reasons)


def test_aliases_are_normalized(sample_paths) -> None:
    by_id = {c.conversation_id: c for c in _sample_bundle(sample_paths).conversations}
    assert by_id["d-002"].channel is Channel.WHATSAPP
    assert by_id["d-002"].messages[0].sender_role is SenderRole.PLAYER
    assert by_id["d-006"].channel is Channel.EMAIL
    assert by_id["d-006"].messages[-1].sender_role is SenderRole.MANAGER


def test_extra_csv_columns_kept_as_attributes(sample_paths) -> None:
    players = {p.player_id: p for p in _sample_bundle(sample_paths).players}
    assert players["p-001"].attributes == {"country": "DE", "registered_at": "2023-04-11"}
    assert players["p-002"].display_name == "Demo Player 002"  # first row wins


@pytest.mark.parametrize(
    ("raw", "expected", "assumed"),
    [
        ("2026-11-10T09:00:00Z", datetime(2026, 11, 10, 9, tzinfo=UTC), False),
        ("2026-11-10T11:00:00+02:00", datetime(2026, 11, 10, 9, tzinfo=UTC), False),
        ("2026-11-10 09:00:00", datetime(2026, 11, 10, 9, tzinfo=UTC), True),
        (1_793_610_000, datetime.fromtimestamp(1_793_610_000, tz=UTC), False),
        ("yesterday", None, False),
        ("", None, False),
    ],
)
def test_parse_timestamp(raw, expected, assumed) -> None:
    assert parse_timestamp(raw) == (expected, assumed)


def test_unknown_labels_return_none() -> None:
    assert normalize_channel("pigeon") is None
    assert normalize_sender("robot") is None
    assert normalize_channel(" TG ") is Channel.TELEGRAM


def test_invalid_json_file_is_an_error_not_a_crash(tmp_path: Path, sample_paths) -> None:
    broken = tmp_path / "dialogs.json"
    broken.write_text("{not json", encoding="utf-8")
    report = ingest(get_adapter("sample_v1"), sample_paths[0], broken).report
    assert report.conversations_kept == 0
    assert any("invalid JSON" in i.reason for i in report.errors)


def test_unknown_channel_is_kept_as_other(tmp_path: Path, sample_paths) -> None:
    dialogs = tmp_path / "dialogs.json"
    dialogs.write_text(
        json.dumps(
            [
                {
                    "dialog_id": "x-1",
                    "player_id": "p-001",
                    "channel": "pigeon",
                    "messages": [
                        {
                            "id": "x-1-1",
                            "sender": "player",
                            "timestamp": "2026-11-01T10:00:00Z",
                            "text": "hello",
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    bundle = ingest(get_adapter("sample_v1"), sample_paths[0], dialogs)
    assert bundle.conversations[0].channel is Channel.OTHER
    assert bundle.report.warnings[0].level is IssueLevel.WARNING


def test_reimport_is_idempotent(session, sample_paths) -> None:
    bundle = _sample_bundle(sample_paths)
    first = save_bundle(session, bundle)
    second = save_bundle(session, _sample_bundle(sample_paths))

    assert (first.players_created, first.conversations_created) == (8, 9)
    assert (second.players_created, second.conversations_created) == (0, 0)
    assert (second.players_updated, second.conversations_updated) == (8, 9)
    assert len(load_players(session)) == 8
    stored = load_conversations(session)
    assert len(stored) == 9
    assert sum(len(c.messages) for c in stored) == 18


def test_roundtrip_preserves_timezone_and_order(session, sample_paths) -> None:
    save_bundle(session, _sample_bundle(sample_paths))
    d001 = next(c for c in load_conversations(session) if c.conversation_id == "d-001")
    assert [m.message_id for m in d001.messages] == ["m-001-1", "m-001-2", "m-001-3"]
    assert d001.messages[0].sent_at == datetime(2026, 11, 10, 9, tzinfo=UTC)


def test_cli_import(tmp_path: Path, sample_paths, capsys) -> None:
    db_url = f"sqlite:///{(tmp_path / 'cli.db').as_posix()}"
    args = [
        "import",
        "--players",
        str(sample_paths[0]),
        "--dialogs",
        str(sample_paths[1]),
        "--database-url",
        db_url,
    ]
    assert main(args) == 0
    assert main(args) == 0
    out = capsys.readouterr().out
    assert "conversations:  9 kept / 11 read" in out
    assert "conversations +0 ~9" in out  # second run updated, created nothing


def test_cli_triage_prints_sorted_queue(tmp_path: Path, sample_paths, capsys) -> None:
    db_url = f"sqlite:///{(tmp_path / 'triage.db').as_posix()}"
    imp = ["import", "--players", str(sample_paths[0]), "--dialogs", str(sample_paths[1])]
    assert main([*imp, "--database-url", db_url]) == 0
    capsys.readouterr()

    assert main(["triage", "--database-url", db_url]) == 0
    lines = [
        ln for ln in capsys.readouterr().out.splitlines() if ln[:2] in {"P0", "P1", "P2", "P3"}
    ]
    assert len(lines) == 9
    assert [ln[:2] for ln in lines] == sorted(ln[:2] for ln in lines)
    assert "[offer_to_vulnerable_player]" in "\n".join(lines)


def test_cli_triage_never_presents_fake_output_as_ai(tmp_path: Path, sample_paths, capsys) -> None:
    db_url = f"sqlite:///{(tmp_path / 'label.db').as_posix()}"
    imp = ["import", "--players", str(sample_paths[0]), "--dialogs", str(sample_paths[1])]
    assert main([*imp, "--database-url", db_url]) == 0
    capsys.readouterr()

    assert main(["triage", "--database-url", db_url]) == 0
    why = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip().startswith("why:")]
    assert why
    assert not [ln for ln in why if "AI" in ln], "fake provider output must not be called AI"
    assert any("эвристика" in ln for ln in why)


def test_cli_triage_on_empty_db(tmp_path: Path, capsys) -> None:
    db_url = f"sqlite:///{(tmp_path / 'empty.db').as_posix()}"
    assert main(["triage", "--database-url", db_url]) == 1
    assert "run `import` first" in capsys.readouterr().err


def test_unreadable_files_are_reported_not_raised(tmp_path: Path, sample_paths) -> None:
    bad_players = tmp_path / "players.csv"
    bad_players.write_bytes(b"player_id,display_name\np-001,\xff\xfe broken\n")
    report = ingest(get_adapter("sample_v1"), bad_players, sample_paths[1]).report
    assert report.players_kept == 0
    assert any("cannot read players file" in i.reason for i in report.errors)

    bad_dialogs = tmp_path / "dialogs.json"
    bad_dialogs.write_bytes(b'{"dialogs": [\xff]}')
    report = ingest(get_adapter("sample_v1"), sample_paths[0], bad_dialogs).report
    assert report.conversations_kept == 0
    assert any("cannot read dialogs file" in i.reason for i in report.errors)
