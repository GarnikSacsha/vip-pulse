from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.ingestion.adapters import get_adapter
from app.ingestion.pipeline import ingest
from app.policy.config import PolicyConfig
from app.policy.facts import compute_facts, dataset_as_of
from app.policy.priority import SAFE_RG_ACTION, Route, decide
from app.policy.safety import SafetySignal, detect_safety
from app.schemas.analysis import LLMAnalysis, Priority, SafetyFlag
from app.schemas.domain import Channel, Conversation, Message, SenderRole

T0 = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
CFG = PolicyConfig.load()


def conv(
    *turns: tuple[str, float, str], channel: Channel = Channel.TELEGRAM, cid: str = "c1"
) -> Conversation:
    """turns: (sender, hours after T0, text)."""
    return Conversation(
        conversation_id=cid,
        player_id="p1",
        channel=channel,
        messages=tuple(
            Message(
                message_id=f"{cid}-m{i}",
                conversation_id=cid,
                sender_role=SenderRole(sender),
                sent_at=T0 + timedelta(hours=hours),
                text=text,
            )
            for i, (sender, hours, text) in enumerate(turns, start=1)
        ),
    )


def analysis(**overrides: object) -> LLMAnalysis:
    base = {
        "category": "general",
        "sentiment": "neutral",
        "urgency": "low",
        "summary": "s",
        "requires_action": False,
        "confidence": 0.9,
    }
    return LLMAnalysis.model_validate(base | overrides)


def action(category: str = "withdrawal", urgency: str = "medium", **kw: object) -> LLMAnalysis:
    fields: dict[str, object] = {
        "category": category,
        "urgency": urgency,
        "requires_action": True,
        "next_action": "Проверить статус и ответить игроку",
        "evidence_message_ids": ["c1-m1"],
    }
    return analysis(**(fields | kw))


def run(c: Conversation, a: LLMAnalysis | None, as_of_hours: float, cfg: PolicyConfig = CFG):
    facts = compute_facts(c, T0 + timedelta(hours=as_of_hours), cfg.sla)
    return facts, decide(facts, a, detect_safety(c, cfg), cfg, simulated=False)


# --- facts -------------------------------------------------------------------------------


def test_facts_waiting_player() -> None:
    c = conv(("player", 0, "a"), ("manager", 1, "b"), ("player", 2, "c"), ("player", 3, "d"))
    facts = compute_facts(c, T0 + timedelta(hours=8), CFG.sla)
    assert facts.awaiting_reply
    assert facts.pending_message_ids == ("c1-m3", "c1-m4")
    assert facts.wait_hours == 6
    assert facts.sla_breached  # 6h > 4h telegram SLA
    assert facts.median_response_minutes == 60


def test_facts_answered_conversation_is_not_waiting() -> None:
    facts = compute_facts(conv(("player", 0, "a"), ("manager", 1, "b")), T0, CFG.sla)
    assert not facts.awaiting_reply
    assert facts.wait_hours is None
    assert not facts.sla_breached


def test_system_messages_do_not_count_as_answers() -> None:
    c = conv(("player", 0, "help"), ("system", 0.5, "auto-reply: we will answer soon"))
    facts = compute_facts(c, T0 + timedelta(hours=5), CFG.sla)
    assert facts.awaiting_reply
    assert facts.last_sender is SenderRole.PLAYER


def test_email_has_longer_sla() -> None:
    c = conv(("player", 0, "a"), channel=Channel.EMAIL)
    assert not compute_facts(c, T0 + timedelta(hours=6), CFG.sla).sla_breached
    assert compute_facts(c, T0 + timedelta(hours=9), CFG.sla).sla_breached


def test_dataset_as_of_is_latest_message() -> None:
    a = conv(("player", 0, "a"), cid="a")
    b = conv(("player", 5, "b"), cid="b")
    assert dataset_as_of([a, b]) == T0 + timedelta(hours=5)


# --- safety ------------------------------------------------------------------------------


def test_rg_keywords_detected_only_in_player_messages() -> None:
    c = conv(("manager", 0, "Можно закрыть аккаунт в настройках"), ("player", 1, "спасибо"))
    assert detect_safety(c, CFG).flag is SafetyFlag.NONE


def test_offer_after_rg_signal_is_flagged() -> None:
    c = conv(
        ("player", 0, "Не могу остановиться, заблокируйте меня"),
        ("manager", 1, "Давайте начислю бонус, чтобы отыграться"),
    )
    signal = detect_safety(c, CFG)
    assert signal.flag is SafetyFlag.RESPONSIBLE_GAMING
    assert signal.message_ids == ("c1-m1",)
    assert signal.offer_after_rg_message_ids == ("c1-m2",)


def test_fraud_keywords_detected() -> None:
    c = conv(("player", 0, "Вход с нового устройства, это был не я!"))
    assert detect_safety(c, CFG).flag is SafetyFlag.FRAUD_SECURITY


def test_cannot_meet_is_not_fraud() -> None:
    c = conv(("player", 0, "I cannot meet the wagering requirement"))
    assert detect_safety(c, CFG).flag is SafetyFlag.NONE


# --- priority ----------------------------------------------------------------------------


def test_rg_is_p0_routed_to_specialist_even_when_llm_missed_it() -> None:
    c = conv(("player", 0, "Хочу самоисключение на год"), ("manager", 0.2, "Хорошо"))
    _, d = run(c, analysis(), 1)
    assert d.priority is Priority.P0
    assert d.route is Route.RG_SPECIALIST
    assert d.suppress_offers and d.requires_human_review
    assert d.next_action == SAFE_RG_ACTION


def test_bonus_suggestion_is_removed_for_vulnerable_player() -> None:
    c = conv(("player", 0, "Не могу остановиться"))
    a = action(
        category="responsible_gaming",
        next_action="Предложить бонус 50 фриспинов",
        safety_flag="responsible_gaming",
    )
    _, d = run(c, a, 1)
    assert d.next_action == SAFE_RG_ACTION
    assert "guard.offer_removed" in {r.code for r in d.reasons}


def test_llm_safety_flag_is_respected_without_keywords() -> None:
    c = conv(("player", 0, "Кто-то поменял мой пароль"))
    _, d = run(c, action(category="account", safety_flag="fraud_security"), 1)
    assert d.priority is Priority.P0
    assert d.route is Route.SECURITY


def test_money_request_waiting_past_critical_threshold_is_p0() -> None:
    c = conv(("player", 0, "Где мой вывод?"))
    _, d = run(c, action("withdrawal"), 30)
    assert d.priority is Priority.P0
    assert d.reasons[0].code == "sla.money_critical"


def test_money_alone_is_not_critical() -> None:
    c = conv(("player", 0, "Где мой вывод?"))
    _, d = run(c, action("withdrawal"), 1)
    assert d.priority is Priority.P2


def test_non_money_request_past_sla_is_p1() -> None:
    c = conv(("player", 0, "Слоты не грузятся"))
    _, d = run(c, action("technical"), 30)
    assert d.priority is Priority.P1


def test_resolved_conversation_is_p3() -> None:
    c = conv(("player", 0, "Депозит не пришёл"), ("manager", 1, "Зачислили"))
    _, d = run(c, analysis(category="deposit", sentiment="positive"), 2)
    assert d.priority is Priority.P3
    assert d.reasons[0].code == "none"


def test_closing_thanks_from_player_is_not_a_pending_request() -> None:
    c = conv(("player", 0, "Депозит?"), ("manager", 1, "Зачислили"), ("player", 2, "Спасибо!"))
    facts, d = run(c, analysis(category="deposit", sentiment="positive"), 30)
    assert facts.awaiting_reply and facts.sla_breached  # the raw fact stays honest
    assert d.priority is Priority.P3
    assert d.reasons[0].code == "sla.no_reply_needed"


def test_closing_thanks_without_llm_stays_conservative() -> None:
    c = conv(("player", 0, "Депозит?"), ("manager", 1, "Зачислили"), ("player", 2, "Спасибо!"))
    assert run(c, None, 30)[1].priority is Priority.P1


def test_high_urgency_and_escalation_raise_to_p1() -> None:
    c = conv(("player", 0, "a"), ("manager", 0.1, "b"))
    assert run(c, action(urgency="high"), 1)[1].priority is Priority.P1
    assert run(c, action(needs_escalation=True), 1)[1].priority is Priority.P1


def test_llm_failure_falls_back_to_facts_and_asks_for_review() -> None:
    c = conv(("player", 0, "Ответьте пожалуйста"))
    _, d = run(c, None, 10)
    assert d.priority is Priority.P1  # from SLA breach alone
    assert d.requires_human_review
    assert "analysis.unavailable" in {r.code for r in d.reasons}


def test_low_confidence_requires_review() -> None:
    c = conv(("player", 0, "a"), ("manager", 0.1, "b"))
    _, d = run(c, action(confidence=0.3), 1)
    assert d.requires_human_review


def test_thresholds_are_configurable(tmp_path: Path) -> None:
    text = Path(__file__).parents[1].joinpath("app/policy/thresholds.yaml").read_text("utf-8")
    custom = tmp_path / "policy.yaml"
    custom.write_text(text.replace("critical_wait_hours: 24", "critical_wait_hours: 2"), "utf-8")
    cfg = PolicyConfig.load(custom)
    c = conv(("player", 0, "Где мой вывод?"))
    assert run(c, action("withdrawal"), 3, CFG)[1].priority is Priority.P2
    assert run(c, action("withdrawal"), 3, cfg)[1].priority is Priority.P0


def test_safety_signal_dominates_any_analysis() -> None:
    facts = compute_facts(conv(("player", 0, "a")), T0, CFG.sla)
    signal = SafetySignal(flag=SafetyFlag.RESPONSIBLE_GAMING, message_ids=("c1-m1",))
    assert decide(facts, analysis(), signal, CFG, simulated=False).priority is Priority.P0


# --- sample dataset smoke ----------------------------------------------------------------


@pytest.fixture
def sample_conversations(sample_paths) -> dict[str, Conversation]:
    bundle = ingest(get_adapter("sample_v1"), *sample_paths)
    return {c.conversation_id: c for c in bundle.conversations}


def test_sample_facts_without_llm(sample_conversations) -> None:
    as_of = dataset_as_of(sample_conversations.values())
    facts = {cid: compute_facts(c, as_of, CFG.sla) for cid, c in sample_conversations.items()}
    assert facts["d-001"].awaiting_reply and facts["d-001"].sla_breached
    assert facts["d-002"].awaiting_reply  # "спасибо" came last; the LLM decides it needs no reply
    assert not facts["d-010"].awaiting_reply  # manager wrote last, nobody is waiting

    d004 = sample_conversations["d-004"]
    signal = detect_safety(d004, CFG)
    decision = decide(facts["d-004"], None, signal, CFG, simulated=False)
    assert decision.priority is Priority.P0
    assert "offer_to_vulnerable_player" in decision.quality_flags
    assert detect_safety(sample_conversations["d-009"], CFG).flag is SafetyFlag.FRAUD_SECURITY


# --- provenance of the analysis ------------------------------------------------------------


def _reason_texts(simulated: bool) -> list[str]:
    c = conv(("player", 0, "Где мой вывод?"))
    facts = compute_facts(c, T0 + timedelta(hours=1), CFG.sla)
    a = action(needs_escalation=True, confidence=0.3)
    return [
        r.text for r in decide(facts, a, detect_safety(c, CFG), CFG, simulated=simulated).reasons
    ]


def test_reasons_from_real_model_are_labelled_ai() -> None:
    texts = [t for t in _reason_texts(simulated=False) if "(" in t]
    assert texts and all("AI" in t for t in texts)


def test_reasons_from_simulated_analysis_never_say_ai() -> None:
    texts = _reason_texts(simulated=True)
    assert not [t for t in texts if "AI" in t]
    assert any("эвристика" in t for t in texts)


def test_simulated_flag_is_required() -> None:
    facts = compute_facts(conv(("player", 0, "a")), T0, CFG.sla)
    with pytest.raises(TypeError):
        decide(facts, None, SafetySignal(), CFG)  # type: ignore[call-arg]


def test_safety_reason_from_analysis_is_labelled_but_keyword_reason_is_not() -> None:
    by_model = conv(("player", 0, "Кто-то поменял мой пароль"))
    facts = compute_facts(by_model, T0, CFG.sla)
    a = action(category="account", safety_flag="fraud_security")
    d = decide(facts, a, detect_safety(by_model, CFG), CFG, simulated=True)
    assert d.reasons[0].text.endswith("(эвристика fake, без модели)")

    by_keyword = conv(("player", 0, "Это был не я!"))
    facts = compute_facts(by_keyword, T0, CFG.sla)
    d = decide(facts, a, detect_safety(by_keyword, CFG), CFG, simulated=True)
    assert d.reasons[0].text == "Возможный взлом или мошенничество"  # found by code, not a model
