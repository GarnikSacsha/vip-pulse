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
