"""Signals from the player's profile (players.csv): decided in code, never by the LLM."""

from datetime import UTC, datetime, timedelta

from app.policy.config import PolicyConfig
from app.policy.facts import compute_facts
from app.policy.player import player_signals
from app.policy.priority import SAFE_RESTRICTED_ACTION, Route, decide
from app.policy.safety import detect_safety
from app.schemas.analysis import LLMAnalysis, Priority
from app.schemas.domain import Channel, Conversation, Message, Player, SenderRole

CFG = PolicyConfig.load()
T0 = datetime(2026, 1, 10, 9, 0, tzinfo=UTC)


def _conv(*turns: tuple[SenderRole, str], hours_apart: float = 1.0) -> Conversation:
    messages = tuple(
        Message(
            message_id=f"c-{i}",
            conversation_id="c",
            sender_role=role,
            sent_at=T0 + timedelta(hours=i * hours_apart),
            text=text,
        )
        for i, (role, text) in enumerate(turns, start=1)
    )
    return Conversation(
        conversation_id="c", player_id="p", channel=Channel.TELEGRAM, messages=messages
    )


def _player(**attributes: str) -> Player:
    return Player(player_id="p", manager_id="m", segment="VIP", attributes=attributes)


def _analysis(**overrides: object) -> LLMAnalysis:
    base: dict = {
        "category": "general",
        "sentiment": "neutral",
        "urgency": "low",
        "summary": "s",
        "requires_action": False,
        "safety_flag": "none",
        "confidence": 0.9,
    }
    return LLMAnalysis.model_validate(base | overrides)


def _decide(conv: Conversation, player: Player, analysis: LLMAnalysis | None = None):
    facts = compute_facts(conv, conv.last_message_at, CFG.sla)
    return decide(
        facts,
        analysis or _analysis(),
        detect_safety(conv, CFG),
        CFG,
        simulated=False,
        player=player_signals(player, conv, CFG),
    )


QUIET = _conv((SenderRole.MANAGER, "Добрый день!"))
OFFER = _conv((SenderRole.MANAGER, "Для вас бонус 50% на депозит!"))


def test_thresholds_live_in_the_yaml() -> None:
    assert CFG.player.restricted_statuses == ("self_excluded", "limit_set")
    assert CFG.player.failed_deposits_7d == 3
    assert CFG.player.pending_withdrawal_usd == 1000


def test_no_profile_columns_means_no_signals() -> None:
    signals = player_signals(Player(player_id="p"), QUIET, CFG)
    assert signals.reasons == () and not signals.restricted


def test_self_excluded_player_goes_to_the_rg_specialist_without_offers() -> None:
    d = _decide(QUIET, _player(account_status="self_excluded"))
    assert d.route == Route.RG_SPECIALIST
    assert d.priority == Priority.P0
    assert d.suppress_offers and d.requires_human_review
    assert "player.restricted" in [r.code for r in d.reasons]


def test_offer_to_a_player_with_limits_is_a_manager_mistake() -> None:
    d = _decide(OFFER, _player(account_status="limit_set"))
    assert "offer_to_restricted_player" in d.quality_flags
    assert d.suppress_offers
    assert d.priority <= Priority.P1
    assert d.route == Route.MANAGER  # limits alone do not need the specialist


def test_offer_to_an_active_player_is_fine() -> None:
    d = _decide(OFFER, _player(account_status="active"))
    assert d.quality_flags == ()
    assert not d.suppress_offers


def test_suggested_offer_is_replaced_for_a_restricted_player() -> None:
    conv = _conv((SenderRole.PLAYER, "Как дела с турнирами?"))
    advice = _analysis(
        requires_action=True,
        next_action="Предложить бонус на депозит",
        evidence_message_ids=["c-1"],
    )
    d = _decide(conv, _player(account_status="limit_set"), advice)
    assert d.next_action == SAFE_RESTRICTED_ACTION
    assert "guard.offer_removed" in [r.code for r in d.reasons]


def test_failed_deposits_and_pending_withdrawal_raise_priority() -> None:
    conv = _conv((SenderRole.PLAYER, "Не могу пополнить"))
    d = _decide(conv, _player(failed_deposits_7d="7", pending_withdrawal_usd="12000"))
    codes = {r.code: r.text for r in d.reasons}
    assert codes["player.failed_deposits"] == "Неудачных депозитов за 7 дней: 7"
    assert codes["player.pending_withdrawal"] == "Вывод в ожидании: $12 000"
    assert d.priority == Priority.P1  # the player waits and money is stuck


def test_deposit_drop_is_a_churn_risk() -> None:
    d = _decide(QUIET, _player(deposits_30d_usd="1500", deposits_prev_30d_usd="22000"))
    reason = next(r for r in d.reasons if r.code == "player.deposit_drop")
    assert reason.text == "Депозиты за 30 дней упали: $22 000 → $1 500"
    assert d.priority == Priority.P2


def test_deposit_spike_needs_a_human_look() -> None:
    d = _decide(QUIET, _player(deposits_30d_usd="9800", deposits_prev_30d_usd="5200"))
    assert "player.deposit_spike" in [r.code for r in d.reasons]
    assert d.requires_human_review


def test_garbage_numbers_are_ignored_not_raised() -> None:
    signals = player_signals(_player(failed_deposits_7d="n/a", deposits_30d_usd=""), QUIET, CFG)
    assert signals.reasons == ()


def test_refusing_a_bonus_is_not_an_offer() -> None:
    conv = _conv((SenderRole.MANAGER, "Давай сегодня без бонусов, лучше сделаем паузу."))
    d = _decide(conv, _player(account_status="limit_set"))
    assert d.quality_flags == ()
    conv = _conv((SenderRole.MANAGER, "No bonus today, let's take a break."))
    assert _decide(conv, _player(account_status="limit_set")).quality_flags == ()


def test_reload_and_raising_the_limit_count_as_offers() -> None:
    reload = _conv((SenderRole.MANAGER, "Great weekend reload for you, 50% up to $500!"))
    assert (
        "offer_to_restricted_player"
        in _decide(reload, _player(account_status="limit_set")).quality_flags
    )
    raise_limit = _conv((SenderRole.MANAGER, "Your deposit limit can be raised anytime."))
    assert (
        "offer_to_restricted_player"
        in _decide(raise_limit, _player(account_status="limit_set")).quality_flags
    )
    ru = _conv((SenderRole.MANAGER, "Могу поднять лимит, если хочешь."))
    assert (
        "offer_to_restricted_player"
        in _decide(ru, _player(account_status="limit_set")).quality_flags
    )


def test_setting_a_limit_is_not_an_offer() -> None:
    conv = _conv((SenderRole.MANAGER, "Могу поставить лимит на депозит, если хочешь."))
    assert _decide(conv, _player(account_status="limit_set")).quality_flags == ()


def test_a_message_that_refuses_bonuses_is_not_an_offer_even_if_it_quotes_the_request() -> None:
    conv = _conv((SenderRole.MANAGER, "Ты просишь бонусы каждый день. Давай сегодня без бонусов."))
    assert _decide(conv, _player(account_status="limit_set")).quality_flags == ()


# --- offers after a responsible-gaming signal raised by the model, not the keyword net ---------


def _rg_by_model(evidence: list[str]) -> LLMAnalysis:
    return _analysis(
        category="responsible_gaming",
        sentiment="negative",
        requires_action=True,
        next_action="Передать специалисту",
        safety_flag="responsible_gaming",
        evidence_message_ids=evidence,
    )


def test_offer_after_a_model_raised_rg_signal_is_a_manager_mistake() -> None:
    conv = _conv(
        (SenderRole.PLAYER, "Слил всё за вечер, я в минусе по уши"),
        (SenderRole.MANAGER, "Давай дам кешбэк 20%, отыграешь!"),
    )
    d = _decide(conv, _player(), _rg_by_model(["c-1"]))
    assert "offer_to_vulnerable_player" in d.quality_flags


def test_offer_before_the_rg_signal_is_not_flagged() -> None:
    conv = _conv(
        (SenderRole.MANAGER, "С днём рождения! Держи фриспины."),
        (SenderRole.PLAYER, "Спасибо. Кстати, хочу поставить себе паузу, слишком много играю."),
    )
    d = _decide(conv, _player(), _rg_by_model(["c-2"]))
    assert d.quality_flags == ()


def test_spelling_variants_of_cashback_count_as_offers() -> None:
    for text in ("Начислю кешбэк", "Начислю кэшбек", "Отыграешь всё сегодня"):
        conv = _conv((SenderRole.MANAGER, text))
        assert (
            "offer_to_restricted_player"
            in _decide(conv, _player(account_status="limit_set")).quality_flags
        ), text
