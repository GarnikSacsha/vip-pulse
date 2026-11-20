# 0013. Escalated work has its own SLA lane

Date: 2026-11-20. Status: accepted (Denys).

## Context

On the team lead board, a P0 responsible-gaming case whose player had waited 7 days sat in
«Всё ок · Ход за игроком» with the label «SLA на исходе». Two causes: the analysis said no reply
was needed, so the backend put the item into the `ok` lane; the card label was computed in the
browser from the wait time, independently of the lane.

## Decision

- New lane `specialist` («У специалиста»): every active item routed away from the manager
  (responsible-gaming specialist, security). It never lands in «Всё ок», whatever the model said
  about a reply. The card shows how long the player has waited.
- The lane is decided in `app/policy/sla.py` only. The card label is derived from the lane, so
  a lane and its label cannot disagree: «Всё ок» always reads «не ждёт ответа».
- «Всё ок» = active work where the player's turn is next, or the analysis says nothing needs an
  answer («спасибо, всё пришло»).

## Consequences

- A breached escalation shows in «У специалиста», not in «Горит»: the manager is not the one who
  must act. Its overdue flag and priority are unchanged, so it still counts in «Просрочен ответ».
