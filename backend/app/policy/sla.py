"""Which SLA lane a work item belongs to. Used by the team lead board and the pulse indicator."""

from enum import StrEnum


class SlaLane(StrEnum):
    BREACHED = "breached"  # «Горит»: the player waits longer than the channel's SLA
    AT_RISK = "at_risk"  # «Скоро нарушится»: past the at-risk share of the SLA
    WAITING = "waiting"  # «Ждёт»: the player waits, within the SLA
    OK = "ok"  # «Всё ок»: nobody waits, or the item is not open work


def sla_lane(
    *,
    active: bool,
    awaiting_reply: bool,
    wait_hours: float | None,
    sla_hours: float,
    breached: bool,
    at_risk_share: float,
) -> SlaLane:
    """Lane for one item.

    `breached` comes from the triage that set the priority (its SLA reasons), so "Горит" always
    agrees with the priority. Without it the item is at most "at risk", even if today's thresholds
    would call it late: the next triage run settles that.
    """
    if not active or not awaiting_reply or wait_hours is None:
        return SlaLane.OK
    if breached:
        return SlaLane.BREACHED
    if wait_hours >= at_risk_share * sla_hours:
        return SlaLane.AT_RISK
    return SlaLane.WAITING
