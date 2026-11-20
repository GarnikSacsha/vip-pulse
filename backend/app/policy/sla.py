"""Who owes the next message, and which SLA lane a work item belongs to.

`reply_state` is the single source of truth for "the player is waiting for the manager"
(decision 0017). The raw fact (the player wrote last) is corrected by two decisions: the analysis
may say nothing needs an answer («спасибо, всё пришло»), and an escalated case is the
specialist's. Lanes, overdue counts, waits and the conversation facts all derive from it.
"""

from enum import StrEnum


class ReplyState(StrEnum):
    PLAYERS_TURN = "players_turn"  # the manager wrote last
    NO_REPLY_NEEDED = "no_reply_needed"  # the player wrote last; the analysis: nothing to answer
    MANAGER = "manager"  # the player waits for the manager
    SPECIALIST = "specialist"  # the player waits; the case is with a specialist


def reply_state(*, awaiting_reply: bool, reply_needed: bool, escalated: bool) -> ReplyState:
    if not awaiting_reply:
        return ReplyState.PLAYERS_TURN
    if escalated:  # a safety case never reads "no reply needed"
        return ReplyState.SPECIALIST
    return ReplyState.MANAGER if reply_needed else ReplyState.NO_REPLY_NEEDED


class SlaLane(StrEnum):
    BREACHED = "breached"  # «Горит»: the player waits longer than the channel's SLA
    AT_RISK = "at_risk"  # «Скоро нарушится»: past the at-risk share of the SLA
    WAITING = "waiting"  # «Ждёт»: the player waits, within the SLA
    OK = "ok"  # «Всё ок»: nobody waits, or the item is not open work
    # «У специалиста»: escalated to a responsible-gaming or security specialist. Never «Всё ок»,
    # whatever the model said about a reply (decision 0013).
    SPECIALIST = "specialist"


def sla_lane(
    *,
    active: bool,
    awaiting_reply: bool,
    wait_hours: float | None,
    sla_hours: float,
    breached: bool,
    at_risk_share: float,
    reply_needed: bool = True,
    escalated: bool = False,
) -> SlaLane:
    """Lane for one item.

    `breached` comes from the triage that set the priority (its SLA reasons), so "Горит" always
    agrees with the priority. Without it the item is at most "at risk", even if today's thresholds
    would call it late: the next triage run settles that.
    """
    if active and escalated:
        return SlaLane.SPECIALIST
    state = reply_state(awaiting_reply=awaiting_reply, reply_needed=reply_needed, escalated=False)
    if not active or state != ReplyState.MANAGER or wait_hours is None:
        return SlaLane.OK
    if breached:
        return SlaLane.BREACHED
    if wait_hours >= at_risk_share * sla_hours:
        return SlaLane.AT_RISK
    return SlaLane.WAITING
