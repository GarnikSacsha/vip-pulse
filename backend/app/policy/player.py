"""Signals from the player's profile: account restrictions and payment metrics.

Read from the player's attributes (columns of players.csv kept by the adapter). Missing or
unparsable values give no signal: a format without these columns simply has none. The LLM never
sees or decides any of this.
"""

from pydantic import BaseModel, ConfigDict

from app.policy.config import PolicyConfig, mentions_offer
from app.policy.priority import Reason
from app.schemas.domain import Conversation, Player, SenderRole


class PlayerSignals(BaseModel):
    model_config = ConfigDict(frozen=True)

    # account_status from the restricted list ("self_excluded", "limit_set"), else None
    restricted: str | None = None
    self_excluded: bool = False
    # Manager messages with an offer while the account is restricted.
    offer_message_ids: tuple[str, ...] = ()
    # Money stuck or failing: the player cannot deposit or is waiting for a payout.
    money_reasons: tuple[Reason, ...] = ()
    # Retention and risk context: deposit drop (churn) or spike (possible harm).
    trend_reasons: tuple[Reason, ...] = ()
    needs_review: bool = False

    @property
    def reasons(self) -> tuple[Reason, ...]:
        return self.money_reasons + self.trend_reasons


def _number(value: object) -> float | None:
    try:
        return float(str(value).strip().replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return None


def _usd(value: float) -> str:
    return "$" + f"{value:,.0f}".replace(",", " ")


def is_deposit_spike(now: float, before: float, cfg: PolicyConfig) -> bool:
    """A sharp rise: by the ratio and by at least the minimum amount (both in thresholds.yaml)."""
    rules = cfg.player
    return now > before * rules.deposit_spike_ratio and now - before >= rules.deposit_spike_min_usd


def player_signals(player: Player | None, conv: Conversation, cfg: PolicyConfig) -> PlayerSignals:
    if player is None:
        return PlayerSignals()
    attrs = player.attributes
    rules = cfg.player

    status = str(attrs.get("account_status") or "").strip().lower()
    restricted = status if status in rules.restricted_statuses else None
    offers: tuple[str, ...] = ()
    if restricted:
        offers = tuple(
            m.message_id
            for m in conv.messages
            if m.sender_role == SenderRole.MANAGER and mentions_offer(m.text, cfg.offers)
        )

    money: list[Reason] = []
    failed = _number(attrs.get("failed_deposits_7d"))
    if failed is not None and failed >= rules.failed_deposits_7d:
        money.append(
            Reason(
                code="player.failed_deposits", text=f"Неудачных депозитов за 7 дней: {failed:.0f}"
            )
        )
    pending = _number(attrs.get("pending_withdrawal_usd"))
    if pending is not None and pending >= rules.pending_withdrawal_usd:
        money.append(
            Reason(code="player.pending_withdrawal", text=f"Вывод в ожидании: {_usd(pending)}")
        )

    trend: list[Reason] = []
    review = False
    now = _number(attrs.get("deposits_30d_usd"))
    before = _number(attrs.get("deposits_prev_30d_usd"))
    if now is not None and before:
        if now < before * rules.deposit_drop_share:
            trend.append(
                Reason(
                    code="player.deposit_drop",
                    text=f"Депозиты за 30 дней упали: {_usd(before)} → {_usd(now)}",
                )
            )
        elif is_deposit_spike(now, before, cfg):
            review = True
            trend.append(
                Reason(
                    code="player.deposit_spike",
                    text=(
                        f"Депозиты за 30 дней выросли: {_usd(before)} → {_usd(now)}, "
                        "проверить на риск для игрока"
                    ),
                )
            )

    return PlayerSignals(
        restricted=restricted,
        self_excluded=restricted == "self_excluded",
        offer_message_ids=offers,
        money_reasons=tuple(money),
        trend_reasons=tuple(trend),
        needs_review=review,
    )
