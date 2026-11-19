# Decision record: work item lifecycle and analysis cache

- Status: accepted
- Date: 2026-11-19
- Scope: `backend/app/tasks/service.py`, `backend/app/analysis/prompts.py`

## Problem

1. Triage runs repeatedly (new data, changed thresholds). What happens to a status the manager
   set? Should a re-run close or reopen work by itself?
2. With a paid model, every re-run must not re-send every conversation.

## Evidence

- Silently closing an item the manager is working on, or reopening a resolved one, makes the
  queue untrustworthy.
- A player writing again after "resolved" is the most common reason a case is not really over.
- The first prompt carried the wait time, which depends on the dataset's reference "now": one new
  message anywhere changed the cache key of every conversation (caught by
  `test_cache_key_does_not_depend_on_reference_time`).

## Decision

- One work item per conversation. New items: P0–P2 → `open`, P3 → `no_action`.
- Re-runs update the decision (priority, reasons, next step) but keep the status, with two
  exceptions made by the system and written to the audit trail: `resolved` → `open` when the player
  wrote after the item was last seen, and `no_action` → `open` when the policy now requires action.
- Manual transitions: open ↔ in_progress, open/in_progress → resolved, resolved/no_action → open.
  `no_action` is never a manual target. Every change is audited with actor and optional note.
- Analyses are cached by a hash of provider, model, prompt version, response schema and prompt
  text. Only successful analyses are reused; failures are retried on the next run.
- The prompt contains only time-independent facts; wait time and SLA stay in code.

## Consequences

- Benefits: the manager's work is never overwritten; threshold changes are instant and free;
  re-runs cost only the changed conversations.
- Costs/risks: an item stays `open` if the policy later says P3; the manager closes it. No
  authentication yet, so the actor is a demo role.
- Revisit when: real users and authentication arrive, or managers ask for auto-close.

## Alternatives not chosen

- Recompute status from the policy on every run: overwrites human decisions.
- No cache: every threshold tweak would re-send the whole dataset to a paid model.
