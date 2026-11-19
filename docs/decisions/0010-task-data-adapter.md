# 0010. Adapter for the task files (`task_v1`)

Date: 2026-11-19. Status: accepted.

## Context

The task files arrived (`data/input/`, git-ignored, internal): 50 players, 40 dialogs, 166
messages, `as_of` 2026-11-18. Their shape differs from the synthetic sample.

## Decision

A new adapter `task_v1`; the domain model does not change (rule from 0003).

- Messages have no ids: `<dialog_id>-<n>`, 1-based in file order, stable on re-import.
- Timestamps have no timezone: UTC is assumed and reported once per file, not per message.
- `manager` (a name) is the manager id; `status` (VIP / pre-VIP) is the segment; there is no
  display name, so the UI shows the player id.
- `geo` is exposed as country (it is a region such as CIS) and `vip_since` as the start date in
  the dossier. Every other column (account status, deposits, withdrawals, bonuses, logins) is kept
  in the player's attributes.
- Dataset "now" stays the latest message (2026-11-18 14:02 UTC), consistent with 0004; the file's
  `as_of` is a date only.
- Tests use an invented fixture of the same shape (`backend/tests/fixtures/task_v1/`); the real
  files never enter tests or Git.

## Consequences

- Import: 50/50 players, 40/40 dialogs, 166 messages, 0 errors, 1 warning (timezone).
- The policy does not read player metrics yet. Bonus offers to players with `limit_set` or
  `self_excluded` are not flagged unless the conversation itself has a responsible-gaming signal.
  Next step: deterministic player signals from `account_status` and payment metrics.
- Sending the task files to Gemini stays blocked until the API tier is confirmed (0008).
