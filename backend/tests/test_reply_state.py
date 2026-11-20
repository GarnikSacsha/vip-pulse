"""One source of truth for "the player is waiting for the manager" (decision 0017).

The raw fact (the player wrote last) is corrected by two decisions: the analysis may say nothing
needs an answer, and an escalated case is the specialist's. Every number on every screen uses the
same state.
"""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.analysis.llm import FakeProvider
from app.db import init_db, make_engine, session_scope
from app.ingestion.adapters import get_adapter
from app.ingestion.pipeline import ingest
from app.ingestion.store import save_bundle
from app.main import create_app
from app.policy.config import PolicyConfig
from app.policy.sla import ReplyState, reply_state
from app.tasks.service import run_triage

NOW = datetime(2026, 11, 19, 9, tzinfo=UTC)


@pytest.mark.parametrize(
    ("awaiting", "needed", "escalated", "state"),
    [
        (False, True, False, ReplyState.PLAYERS_TURN),
        (False, True, True, ReplyState.PLAYERS_TURN),
        (True, False, False, ReplyState.NO_REPLY_NEEDED),
        (True, True, False, ReplyState.MANAGER),
        (True, True, True, ReplyState.SPECIALIST),
        (True, False, True, ReplyState.SPECIALIST),  # a safety case never reads "no reply needed"
    ],
)
def test_reply_state(awaiting: bool, needed: bool, escalated: bool, state: ReplyState) -> None:
    got = reply_state(awaiting_reply=awaiting, reply_needed=needed, escalated=escalated)
    assert got == state


@pytest.fixture
def client(sample_paths) -> Iterator[TestClient]:
    engine = make_engine("sqlite://")
    init_db(engine)
    for session in session_scope(engine):
        save_bundle(session, ingest(get_adapter("sample_v1"), *sample_paths))
        run_triage(session, FakeProvider(), PolicyConfig.load(), now=NOW)
    with TestClient(create_app(engine=engine)) as c:
        yield c


def test_overdue_numbers_agree_everywhere(client: TestClient) -> None:
    overview = client.get("/api/overview").json()
    active = client.get("/api/queue", params={"status": ["open", "in_progress"]}).json()
    burning = [i for i in active if i["sla_lane"] == "breached"]
    assert overview["totals"]["overdue"] == len(burning)
    assert overview["totals"]["overdue"] == sum(c["overdue"] for c in overview["channels"])
    assert overview["totals"]["overdue"] == sum(m["overdue"] for m in overview["managers"])
    assert sum(i["overdue"] for i in active) == len(burning)
    # «Ответ в рамках SLA»: waiting players the managers owe, escalations excluded.
    owed = [i for i in active if i["reply_state"] == "manager"]
    assert overview["totals"]["awaiting_reply"] == len(owed)


def test_no_reply_needed_is_not_a_wait_anywhere(client: TestClient) -> None:
    # d-002: "Да, всё пришло, спасибо!" — the player wrote last, ~18 h before the data date.
    item = next(i for i in client.get("/api/queue").json() if i["conversation_id"] == "d-002")
    assert item["reply_state"] == "no_reply_needed"
    assert item["awaiting_reply"] is False
    assert item["wait_hours"] is None
    assert item["overdue"] is False

    facts = client.get("/api/conversations/d-002").json()["facts"]
    assert facts["awaiting_reply"] is False
    assert facts["sla_breached"] is False
    assert facts["reply_state"] == "no_reply_needed"

    waits = [m["oldest_wait_hours"] for m in client.get("/api/overview").json()["managers"]]
    raw = client.get("/api/conversations/d-002").json()["facts"]["raw_wait_hours"]
    assert raw is not None and raw not in waits


def test_escalated_case_waits_for_the_specialist_not_the_manager(client: TestClient) -> None:
    item = next(i for i in client.get("/api/queue").json() if i["conversation_id"] == "d-009")
    assert item["route"] == "security"
    assert item["reply_state"] == "specialist"
    assert item["sla_lane"] == "specialist"
    assert item["overdue"] is False  # not in «Просрочен ответ»: shown in «У специалиста»
