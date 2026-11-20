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
    # An open conversation the player is waiting on: answer it before any win-back message.
    open_request: "OpenRequest | None" = None


class OpenRequest(BaseModel):
    """The player's most urgent active conversation in the queue."""

    model_config = ConfigDict(frozen=True)

    conversation_id: str
    category: str | None
    priority: str
    wait_hours: float | None  # None: the manager wrote last


OPEN_REQUEST_ACTION = (
    "Сначала закрыть открытый запрос игрока в очереди, потом писать про возвращение."
)


class BirthdayItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    player: Player
    birthday: date
    days: int  # from the data date to the birthday: 0 today, negative = already passed
    next_action: str


BIRTHDAY_ACTION = "Поздравить лично, без бонуса и промо."


def _birthday_in(year: int, born: date) -> date:
    # 29 February is celebrated on 28 February in a common year.
    try:
        return born.replace(year=year)
    except ValueError:
        return date(year, 2, 28)


def birthdays(players: Iterable[Player], as_of: datetime, cfg: PolicyConfig) -> list[BirthdayItem]:
    """Players whose birthday is within ± the window of the data date (not the system clock).

    Restricted accounts are left out, like in the win-back list.
    """
    window = cfg.winback.birthday_window_days
    today = as_of.date()
    found: list[BirthdayItem] = []
    for player in players:
        attrs = player.attributes
        status = str(attrs.get("account_status") or "").strip().lower()
        born = _day(attrs.get("birthday"))
        if born is None or status in cfg.player.restricted_statuses:
            continue
        # The nearest occurrence: last year, this year or next year (handles new year).
        days = min(
            ((_birthday_in(today.year + shift, born) - today).days for shift in (-1, 0, 1)),
            key=abs,
        )
        if abs(days) <= window:
            found.append(
                BirthdayItem(player=player, birthday=born, days=days, next_action=BIRTHDAY_ACTION)
            )
    # Upcoming first (soonest), then the ones just passed (most recent first).
    found.sort(key=lambda b: (b.days < 0, abs(b.days), b.player.player_id))
    return found


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
    excluded: set[str] | frozenset[str] = frozenset(),
    open_requests: dict[str, OpenRequest] | None = None,
) -> list[WinbackItem]:
    """`excluded`: players with a risk signal in their conversations (e.g. responsible gaming)."""
    rules = cfg.winback
    today = as_of.date()
    items: list[WinbackItem] = []
    for player in players:
        attrs = player.attributes
        status = str(attrs.get("account_status") or "").strip().lower()
        if status in cfg.player.restricted_statuses or player.player_id in excluded:
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
        if now is not None and before and now >= before * cfg.player.deposit_spike_ratio:
            continue  # a sharp rise is a harm-risk signal, not a reason to reach out with promo
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
            reasons.append(
                Reason(code="winback.no_contact", text="Переписок с игроком ещё не было")
            )
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
        request = (open_requests or {}).get(player.player_id)
        items.append(
            WinbackItem(
                player=player,
                tier=tier,
                reasons=tuple(reasons),
                next_action=OPEN_REQUEST_ACTION if request else _action(tier, game),
                open_request=request,
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
