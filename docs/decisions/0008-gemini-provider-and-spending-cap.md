# Decision record: Gemini provider and spending cap

- Status: accepted (Denys, 2026-11-19), with one open point (API tier, below)
- Date: 2026-11-19
- Scope: `backend/app/analysis/llm/`, `backend/app/tasks/service.py`, `backend/app/config.py`

## Problem

The analysis needs a real model, and the project rules allow no paid calls without an explicit
cap. A triage run can be started from the CLI or the browser, several times, by different
processes. Task data belongs to the employer and must not leave the machine without a recorded
decision.

## Evidence

- `gemini-2.5-flash` answers HTTP 404 "no longer available to new users" and points to
  `gemini-3.8-flash`, which is the default model now. A key on the free tier gets HTTP 429 (no
  quota) for it: billing must be enabled.
- Paid-tier list prices of `gemini-3.8-flash` (Gemini pricing page, checked 2026-11-19):
  $0.75 per 1M input tokens, $3.75 per 1M output tokens (thinking included) until 2026-12-31,
  doubled from 2027-01-01.
- First live run (synthetic sample, 9 conversations, thinking off): ~600 input and ~150 output
  tokens per conversation, $0.0091 in total, 12 s, all answers passed schema and evidence
  validation. 250 conversations come to about $0.25. The worst-case reservation (~$0.009 per
  call) is ~9× the real cost, as intended.
- The same pricing page says that on the **free tier content is used to improve Google's
  products**, and on the paid tier it is not.

## Decision

- Gemini over its REST API (`generateContent`), standard library only: no new runtime dependency.
  JSON mode with the `LLMAnalysis` schema (refs inlined), temperature 0, thinking off by default
  (`GEMINI_THINKING_BUDGET`), at most 2048 output tokens.
- **Spending cap: $1 in total** (`LLM_BUDGET_USD=1.0`, Denys). It covers every run recorded in
  the database: each billed call goes to the `llm_calls` table, and each run starts from that
  total.
- Before every attempt the provider reserves the worst-case cost (prompt at 2 characters per
  token + the maximum output). If the reservation does not fit, the call is not sent; the
  conversation fails as `BudgetExceeded` and goes to human review. With parallel calls, all
  in-flight reservations count, so the cap holds.
- Real cost comes from the reported `usageMetadata`. When the response is lost after the
  request was sent (read timeout, reset, malformed body), the worst case is booked, because the
  request may still have been billed. A request that never left the machine (DNS, refused
  connection) costs nothing. Every reservation is settled exactly once.
- Retries: 429 and 5xx with backoff (`Retry-After` honoured, at most 3 retries); network errors
  likewise. Failures that the same request would repeat (other 4xx, blocked prompt, empty or
  truncated answer such as `MAX_TOKENS` or `SAFETY`, no budget) are permanent: fail closed, no
  retry, so they are not paid for twice. The API key is sent in a header and redacted from errors.
- The ledger is committed after every analysis, so a crash or Ctrl+C later in the run cannot
  hide spend. Ctrl+C during the parallel stage cancels queued calls and saves calls in flight.
- Up to `LLM_CONCURRENCY` (default 4) parallel calls per run. One run at a time per database:
  a lock inside the process and a lease row (`run_lease`) across processes, so the CLI and the
  API cannot spend the budget twice. A lease older than 30 minutes is treated as left by a
  crashed process and taken over.

## Open point

- **API tier for the task files.** On the free tier Google may use the content to improve its
  products. Recommended: a paid-tier key (billing enabled) with the $1 cap, or synthetic data
  only on a free key. Until Denys confirms the tier, task files are not sent to Gemini.

## Consequences

- Benefits: the cap cannot be exceeded by re-runs, restarts or parallel calls; a broken or
  exhausted provider never stops the queue (failed items go to review).
- Costs/risks: the worst-case reservation is pessimistic, so the last cents of the budget are
  not used. Prices are configuration and must be updated together with `GEMINI_MODEL`. The
  ledger lives in the SQLite file: deleting the database resets the recorded spend (the Google
  Cloud budget alert stays the outer guard).
- Revisit when: a second model or provider is added, or the budget changes.

## Alternatives not chosen

- `google-genai` SDK: a new dependency for one HTTP call.
- Counting calls instead of money: does not bound the cost of long conversations or thinking.
- A cap per run only: repeated runs would add up without limit.
