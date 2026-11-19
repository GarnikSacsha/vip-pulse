# Architecture

## Principle: facts in code, meaning from the LLM, decisions by policy

| Question | Who answers | Why |
|---|---|---|
| Who wrote last, how long is the player waiting, is the SLA breached? | Python (`app/policy/facts.py`) | Exact, cheap, reproducible. An LLM can miscount time. |
| What is the request about, how does the player feel, what is the next step, which messages prove it? | LLM (`app/analysis`) | Needs language understanding. |
| How urgent is it, who handles it, may we suggest an offer? | Rules (`app/policy/priority.py`) | Explainable, testable, tunable in `thresholds.yaml` without re-prompting. |

## Pipeline

```
players.csv ─┐
dialogs.json ┴─► adapter ─► pipeline checks ─► SQLite
                (format)    (dedupe, refs,     players / conversations / messages
                             import report)
                                   │
                ┌──────────────────┼────────────────────┐
                ▼                  ▼                    ▼
        facts (code)       LLM analysis           safety net (keywords)
        wait, SLA,         category, sentiment,   responsible gaming,
        pending msgs       next action, evidence  fraud, offers to
                           ids, confidence        vulnerable players
                │          strict schema, fail       │
                │          closed on bad evidence    │
                └──────────────────┬────────────────────┘
                                   ▼
                     priority decision P0–P3 + route + reasons
                     + human-review flag + safe next action
                                   ▼
                     work items (one per conversation) + audit trail
                     analyses cached by input hash
                                   ▼
             FastAPI  /api/queue · /api/conversations · /api/tasks
                                   ▼
             React UI: queue → conversation with evidence → status change
```

## Modules

| Path | Responsibility |
|---|---|
| `app/schemas/` | Pydantic contracts: normalized domain, taxonomy, strict LLM output |
| `app/ingestion/` | Adapter per source format, normalization, dedupe, import report, idempotent store |
| `app/policy/` | Facts, safety net, priority rules, `thresholds.yaml` |
| `app/analysis/` | Prompt, provider interface (`fake` now, Gemini next), validation service |
| `app/triage.py` | Pure glue: facts → analysis → policy → sorted queue (no database) |
| `app/tasks/` | Persisted triage: analysis cache, work items, status transitions, audit |
| `app/api/` | FastAPI routers and response models (the UI contract) |
| `app/cli.py` | `import` and `triage` commands |
| `frontend/src/` | React UI: typed API client, queue and conversation pages |

## Decisions

Full records with evidence and rejected alternatives are in [`docs/decisions/`](decisions/):
[0001 meaning / facts / rules](decisions/0001-llm-meaning-code-facts-rules-priority.md),
[0002 SQLite](decisions/0002-sqlite-local-persistence.md),
[0003 adapter per format](decisions/0003-adapter-per-source-format.md),
[0004 reference time](decisions/0004-dataset-reference-time.md),
[0005 safety net and simulated output](decisions/0005-safety-net-and-simulated-output.md),
[0006 languages, provider, dependencies](decisions/0006-conventions-and-dependencies.md),
[0007 work item lifecycle and analysis cache](decisions/0007-work-item-lifecycle-and-analysis-cache.md).

- **Adapter per format.** The real `dialogs.json` / `players.csv` were not available when the
  foundation was built. The internal model is ours; only a new adapter is needed for the real files.
- **"Now" = latest message in the dataset.** Demo data is historical; the wall clock would mark
  everything as overdue.
- **The LLM never sets priority.** It returns meaning plus evidence; rules turn that into urgency.
- **Fail closed.** Invalid JSON, unknown fields or evidence citing a message that is not in the
  conversation make the analysis `failed`. The item still gets a conservative priority from facts
  and is flagged for human review. One bad conversation never stops a batch.
- **Safety beats everything.** A keyword net runs on player messages even if the LLM is down or
  misses the signal. Responsible-gaming cases go to a specialist, offers are stripped from advice,
  and a manager who offered a bonus to such a player is flagged.
- **A money request alone is not critical.** It becomes P0 only when unanswered past
  `critical_wait_hours`.
- **A closing "thank you" is not a pending request.** Facts say the player spoke last; the LLM
  decides there is nothing to answer. Without an LLM result the policy stays conservative.
- **Thresholds are assumptions.** The task gives no evaluation rules, so every number lives in
  `thresholds.yaml`, commented as illustrative.
- **The manager owns the status.** Re-runs update the decision, not the status; a closed item
  reopens only when the player writes again. Analyses are cached, so tuning thresholds is free.

## Roadmap

1. **Done — stage 1:** backend foundation, ingestion, policy, LLM contract, offline provider, CLI, CI.
2. **Done — stage 2a (browser slice):** persisted analyses with cache, work items and audit, REST
   API, manager queue and conversation view.
3. **Next — stage 2b:** real data adapter + data contract, Gemini provider (retries, bounded
   concurrency, cost cap).
4. **Stage 2c (oversight views):** `/api/overview` and the team lead / head-of-VIP pages, computed
   from the same queue the managers see.
5. **Then:** gold set evaluation, visual polish, one-page brief, demo.
