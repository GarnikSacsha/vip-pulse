"""Who to win back: silent or slipping players, found in code from the profile and contact dates."""

from datetime import UTC, datetime

from app.policy.config import PolicyConfig
from app.policy.winback import Tier, winback
from app.schemas.domain import Player

CFG = PolicyConfig.load()
AS_OF = datetime(2026, 1, 31, 12, 0, tzinfo=UTC)


def _player(pid: str, **attrs: str) -> Player:
    base = {"account_status": "active", "favorite_game": "Demo Slot"}
    return Player(player_id=pid, manager_id="m1", segment="VIP", attributes=base | attrs)


def test_thresholds_live_in_the_yaml() -> None:
    assert CFG.winback.silent_days == 14


def test_silent_player_who_stopped_depositing_is_urgent() -> None:
    p = _player(
        "a",
        last_login_at="2026-01-05",
        deposits_30d_usd="0",
        deposits_prev_30d_usd="9000",
    )
    [item] = winback([p], {}, AS_OF, CFG)
    assert item.tier == Tier.URGENT
    texts = [r.text for r in item.reasons]
    assert "Не заходил 26 дн." in texts
    assert "Перестал вносить депозиты: было $9 000 за 30 дней" in texts
    assert "Переписок с игроком ещё не было" in texts
    assert "Demo Slot" in item.next_action
    assert "бонус" not in item.next_action.lower() or "только если" in item.next_action


def test_deposit_drop_needs_attention() -> None:
    p = _player(
        "b", last_login_at="2026-01-30", deposits_30d_usd="1000", deposits_prev_30d_usd="5000"
    )
    [item] = winback([p], {"b": datetime(2026, 1, 29, tzinfo=UTC)}, AS_OF, CFG)
    assert item.tier == Tier.ATTENTION
    assert item.last_contact_days == 2


def test_never_contacted_active_player_is_an_introduction() -> None:
    p = _player(
        "c", last_login_at="2026-01-30", deposits_30d_usd="3000", deposits_prev_30d_usd="2900"
    )
    [item] = winback([p], {}, AS_OF, CFG)
    assert item.tier == Tier.INTRODUCE


def test_healthy_contacted_player_is_not_listed() -> None:
    p = _player(
        "d", last_login_at="2026-01-30", deposits_30d_usd="3000", deposits_prev_30d_usd="2900"
    )
    assert winback([p], {"d": datetime(2026, 1, 30, tzinfo=UTC)}, AS_OF, CFG) == []


def test_restricted_accounts_are_never_listed() -> None:
    for status in ("self_excluded", "limit_set"):
        p = _player(
            "e",
            account_status=status,
            last_login_at="2025-12-01",
            deposits_30d_usd="0",
            deposits_prev_30d_usd="9000",
        )
        assert winback([p], {}, AS_OF, CFG) == [], status


def test_order_urgent_first_then_by_value() -> None:
    small = _player(
        "s", last_login_at="2026-01-01", deposits_30d_usd="0", deposits_prev_30d_usd="1000"
    )
    big = _player(
        "b", last_login_at="2026-01-01", deposits_30d_usd="0", deposits_prev_30d_usd="20000"
    )
    intro = _player(
        "i", last_login_at="2026-01-30", deposits_30d_usd="50000", deposits_prev_30d_usd="50000"
    )
    items = winback([small, intro, big], {}, AS_OF, CFG)
    assert [i.player.player_id for i in items] == ["b", "s", "i"]


def test_players_with_a_risk_signal_are_never_listed() -> None:
    p = _player("r", last_login_at="2025-12-01", deposits_30d_usd="0", deposits_prev_30d_usd="9000")
    assert winback([p], {}, AS_OF, CFG, excluded={"r"}) == []


def test_deposit_spike_is_not_an_introduction() -> None:
    p = _player(
        "x", last_login_at="2026-01-30", deposits_30d_usd="4900", deposits_prev_30d_usd="800"
    )
    assert winback([p], {}, AS_OF, CFG) == []


def test_never_contacted_reason_names_the_conversation_not_the_manager() -> None:
    p = _player(
        "n", last_login_at="2026-01-30", deposits_30d_usd="3000", deposits_prev_30d_usd="2900"
    )
    [item] = winback([p], {}, AS_OF, CFG)
    assert [r.text for r in item.reasons] == ["Переписок с игроком ещё не было"]
