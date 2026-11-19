# 0012. Personal-contact alerts and the win-back list

Date: 2026-11-19. Status: accepted (Denys).

## Context

On the task files the model gave a low priority to a request for a bonus on another account paid
with the same card. Denys: this must not block the player, but the manager must be notified and
contact the player personally. The brief also names winning back silent players as core VIP work,
and 10 of 50 players had no conversation at all, so the queue never showed them.

## Decision

- **Alerts.** A player message about another account or a shared card (keywords in
  `thresholds.yaml`, `safety.multi_account`) raises the reason `alert.multi_account`: at least
  P1, next step «связаться лично и уточнить», no block, no escalation, not a manager mistake.
  The API exposes `alerts` on queue items and tasks; the UI shows a tag in the queue, a notice in
  the conversation and a «Нужен личный контакт» group for the team lead.
- **Win-back list** (`/api/winback`, page «Кого вернуть»), decided in code for every player:
  urgent — no login for `winback.silent_days` (14) or deposits fell to zero; attention — deposits
  below half of the previous 30 days; introduce — active but never contacted. Ordered by tier and
  then by the 30-day deposit amount at stake. Restricted accounts (self-exclusion, limits) are
  never listed. The next step is a template without promo pressure.
- **SLA lane fix.** When the analysis says no reply is needed, the lane is «Всё ок» instead of
  pulsing as at risk.

## Consequences

- On the task files: 1 alert, 16 players to win back (4 urgent, 5 attention, 7 introduce).
- Keywords are a safety net: new wording needs new entries. A model field for bonus abuse,
  checked by code, is the next step.
