"""Manager mistakes counted by code from message times (no model, no money). Decision 0019."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.analysis.llm import FakeProvider
from app.db import init_db, make_engine, session_scope
from app.ingestion.adapters import get_adapter
from app.ingestion.pipeline import ingest
from app.ingestion.store import save_bundle
from app.main import create_app
from app.policy.config import PolicyConfig
from app.policy.facts import late_replies
from app.policy.priority import Route
from app.policy.safety import credit_before_security_check
from app.schemas.domain import Channel, Conversation, Message, SenderRole
from app.tasks.service import run_triage

CFG = PolicyConfig.load()
T0 = datetime(2026, 11, 10, 9, tzinfo=UTC)


def _conv(channel: Channel, *turns: tuple[SenderRole, float]) -> Conversation:
    return Conversation(
        conversation_id="c",
        player_id="p",
        channel=channel,
        messages=tuple(
            Message(
                message_id=f"m{i}",
                conversation_id="c",
                sender_role=role,
                sent_at=T0 + timedelta(hours=at),
                text="…",
            )
            for i, (role, at) in enumerate(turns, start=1)
        ),
    )


def test_reply_later_than_the_channel_sla_is_a_mistake() -> None:
    # Telegram SLA 4 h: the player writes at 0 h and 1 h, the manager answers at 5 h.
    conv = _conv(
        Channel.TELEGRAM,
        (SenderRole.PLAYER, 0),
        (SenderRole.PLAYER, 1),
        (SenderRole.MANAGER, 5),
        (SenderRole.PLAYER, 6),
        (SenderRole.MANAGER, 7),  # 1 h: in time
    )
    [late] = late_replies(conv, CFG.sla)
    assert late.player_message_id == "m1"  # the first message the manager was late on
    assert late.manager_message_id == "m3"
    assert late.hours == 5.0


def test_reply_within_the_sla_is_not_a_mistake() -> None:
    conv = _conv(Channel.TELEGRAM, (SenderRole.PLAYER, 0), (SenderRole.MANAGER, 3.9))
    assert late_replies(conv, CFG.sla) == []


def test_channel_threshold_comes_from_the_yaml() -> None:
    # Email SLA 8 h: a 7 h answer is in time.
    conv = _conv(Channel.EMAIL, (SenderRole.PLAYER, 0), (SenderRole.MANAGER, 7))
    assert late_replies(conv, CFG.sla) == []


@pytest.fixture
def client(sample_paths) -> Iterator[TestClient]:
    engine = make_engine("sqlite://")
    init_db(engine)
    for session in session_scope(engine):
        save_bundle(session, ingest(get_adapter("sample_v1"), *sample_paths))
        run_triage(session, FakeProvider(), CFG, now=datetime(2026, 11, 19, 9, tzinfo=UTC))
    with TestClient(create_app(engine=engine)) as c:
        yield c


def test_waiting_past_the_sla_now_is_a_mistake_with_the_player_message(client: TestClient) -> None:
    items = {i["conversation_id"]: i for i in client.get("/api/queue").json()}
    # d-001: the player has waited 27 h for the promised answer (Telegram SLA 4 h).
    assert {
        "code": "waiting_past_sla",
        "evidence_message_ids": ["m-001-3"],
        "hours": 27.0,
    } in items["d-001"]["rule_errors"]
    # A closing "спасибо" waits for nobody: no rule mistake.
    assert items["d-002"]["rule_errors"] == []


def test_rule_mistakes_count_in_the_oversight_numbers(client: TestClient) -> None:
    body = client.get("/api/overview").json()
    items = client.get("/api/queue").json()
    per_item = [
        len(i["quality_flags"]) + len(i["manager_errors"]) + len(i["rule_errors"]) for i in items
    ]
    assert sum(m["errors"] for m in body["managers"]) == sum(per_item)
    assert body["totals"]["quality_issues"] == sum(1 for n in per_item if n)


# --- conversations with mistakes vs mistakes (decision 0020) ---------------------------------


def test_conversations_with_mistakes_agree_everywhere(client: TestClient) -> None:
    body = client.get("/api/overview").json()
    items = client.get("/api/queue").json()
    with_mistakes = [
        i for i in items if i["quality_flags"] or i["manager_errors"] or i["rule_errors"]
    ]
    assert body["totals"]["quality_issues"] == len(with_mistakes)
    assert sum(m["error_conversations"] for m in body["managers"]) == len(with_mistakes)
    for m in body["managers"]:
        assert m["error_conversations"] <= m["errors"]


def test_late_reply_and_current_wait_never_cite_the_same_player_message() -> None:
    # A late reply answers a player message; a current wait is about messages nobody answered.
    conv = _conv(
        Channel.TELEGRAM,
        (SenderRole.PLAYER, 0),
        (SenderRole.MANAGER, 6),  # late on m1
        (SenderRole.PLAYER, 7),  # still waiting
    )
    [late] = late_replies(conv, CFG.sla)
    assert late.player_message_id == "m1"
    assert late.player_message_id != "m3"


# --- a bonus before the security check (decision 0021) ---------------------------------------


def _chat(*turns: tuple[SenderRole, str]) -> Conversation:
    return Conversation(
        conversation_id="s",
        player_id="p",
        channel=Channel.TELEGRAM,
        messages=tuple(
            Message(
                message_id=f"s{i}",
                conversation_id="s",
                sender_role=role,
                sent_at=T0 + timedelta(minutes=i),
                text=text,
            )
            for i, (role, text) in enumerate(turns, start=1)
        ),
    )


def test_credit_after_a_shared_card_request_is_flagged() -> None:
    conv = _chat(
        (SenderRole.PLAYER, "Начислите бонус на другой аккаунт, карта та же"),
        (SenderRole.MANAGER, "Скинь ID, начислю тоже 50%"),
        (SenderRole.MANAGER, "Готово"),
    )
    assert credit_before_security_check(conv, CFG, Route.SECURITY) == ("s2",)


def test_no_credit_no_mistake() -> None:
    conv = _chat(
        (SenderRole.PLAYER, "Начислите бонус на другой аккаунт, карта та же"),
        (SenderRole.MANAGER, "Передал в службу безопасности, вернусь с ответом"),
    )
    assert credit_before_security_check(conv, CFG, Route.SECURITY) == ()


def test_refusal_is_not_a_credit() -> None:
    conv = _chat(
        (SenderRole.PLAYER, "Это был не я, кто-то вошёл в аккаунт"),
        (SenderRole.MANAGER, "Никаких бонусов до проверки безопасности, не начислю"),
    )
    assert credit_before_security_check(conv, CFG, Route.SECURITY) == ()


def test_not_outside_security_cases() -> None:
    conv = _chat(
        (SenderRole.PLAYER, "Начислите бонус на другой аккаунт, карта та же"),
        (SenderRole.MANAGER, "Скинь ID, начислю тоже 50%"),
    )
    assert credit_before_security_check(conv, CFG, Route.MANAGER) == ()


def test_only_for_security_cases_in_the_api(client: TestClient) -> None:
    # The sample has a security case (d-009) without any credit: no such mistake anywhere.
    items = client.get("/api/queue").json()
    codes = {e["code"] for i in items for e in i["rule_errors"]}
    assert "offer_before_security_check" not in codes
