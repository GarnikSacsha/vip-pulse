"""SLA lanes for the team lead board and the pulse indicator: decided in code, never by the LLM."""

import pytest

from app.policy.config import PolicyConfig
from app.policy.sla import SlaLane, sla_lane

CFG = PolicyConfig.load()


def test_at_risk_share_comes_from_thresholds() -> None:
    assert CFG.sla.at_risk_share == 0.75


@pytest.mark.parametrize(
    ("active", "awaiting", "wait", "breached", "lane"),
    [
        (True, True, 5.0, True, SlaLane.BREACHED),
        (True, True, 3.0, False, SlaLane.AT_RISK),  # 3 h of 4 h = 75 %
        (True, True, 2.9, False, SlaLane.WAITING),
        (True, False, None, False, SlaLane.OK),  # active, but the manager spoke last
        (False, True, 30.0, False, SlaLane.OK),  # resolved / no action: not open work
        # The triage found no breach (e.g. thresholds changed since): never "breached" here,
        # so the lane cannot disagree with the priority reasons.
        (True, True, 9.0, False, SlaLane.AT_RISK),
    ],
)
def test_lane(active: bool, awaiting: bool, wait: float | None, breached: bool, lane) -> None:
    got = sla_lane(
        active=active,
        awaiting_reply=awaiting,
        wait_hours=wait,
        sla_hours=4.0,
        breached=breached,
        at_risk_share=CFG.sla.at_risk_share,
    )
    assert got == lane


# --- lanes agree with labels; escalated work has its own lane (decision 0013) ---------------


def _lane(**kw) -> SlaLane:
    base = dict(
        active=True,
        awaiting_reply=True,
        wait_hours=1.0,
        sla_hours=4.0,
        breached=False,
        at_risk_share=CFG.sla.at_risk_share,
    )
    base.update(kw)
    return sla_lane(**base)


def test_player_waiting_past_the_sla_burns() -> None:
    assert _lane(wait_hours=30.0, breached=True) == SlaLane.BREACHED


def test_player_waiting_close_to_the_sla_is_at_risk() -> None:
    assert _lane(wait_hours=3.5) == SlaLane.AT_RISK


def test_players_turn_is_ok() -> None:
    assert _lane(awaiting_reply=False, wait_hours=None) == SlaLane.OK


def test_escalated_work_is_with_the_specialist_never_ok() -> None:
    # A responsible-gaming case where the model said "no reply needed" and the player waits 7 days.
    lane = _lane(wait_hours=173.0, reply_needed=False, escalated=True)
    assert lane == SlaLane.SPECIALIST
    assert _lane(wait_hours=30.0, breached=True, escalated=True) == SlaLane.SPECIALIST
    assert _lane(awaiting_reply=False, wait_hours=None, escalated=True) == SlaLane.SPECIALIST


def test_closed_escalation_is_ok() -> None:
    assert _lane(active=False, escalated=True) == SlaLane.OK
