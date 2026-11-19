"""Who to win back: silent or slipping players, including those without any conversation."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.api.deps import get_policy
from app.api.queue import SessionDep, _as_of, _player
from app.api.schemas import ReasonOut, WinbackOut
from app.models import ConversationRow, PlayerRow, TaskRow
from app.policy.config import PolicyConfig
from app.policy.winback import winback
from app.schemas.domain import Player

router = APIRouter(prefix="/api", tags=["winback"])


@router.get("/winback", response_model=list[WinbackOut])
def list_winback(
    session: SessionDep,
    policy: Annotated[PolicyConfig, Depends(get_policy)],
    manager: Annotated[list[str] | None, Query(max_length=64)] = None,
) -> list[WinbackOut]:
    as_of = _as_of(session)
    if as_of is None:
        return []
    query = select(PlayerRow)
    if manager:
        query = query.where(PlayerRow.manager_id.in_(manager))
    rows = {r.player_id: r for r in session.scalars(query)}

    last: dict = {}
    latest_id: dict[str, str] = {}
    contacts = session.execute(
        select(
            ConversationRow.player_id,
            ConversationRow.conversation_id,
            ConversationRow.last_message_at,
        )
    )
    for player_id, conv_id, at in contacts:
        if player_id not in last or at > last[player_id]:
            last[player_id], latest_id[player_id] = at, conv_id

    # Players with a risk signal in any conversation are never offered for win-back.
    risky = {"safety.responsible_gaming", "player.deposit_spike"}
    excluded = set()
    for player_id, route, reasons in session.execute(
        select(ConversationRow.player_id, TaskRow.route, TaskRow.reasons).join(
            TaskRow, TaskRow.conversation_id == ConversationRow.conversation_id
        )
    ):
        if route == "rg_specialist" or any(r.get("code") in risky for r in reasons or []):
            excluded.add(player_id)

    players = [
        Player(
            player_id=r.player_id,
            display_name=r.display_name,
            manager_id=r.manager_id,
            segment=r.segment,
            attributes=r.attributes or {},
        )
        for r in rows.values()
    ]
    return [
        WinbackOut(
            player=_player(rows[item.player.player_id]),
            tier=item.tier.value,
            reasons=[ReasonOut(code=r.code, text=r.text) for r in item.reasons],
            next_action=item.next_action,
            last_login_days=item.last_login_days,
            last_contact_days=item.last_contact_days,
            deposits_30d_usd=item.deposits_30d_usd,
            deposits_prev_30d_usd=item.deposits_prev_30d_usd,
            favorite_game=(rows[item.player.player_id].attributes or {}).get("favorite_game"),
            latest_conversation_id=latest_id.get(item.player.player_id),
        )
        for item in winback(players, last, as_of, policy, excluded=excluded)
    ]
