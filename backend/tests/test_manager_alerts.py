"""Alerts that require the manager to contact the player personally (not a block, not a mistake)."""

from datetime import UTC, datetime, timedelta

from app.policy.config import PolicyConfig
from app.policy.facts import compute_facts
from app.policy.priority import SAFE_MULTI_ACCOUNT_ACTION, Route, decide
from app.policy.safety import detect_safety
from app.policy.sla import SlaLane, sla_lane
from app.schemas.analysis import LLMAnalysis, Priority
from app.schemas.domain import Channel, Conversation, Message, SenderRole

CFG = PolicyConfig.load()
T0 = datetime(2026, 1, 10, 9, 0, tzinfo=UTC)


def _conv(*turns: tuple[SenderRole, str]) -> Conversation:
    messages = tuple(
        Message(
            message_id=f"c-{i}",
            conversation_id="c",
            sender_role=role,
            sent_at=T0 + timedelta(hours=i),
            text=text,
        )
        for i, (role, text) in enumerate(turns, start=1)
    )
    return Conversation(
        conversation_id="c", player_id="p", channel=Channel.TELEGRAM, messages=messages
    )


def _analysis(**overrides: object) -> LLMAnalysis:
    base: dict = {
        "category": "general",
        "sentiment": "positive",
        "urgency": "low",
        "summary": "s",
        "requires_action": False,
        "safety_flag": "none",
        "confidence": 0.9,
    }
    return LLMAnalysis.model_validate(base | overrides)


def _decide(conv: Conversation, analysis: LLMAnalysis | None = None):
    facts = compute_facts(conv, conv.last_message_at, CFG.sla)
    return decide(facts, analysis or _analysis(), detect_safety(conv, CFG), CFG, simulated=False)


def test_keywords_live_in_the_yaml() -> None:
    assert "другой аккаунт" in CFG.safety.multi_account
    assert "same card" in CFG.safety.multi_account


def test_bonus_for_another_account_on_the_same_card_alerts_the_manager() -> None:
    conv = _conv(
        (SenderRole.PLAYER, "Можно бонус и на другой аккаунт? Пополняю с той же карты"),
        (SenderRole.MANAGER, "Пришли ID, посмотрю"),
        (SenderRole.PLAYER, "Спасибо!"),
    )
    d = _decide(conv)
    codes = [r.code for r in d.reasons]
    assert "alert.multi_account" in codes
    assert d.priority <= Priority.P1
    assert d.route == Route.MANAGER  # personal contact, not a block or an escalation
    assert d.next_action == SAFE_MULTI_ACCOUNT_ACTION
    assert d.quality_flags == ()  # an alert, not a manager mistake


def test_only_player_messages_count() -> None:
    conv = _conv((SenderRole.MANAGER, "Напоминаю: один аккаунт на человека, другой аккаунт нельзя"))
    assert "alert.multi_account" not in [r.code for r in _decide(conv).reasons]


def test_english_wording_is_caught() -> None:
    conv = _conv((SenderRole.PLAYER, "Could you add the bonus to my second account? Same card."))
    assert "alert.multi_account" in [r.code for r in _decide(conv).reasons]


def test_lane_is_ok_when_no_reply_is_needed() -> None:
    # The player wrote last ("спасибо"), but the analysis says there is nothing to answer.
    lane = sla_lane(
        active=True,
        awaiting_reply=True,
        wait_hours=170.0,
        sla_hours=4.0,
        breached=False,
        at_risk_share=0.75,
        reply_needed=False,
    )
    assert lane == SlaLane.OK
