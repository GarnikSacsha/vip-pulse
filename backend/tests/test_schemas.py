from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.schemas.analysis import (
    AnalysisOutcome,
    Category,
    LLMAnalysis,
    Priority,
    ProcessingStatus,
    SafetyFlag,
)
from app.schemas.domain import Channel, Conversation, Message, SenderRole

T0 = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


def _msg(mid: str, minutes: int, role: SenderRole = SenderRole.PLAYER, cid: str = "c1") -> Message:
    return Message(
        message_id=mid,
        conversation_id=cid,
        sender_role=role,
        sent_at=T0 + timedelta(minutes=minutes),
        text="hi",
    )


def _analysis(**overrides: object) -> dict:
    base = {
        "category": "withdrawal",
        "sentiment": "negative",
        "urgency": "high",
        "summary": "Player waits for a withdrawal.",
        "requires_action": True,
        "next_action": "Check payout status and reply.",
        "evidence_message_ids": ["m1"],
        "confidence": 0.8,
    }
    return base | overrides


def test_conversation_sorts_messages_chronologically() -> None:
    conv = Conversation(
        conversation_id="c1",
        player_id="p1",
        channel=Channel.TELEGRAM,
        messages=(_msg("m2", 10), _msg("m1", 0)),
    )
    assert [m.message_id for m in conv.messages] == ["m1", "m2"]
    assert conv.last_message_at == T0 + timedelta(minutes=10)


def test_conversation_rejects_foreign_message() -> None:
    with pytest.raises(ValidationError, match="belongs to"):
        Conversation(
            conversation_id="c1",
            player_id="p1",
            channel=Channel.EMAIL,
            messages=(_msg("m1", 0, cid="other"),),
        )


def test_message_requires_timezone() -> None:
    with pytest.raises(ValidationError):
        Message(
            message_id="m1",
            conversation_id="c1",
            sender_role=SenderRole.PLAYER,
            sent_at=datetime(2026, 11, 1, 12, 0),
            text="naive timestamp",
        )


def test_valid_analysis_parses_and_dedupes_evidence() -> None:
    result = LLMAnalysis.model_validate(_analysis(evidence_message_ids=["m1", " m1 ", "m2"]))
    assert result.category is Category.WITHDRAWAL
    assert result.evidence_message_ids == ["m1", "m2"]


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"category": "casino_bonus"}, "category"),
        ({"confidence": 1.5}, "confidence"),
        ({"next_action": None}, "next_action is required"),
        ({"evidence_message_ids": []}, "evidence_message_ids"),
        ({"priority": "P0"}, "Extra inputs"),
    ],
)
def test_invalid_analysis_is_rejected(overrides: dict, error: str) -> None:
    with pytest.raises(ValidationError, match=error):
        LLMAnalysis.model_validate(_analysis(**overrides))


def test_safety_flag_requires_evidence_even_without_action() -> None:
    with pytest.raises(ValidationError, match="evidence_message_ids"):
        LLMAnalysis.model_validate(
            _analysis(
                requires_action=False,
                next_action=None,
                safety_flag=SafetyFlag.RESPONSIBLE_GAMING,
                evidence_message_ids=[],
            )
        )


def test_outcome_status_must_match_payload() -> None:
    with pytest.raises(ValidationError):
        AnalysisOutcome(conversation_id="c1", status=ProcessingStatus.FAILED)
    ok = AnalysisOutcome(
        conversation_id="c1",
        status=ProcessingStatus.OK,
        result=LLMAnalysis.model_validate(_analysis()),
    )
    assert ok.result is not None


def test_priority_values_sort_by_urgency() -> None:
    assert sorted([Priority.P2, Priority.P0, Priority.P3, Priority.P1]) == [
        Priority.P0,
        Priority.P1,
        Priority.P2,
        Priority.P3,
    ]
