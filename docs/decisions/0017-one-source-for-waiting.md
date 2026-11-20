# 0017. One source of truth for "the player is waiting for the manager"

Date: 2026-11-20. Status: accepted (Denys).

## Context

"The player wrote last, but no answer is needed" (the analysis, reason `sla.no_reply_needed`)
reached the SLA lanes only. Every other number used the raw fact: a «ок, спасибо» from a week ago
showed as «Дольше всех ждёт 7 д», «SLA нарушен» in the card and the review group, while the same
conversation sat in «Всё ок». «Просрочен ответ» counted escalated cases too, so it did not match
the «Горит» lane.

## Decision

- `app.policy.sla.reply_state` decides who owes the next message: `players_turn`,
  `no_reply_needed`, `manager`, `specialist`. An escalated case is always `specialist`, never
  "no reply needed".
- Everything derives from it: `awaiting_reply` and `wait_hours` in the queue and the
  conversation facts, `sla_breached` (never for `no_reply_needed`), the lanes, `overdue`,
  «Дольше всех ждёт», «Ответ в рамках SLA», overdue per channel and per manager.
- `overdue` = the «Горит» lane: the manager owes a reply past the channel's SLA. Escalations are
  counted in «У специалиста» and «Эскалации», not in «Просрочен ответ»; the tile says so.
- The card shows «Ответ не требуется (AI)» with the time since the player's last message
  (`raw_wait_hours`), and the channel SLA as «сейчас не применяется».

## Consequences

- Invariant, tested on the sample: KPI «Просрочен ответ» = «Горит» lane = sum of overdue per
  channel = sum per manager.
