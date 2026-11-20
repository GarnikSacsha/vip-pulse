"""Manager mistakes found by the analysis: closed taxonomy, evidence checked fail-closed."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.analysis.evaluate import GoldLabel, evaluate
from app.analysis.llm import FakeProvider
from app.analysis.prompts import PROMPT_VERSION, schema_fingerprint
from app.analysis.service import InvalidOutput, analyze_conversation, parse_output
from app.policy.config import PolicyConfig
from app.policy.facts import compute_facts
from app.schemas.analysis import LLMAnalysis, ManagerErrorCode, ProcessingStatus
from app.schemas.domain import Channel, Conversation, Message, SenderRole

T0 = datetime(2026, 11, 10, 9, tzinfo=UTC)
CFG = PolicyConfig.load()


def _conv(*turns: tuple[SenderRole, str]) -> Conversation:
    return Conversation(
        conversation_id="c1",
        player_id="p1",
        channel=Channel.TELEGRAM,
        messages=tuple(
            Message(
                message_id=f"m{i}",
                conversation_id="c1",
                sender_role=role,
                sent_at=T0 + timedelta(hours=i),
                text=text,
            )
            for i, (role, text) in enumerate(turns, start=1)
        ),
    )


CONV = _conv(
    (SenderRole.PLAYER, "Когда проверят документы?"),
    (SenderRole.MANAGER, "Передал документы в отдел."),
    (SenderRole.PLAYER, "Есть новости?"),
)


def _answer(**overrides: object) -> str:
    data: dict[str, object] = {
        "category": "verification",
        "sentiment": "neutral",
        "urgency": "medium",
        "summary": "Игрок ждёт проверку документов.",
        "requires_action": True,
        "next_action": "Сообщить срок проверки.",
        "evidence_message_ids": ["m1"],
        "confidence": 0.8,
    }
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


def test_the_taxonomy_is_closed() -> None:
    assert {c.value for c in ManagerErrorCode} == {
        "canned_reply",
        "rude_tone",
        "wrong_info",
        "incomplete_answer",
        "wrong_name",
        "broken_promise",
        "retention_pressure",
    }


def test_manager_errors_default_to_none_found() -> None:
    assert parse_output(_answer(), CONV).manager_errors == []


def test_a_cited_manager_error_is_accepted() -> None:
    raw = _answer(manager_errors=[{"code": "incomplete_answer", "evidence_message_ids": ["m2"]}])
    (error,) = parse_output(raw, CONV).manager_errors
    assert error.code == ManagerErrorCode.INCOMPLETE_ANSWER
    assert error.evidence_message_ids == ["m2"]


@pytest.mark.parametrize(
    "errors",
    [
        [{"code": "made_up_code", "evidence_message_ids": ["m2"]}],
        [{"code": "rude_tone", "evidence_message_ids": []}],
        [{"code": "rude_tone", "evidence_message_ids": ["m2"], "comment": "extra"}],
    ],
)
def test_schema_violations_fail_closed(errors: list[dict]) -> None:
    with pytest.raises(InvalidOutput):
        parse_output(_answer(manager_errors=errors), CONV)


def test_error_citing_a_message_that_does_not_exist_fails_closed() -> None:
    raw = _answer(manager_errors=[{"code": "rude_tone", "evidence_message_ids": ["m99"]}])
    with pytest.raises(InvalidOutput, match="not in this conversation"):
        parse_output(raw, CONV)


def test_error_must_cite_a_manager_message() -> None:
    # A mistake of the manager is shown by what the manager wrote, not by the player's words.
    raw = _answer(manager_errors=[{"code": "rude_tone", "evidence_message_ids": ["m1"]}])
    with pytest.raises(InvalidOutput, match="manager message"):
        parse_output(raw, CONV)


def test_contract_change_invalidates_the_cache() -> None:
    assert PROMPT_VERSION == "v4"
    assert "manager_errors" in schema_fingerprint()
    assert "manager_errors" in LLMAnalysis.model_json_schema()["properties"]


def test_fake_provider_returns_errors_and_stays_labelled() -> None:
    facts = compute_facts(CONV, T0 + timedelta(hours=5), CFG.sla)
    outcome = analyze_conversation(FakeProvider(), CONV, None, facts)
    assert outcome.status == ProcessingStatus.OK
    assert outcome.simulated is True
    assert outcome.result is not None
    assert [e.code for e in outcome.result.manager_errors] == [ManagerErrorCode.INCOMPLETE_ANSWER]


def test_fake_provider_flags_a_broken_promise() -> None:
    conv = _conv(
        (SenderRole.PLAYER, "Где мой вывод?"),
        (SenderRole.MANAGER, "Проверю и вернусь к вам сегодня."),
        (SenderRole.PLAYER, "Прошли сутки, ответа нет."),
    )
    facts = compute_facts(conv, T0 + timedelta(hours=5), CFG.sla)
    outcome = analyze_conversation(FakeProvider(), conv, None, facts)
    assert outcome.result is not None
    assert [e.code for e in outcome.result.manager_errors] == [ManagerErrorCode.BROKEN_PROMISE]
    assert outcome.result.manager_errors[0].evidence_message_ids == ["m2"]


def test_eval_scores_manager_errors_as_a_set() -> None:
    gold = {
        "c1": GoldLabel(
            category=["verification"],
            requires_action=[True],
            safety_flag=["none"],
            sentiment=["neutral"],
            manager_errors=[["incomplete_answer"]],
        ),
        "c2": GoldLabel(
            category=["general"],
            requires_action=[False],
            safety_flag=["none"],
            sentiment=["neutral"],
        ),
    }
    base = json.loads(_answer())
    got_right = {**base, "manager_errors": [{"code": "incomplete_answer"}]}
    report = evaluate({"c1": got_right, "c2": {**base, "category": "general"}}, gold)
    assert report.scores["manager_errors"] == (1, 1)  # c2 has no label: not scored

    report = evaluate({"c1": base, "c2": base}, gold)
    assert report.scores["manager_errors"] == (0, 1)
    assert ("c1", "manager_errors", "-", "incomplete_answer") in report.mismatches


def test_gold_label_rejects_unknown_error_codes() -> None:
    with pytest.raises(ValidationError):
        GoldLabel(
            category=["general"],
            requires_action=[False],
            safety_flag=["none"],
            sentiment=["neutral"],
            manager_errors=[["made_up"]],
        )
