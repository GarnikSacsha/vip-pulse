"""Birthdays as a reason to write, and win-back cards that defer to an open request."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.analysis.llm import FakeProvider
from app.db import init_db, make_engine, session_scope
from app.ingestion.adapters import get_adapter
from app.ingestion.pipeline import ingest
from app.ingestion.store import save_bundle
from app.main import create_app
from app.policy.config import PolicyConfig
from app.policy.winback import OpenRequest, birthdays, winback
from app.schemas.domain import Player
from app.tasks.service import run_triage

CFG = PolicyConfig.load()


def _player(pid: str, birthday: str | None, **attrs: str) -> Player:
    base = {"account_status": "active"} | ({"birthday": birthday} if birthday else {})
    return Player(player_id=pid, manager_id="m1", segment="VIP", attributes=base | attrs)


def _days(as_of: datetime, birthday: str) -> int | None:
    found = birthdays([_player("p", birthday)], as_of, CFG)
    return found[0].days if found else None


def test_window_lives_in_the_yaml() -> None:
    assert CFG.winback.birthday_window_days == 7


@pytest.mark.parametrize(
    ("birthday", "days"),
    [
        ("1990-11-18", 0),  # today
        ("1990-11-25", 7),  # last day of the window ahead
        ("1990-11-11", -7),  # last day of the window behind
        ("1990-11-26", None),  # one day too late
        ("1990-11-10", None),  # one day too early
    ],
)
def test_window_edges(birthday: str, days: int | None) -> None:
    assert _days(datetime(2026, 11, 18, 14, tzinfo=UTC), birthday) == days


def test_window_crosses_new_year_both_ways() -> None:
    assert _days(datetime(2026, 12, 29, tzinfo=UTC), "1985-01-03") == 5
    assert _days(datetime(2027, 1, 2, tzinfo=UTC), "1985-12-30") == -3


def test_leap_day_birthday_in_a_common_year() -> None:
    assert _days(datetime(2027, 2, 27, tzinfo=UTC), "1992-02-29") == 1  # celebrated on 28 Feb


def test_restricted_players_and_unknown_dates_are_left_out() -> None:
    as_of = datetime(2026, 11, 18, tzinfo=UTC)
    players = [
        _player("a", "1990-11-20"),
        _player("b", "1990-11-20", account_status="self_excluded"),
        _player("c", "1990-11-20", account_status="limit_set"),
        _player("d", None),
        _player("e", "не указан"),
    ]
    found = birthdays(players, as_of, CFG)
    assert [b.player.player_id for b in found] == ["a"]
    assert "без бонуса" in found[0].next_action


def test_sorted_soonest_first() -> None:
    as_of = datetime(2026, 11, 18, tzinfo=UTC)
    players = [
        _player("late", "1990-11-24"),
        _player("past", "1990-11-15"),
        _player("soon", "1990-11-19"),
    ]
    assert [b.player.player_id for b in birthdays(players, as_of, CFG)] == ["soon", "late", "past"]


def test_open_request_comes_before_win_back() -> None:
    as_of = datetime(2026, 1, 31, 12, tzinfo=UTC)
    p = _player(
        "w", None, last_login_at="2026-01-05", deposits_30d_usd="0", deposits_prev_30d_usd="5000"
    )
    request = OpenRequest(
        conversation_id="c9", category="withdrawal", priority="P0", wait_hours=50.0
    )
    [item] = winback([p], {}, as_of, CFG, open_requests={"w": request})
    assert item.open_request == request
    assert item.next_action.startswith("Сначала закрыть открытый запрос")
    assert "казино" not in item.next_action

    [plain] = winback([p], {}, as_of, CFG)
    assert plain.open_request is None


# --- API --------------------------------------------------------------------------------------


FIXTURE = Path(__file__).parent / "fixtures" / "task_v1"


def _client(tmp_path: Path, extra: str | None = None) -> TestClient:
    # T1 went silent (last login long ago), has a birthday in two days and an open request.
    players = (FIXTURE / "players.csv").read_text(encoding="utf-8")
    players = players.replace("2026-01-10,1990-01-01", "2025-12-01,1990-01-12")
    if extra:
        players = players.rstrip("\n") + "\n" + extra + "\n"
    (tmp_path / "players.csv").write_text(players, encoding="utf-8")
    engine = make_engine("sqlite://")
    init_db(engine)
    for session in session_scope(engine):
        bundle = ingest(get_adapter("task_v1"), tmp_path / "players.csv", FIXTURE / "dialogs.json")
        save_bundle(session, bundle)
        run_triage(session, FakeProvider(), CFG, now=datetime(2026, 1, 10, 13, tzinfo=UTC))
    return TestClient(create_app(engine=engine))


def test_api_lists_birthdays_by_manager(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        body = client.get("/api/birthdays").json()
        assert [(b["player"]["player_id"], b["days"], b["birthday"]) for b in body] == [
            ("T1", 2, "1990-01-12")
        ]
        assert body[0]["next_action"] == "Поздравить лично, без бонуса и промо."
        assert client.get("/api/birthdays", params={"manager": "Ben"}).json() == []


def test_api_win_back_card_points_to_the_open_request(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        [item] = [i for i in client.get("/api/winback").json() if i["player"]["player_id"] == "T1"]
    assert item["open_request"]["conversation_id"] == "X1"
    assert item["open_request"]["category"] == "withdrawal"
    assert item["next_action"].startswith("Сначала закрыть открытый запрос")


def test_introduction_with_a_birthday_gets_one_hint() -> None:
    as_of = datetime(2026, 1, 31, 12, tzinfo=UTC)
    p = _player("n", "1990-02-02", last_login_at="2026-01-30")  # active, never contacted
    [item] = winback([p], {}, as_of, CFG, birthday_ids={"n"})
    assert item.next_action == "Повод познакомиться — поздравить, без бонуса и промо."


def test_api_does_not_list_the_same_player_twice(tmp_path: Path) -> None:
    with _client(
        tmp_path,
        extra="T3,ACME,CIS,ru,VIP,Ольга,2025-01-01,active,500,2,500,2,"
        "2026-01-09,0,0,,0,0,0,2026-01-09,1991-01-11,Demo Slot",
    ) as client:
        winback_items = {i["player"]["player_id"]: i for i in client.get("/api/winback").json()}
        birthday_ids = [b["player"]["player_id"] for b in client.get("/api/birthdays").json()]
    assert winback_items["T3"]["tier"] == "introduce"
    assert winback_items["T3"]["next_action"].startswith("Повод познакомиться")
    assert "T3" not in birthday_ids
    assert "T1" in birthday_ids  # urgent win-back, not an introduction: keeps its birthday line
