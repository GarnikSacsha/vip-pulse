"""Who to win back: players who went silent or are slipping, found in code.

Built from the player's profile (last login, deposits) and the date of the last conversation,
for every player, including those the manager never wrote to. Players with a restricted account
(self-exclusion, limits) are never listed: winning them back would be harm, not service.
"""

from collections.abc import Iterable
from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from app.policy.config import PolicyConfig
from app.policy.player import _number, _usd
from app.policy.priority import Reason
from app.schemas.domain import Player


class Tier(StrEnum):
    URGENT = "urgent"  # went silent or stopped depositing
    ATTENTION = "attention"  # deposits fell sharply
    INTRODUCE = "introduce"  # active, but the manager never wrote


class WinbackItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    player: Player
    tier: Tier
    reasons: tuple[Reason, ...]
    next_action: str
    last_login_days: int | None
    last_contact_days: int | None  # None: no conversation at all
    deposits_30d_usd: float | None
    deposits_prev_30d_usd: float | None


def _day(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def _action(tier: Tier, game: str | None) -> str:
    if tier == Tier.URGENT:
        hook = f" и вспомнить любимую игру ({game})" if game else ""
        return (
            f"Написать лично: спросить, всё ли в порядке{hook}. Бонус — только если нет "
            "признаков риска для игрока."
        )
    if tier == Tier.ATTENTION:
        return "Узнать, что изменилось: выводы, сервис, другое казино? Без давления и промо."
    return "Познакомиться: короткое личное сообщение от менеджера, без промо."


def winback(
    players: Iterable[Player],
    last_contact: dict[str, datetime],
    as_of: datetime,
    cfg: PolicyConfig,
) -> list[WinbackItem]:
    rules = cfg.winback
    today = as_of.date()
    items: list[WinbackItem] = []
    for player in players:
        attrs = player.attributes
        status = str(attrs.get("account_status") or "").strip().lower()
        if status in cfg.player.restricted_statuses:
            continue

        reasons: list[Reason] = []
        tier: Tier | None = None

        login = _day(attrs.get("last_login_at"))
        login_days = (today - login).days if login else None
        if login_days is not None and login_days >= rules.silent_days:
            reasons.append(Reason(code="winback.silent", text=f"Не заходил {login_days} дн."))
            tier = Tier.URGENT

        now = _number(attrs.get("deposits_30d_usd"))
        before = _number(attrs.get("deposits_prev_30d_usd"))
        if now is not None and before:
            if now == 0:
                reasons.append(
                    Reason(
                        code="winback.stopped_depositing",
                        text=f"Перестал вносить депозиты: было {_usd(before)} за 30 дней",
                    )
                )
                tier = Tier.URGENT
            elif now < before * cfg.player.deposit_drop_share:
                reasons.append(
                    Reason(
                        code="winback.deposit_drop",
                        text=f"Депозиты за 30 дней упали: {_usd(before)} → {_usd(now)}",
                    )
                )
                tier = tier or Tier.ATTENTION

        contact = last_contact.get(player.player_id)
        contact_days = (today - contact.date()).days if contact else None
        if contact is None:
            reasons.append(Reason(code="winback.no_contact", text="Менеджер ещё не писал игроку"))
            tier = tier or Tier.INTRODUCE
        elif contact_days is not None and contact_days >= rules.no_contact_days and tier:
            reasons.append(
                Reason(
                    code="winback.old_contact", text=f"Последний контакт {contact_days} дн. назад"
                )
            )

        if tier is None:
            continue
        game = str(attrs.get("favorite_game") or "").strip() or None
        items.append(
            WinbackItem(
                player=player,
                tier=tier,
                reasons=tuple(reasons),
                next_action=_action(tier, game),
                last_login_days=login_days,
                last_contact_days=contact_days,
                deposits_30d_usd=now,
                deposits_prev_30d_usd=before,
            )
        )

    order = {Tier.URGENT: 0, Tier.ATTENTION: 1, Tier.INTRODUCE: 2}
    # Most at stake first: the larger of the two 30-day deposit totals.
    items.sort(
        key=lambda i: (
            order[i.tier],
            -max(i.deposits_30d_usd or 0, i.deposits_prev_30d_usd or 0),
            i.player.player_id,
        )
    )
    return items
