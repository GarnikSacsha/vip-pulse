"""Who to win back, and whose birthday is a reason to write. Decided in code, not by the model."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_policy
from app.api.queue import ACTIVE, SessionDep, _as_of, _player
from app.api.schemas import BirthdayOut, OpenRequestOut, ReasonOut, WinbackOut
from app.models import AnalysisRow, ConversationRow, PlayerRow, TaskRow
from app.policy.config import PolicyConfig
from app.policy.winback import OpenRequest, birthdays, winback
from app.schemas.analysis import Priority
from app.schemas.domain import Player

router = APIRouter(prefix="/api", tags=["winback"])

ManagerQuery = Annotated[list[str] | None, Query(max_length=64)]


def _players(session: Session, manager: list[str] | None) -> dict[str, PlayerRow]:
    query = select(PlayerRow)
    if manager:
        query = query.where(PlayerRow.manager_id.in_(manager))
    return {r.player_id: r for r in session.scalars(query)}


def _domain(rows: dict[str, PlayerRow]) -> list[Player]:
    return [
        Player(
            player_id=r.player_id,
            display_name=r.display_name,
            manager_id=r.manager_id,
            segment=r.segment,
            attributes=r.attributes or {},
        )
        for r in rows.values()
    ]


def _open_requests(session: Session) -> dict[str, OpenRequest]:
    """Per player, the most urgent active conversation that needs the manager.

    Needs the manager: priority P0/P1, or the player waits for an answer that is needed.
    """
    found: dict[str, tuple[tuple[str, float], OpenRequest]] = {}
    rows = session.execute(
        select(ConversationRow.player_id, TaskRow, AnalysisRow.result)
        .join(TaskRow, TaskRow.conversation_id == ConversationRow.conversation_id)
        .outerjoin(AnalysisRow, AnalysisRow.id == TaskRow.analysis_id)
    )
    for player_id, task, result in rows:
        if task.status not in {s.value for s in ACTIVE}:
            continue
        reply_needed = not any(r.get("code") == "sla.no_reply_needed" for r in task.reasons)
        waiting = task.awaiting_reply and reply_needed
        if task.priority not in (Priority.P0, Priority.P1) and not waiting:
            continue
        wait = task.wait_hours if task.awaiting_reply else None
        rank = (task.priority, -(wait or 0.0))
        category: Any = (result or {}).get("category")
        request = OpenRequest(
            conversation_id=task.conversation_id,
            category=category,
            priority=task.priority,
            wait_hours=wait,
        )
        if player_id not in found or rank < found[player_id][0]:
            found[player_id] = (rank, request)
    return {pid: request for pid, (_, request) in found.items()}


@router.get("/winback", response_model=list[WinbackOut])
def list_winback(
    session: SessionDep,
    policy: Annotated[PolicyConfig, Depends(get_policy)],
    manager: ManagerQuery = None,
) -> list[WinbackOut]:
    as_of = _as_of(session)
    if as_of is None:
        return []
    rows = _players(session, manager)

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

    items = winback(
        _domain(rows),
        last,
        as_of,
        policy,
        excluded=excluded,
        open_requests=_open_requests(session),
    )
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
            open_request=(
                OpenRequestOut(**item.open_request.model_dump()) if item.open_request else None
            ),
        )
        for item in items
    ]


@router.get("/birthdays", response_model=list[BirthdayOut])
def list_birthdays(
    session: SessionDep,
    policy: Annotated[PolicyConfig, Depends(get_policy)],
    manager: ManagerQuery = None,
) -> list[BirthdayOut]:
    """Birthdays within ± the window of the data date. Restricted accounts are left out."""
    as_of = _as_of(session)
    if as_of is None:
        return []
    rows = _players(session, manager)
    return [
        BirthdayOut(
            player=_player(rows[b.player.player_id]),
            birthday=b.birthday,
            days=b.days,
            next_action=b.next_action,
        )
        for b in birthdays(_domain(rows), as_of, policy)
    ]
