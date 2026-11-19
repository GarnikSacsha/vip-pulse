# VIP Pulse AI

[![CI](https://github.com/GarnikSacsha/vip-pulse/actions/workflows/ci.yml/badge.svg)](https://github.com/GarnikSacsha/vip-pulse/actions/workflows/ci.yml)

A work queue for VIP managers, built from their conversations with players. It finds unanswered
requests and service problems, puts the most urgent first and suggests the next step. Every
conclusion points to the exact messages it is based on, and responsible-gaming cases go to a
human specialist.

> **Status:** the full path works end to end on synthetic data: import → analysis → prioritised
> inbox in the browser → conversation with evidence → status change with history. By default
> analysis is done by an offline heuristic (the UI says so on every screen); Gemini is built in and
> switched on with an API key, under a hard spending cap.
> See [what is done and what is next](#status).

## Who it is for

| Role | What they get |
|---|---|
| **VIP manager** (primary) | "Who do I answer first and what do I say?" A three-pane inbox: the queue sorted by urgency and waiting time, the conversation, and its analysis with the reason for each priority, a suggested next step and numbered links to the messages that justify it. A player tab shows the dossier. |
| Team lead (`/lead`) | SLA lanes (Горит / Скоро нарушится / Ждёт / Всё ок), escalations, manager mistakes such as offers to vulnerable players, workload per manager with a link to their queue. |
| Head of VIP (`/overview`) | Headline numbers, replies within SLA, categories and channels, and where the numbers come from. Computed from the same queue, nothing hard-coded. |

## How it decides

- **Facts in code:** who wrote last, how long the player is waiting, SLA breach, usual response time.
- **Meaning from the LLM:** category, sentiment, next action and the ids of the messages that
  support it. The answer is validated against a strict schema; an answer citing a message that does
  not exist is rejected.
- **Priority by explicit rules:** P0–P3 with a list of reasons, tunable in
  [`thresholds.yaml`](backend/app/policy/thresholds.yaml) without touching code or prompts.
- **Safety first:** responsible-gaming and fraud signals are caught even without the LLM. Bonuses
  are never suggested to a vulnerable player, and a manager who offered one is flagged.
- **The manager owns the status:** re-analysis never closes their work; a closed item reopens only
  when the player writes again.

Details: [architecture](docs/architecture.md) · [decision records](docs/decisions/).

## Quick start (Windows PowerShell)

Requirements: Python 3.11+ (`py`), Node 24.

**1. Backend: install, import the synthetic sample, analyse, start the API**

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item ..\.env.example .env

.\.venv\Scripts\python.exe -m app.cli import --players ..\data\sample\players.csv --dialogs ..\data\sample\dialogs.json
.\.venv\Scripts\python.exe -m app.cli triage
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --reload
```

The API runs on <http://127.0.0.1:8000>, interactive docs at `/docs`.

**2. Frontend: in a second terminal**

```powershell
cd frontend
npm ci
npm run dev
```

Open <http://localhost:5173>. Vite proxies `/api` to the backend.

macOS / Linux: the same steps with `python3 -m venv .venv` and `.venv/bin/python`.
If the console shows broken Cyrillic, run `$env:PYTHONIOENCODING = "utf-8"` first.

### Task files

The task files go to `data/input/` (git-ignored, never committed). Import them with the `task_v1`
adapter into a separate database ([decision 0010](docs/decisions/0010-task-data-adapter.md)):

```powershell
.\.venv\Scripts\python.exe -m app.cli import --adapter task_v1 --players ..\data\input\players.csv --dialogs ..\data\input\dialogs.json --database-url sqlite:///./task_data.db
.\.venv\Scripts\python.exe -m app.cli triage --database-url sqlite:///./task_data.db
```

### What to look at

1. **Inbox (`/queue`):** three P0 items on top. A withdrawal unanswered for 27 h (its ring is
   solid red: SLA breached), a possible account takeover routed to security, and a player asking
   to be blocked who was offered free spins (flagged "Бонус уязвимому игроку"). Press `j` / `k`
   to walk through the queue; the conversation and its analysis open next to the list.
2. **Open d-004:** hover the numbered pill next to the summary: the cited message lights up in
   the timeline. A red "do not offer bonuses" warning and the route to a responsible-gaming
   specialist sit above. With the offline heuristic the analysis card is hatched and labelled «демо».
3. **Open d-001, tab «Игрок»:** the dossier lists both of the player's conversations and the tone
   trend between them.
4. **Take an item in progress, then resolve it:** the history records who did what, with the note.
5. **Team (`/lead`):** d-001 is in the «Горит» lane; d-004 and d-009 are escalations; mgr-01
   opens their own queue. **Overview (`/overview`):** 5 of 9 conversations need action, 3 of 4
   waiting players are inside the SLA, and the page says the categories come from the demo heuristic.
6. **Change a threshold** in `thresholds.yaml` (for example `critical_wait_hours: 24 → 48`) and run
   `app.cli triage` again: priorities change, cached analyses are reused, nothing is re-sent to the model.

The CLI prints the same queue the browser shows:

```
P0  d-001  p-001   telegram  withdrawal             27h  manager         Проверить статус вывода у платёжной команды…
    why: Финансовый запрос без ответа 27 ч (порог 24 ч); Рекомендована эскалация (эвристика fake, без модели)
P0  d-004  p-004   telegram  responsible_gaming       -  rg_specialist   Передать специалисту по ответственной игре… [review] [offer_to_vulnerable_player]
    why: Сигнал ответственной игры у игрока; Менеджер предложил бонус игроку с сигналом ответственной игры; …
```

### Run with Gemini

Put the key in `backend/.env` and switch the provider:

```
LLM_PROVIDER=gemini
GEMINI_API_KEY=...
LLM_BUDGET_USD=1.0
```

Then `app.cli triage` (or the API) analyses with Gemini. Every billed call is written to the
`llm_calls` table; a call that could push the total over `LLM_BUDGET_USD` is not sent, and the
conversation goes to human review instead. The CLI prints the spend of the run and what is left.
Use a paid-tier key for task data: on the free tier Google may use the content to improve its
products ([decision 0008](docs/decisions/0008-gemini-provider-and-spending-cap.md)).

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/meta` | Dataset date, provider with its label and budget, counts by status and priority |
| GET | `/api/queue?status=&priority=&route=&manager=&player=&overdue=` | Work items, most urgent first; `overdue` = active and past the channel SLA; `sla_lane` per item |
| GET | `/api/overview` | Totals, workload per manager, categories, channels, routes, analysis coverage |
| GET | `/api/conversations/{id}` | Messages (evidence and pending marked), analysis, task, reasons, facts |
| PATCH | `/api/tasks/{id}` | Change status (`open`, `in_progress`, `resolved`) with an optional note |
| GET | `/api/tasks/{id}/audit` | Status history |
| POST | `/api/triage/run` | Re-run analysis; cached conversations are not re-sent; reports spend; 409 while a run is in progress |
| GET | `/health` | Liveness |

## Checks

```powershell
# backend
cd backend
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .

# frontend
cd frontend
npm run lint; npm run typecheck; npm test; npm run build
```

CI runs all of them (Python 3.12 and 3.14, Node 24) and blocks commits that contain `.env` or task data.

## Results on the task files

40 conversations, 50 players (`data/input/`, not in Git), analysed by `gemini-3.8-flash` for
$0.052, 40/40 valid answers.

- **Queue:** 9 × P0, 10 × P1, 4 × P2, 17 × P3; 6 conversations routed to the responsible-gaming
  specialist.
- **Manager mistakes flagged:** a bonus "to win it back" for a player deep in losses, cashback
  offered to a player asking to be blocked, a reload and a limit raise offered to a player who set
  a limit. A manager who refused bonuses and set a limit is not flagged.
- **Found by the model, not by keywords:** a VIP called by the wrong name twice, inaccurate bonus
  terms, a player chasing losses with bonuses.
- **Missed:** a request for a bonus on the wife's account with the same card (possible
  multi-accounting) got a low priority. Bonus abuse is not a rule yet.

## Measuring analysis quality

`data/sample/gold.yaml` holds hand labels for the 9 sample conversations (every acceptable answer
per field). `eval` scores the analyses already stored by `triage`; it makes no LLM calls.

```powershell
.\.venv\Scripts\python.exe -m app.cli eval --gold ..\data\sample\gold.yaml
```

Result on 2026-11-19 (category, needs action, safety flag, tone, evidence):

| Analyses by | Category | Action | Safety flag | Tone | Evidence |
|---|---|---|---|---|---|
| Gemini (`gemini-3.8-flash`) | 9/9 | 9/9 | 9/9 | 9/9 | 9/9 |
| Offline heuristic (`fake`) | 9/9 | 9/9 | 9/9 | 8/9 | 9/9 |

What this shows: the pipeline, the contract and the evidence check work with a real model. What it
does not show: model quality. The sample was written to cover edge cases of import and policy, and
keyword matching solves it almost as well. A meaningful measurement needs harder cases (implicit
responsible-gaming signals, sarcasm, two topics in one conversation) and 8–12 labelled real
conversations once the task files arrive. The labels were drafted by the agent and need review.

## Project layout

```
backend/app/
  schemas/      Pydantic contracts: domain model, taxonomy, strict LLM output
  ingestion/    format adapters, normalization, dedupe, import report, store
  policy/       facts, safety net, priority rules, thresholds.yaml
  analysis/     prompt, LLM providers (fake, Gemini) with spending meter, validation
  tasks/        persisted triage, analysis cache, work items, audit
  api/          FastAPI routers and response models
  cli.py        import / triage commands
frontend/src/
  api/          typed client mirroring backend/app/api/schemas.py
  pages/        inbox (queue + conversation panes), team lead, overview
  components/   badges, pulse indicator, dossier, oversight tiles and panels
frontend/public/fonts/  self-hosted Inter Variable and JetBrains Mono (OFL)
  lib/          formatting, labels, data loading hook
data/
  sample/       synthetic fixture, one edge case per dialog (committed)
  input/        real task files (git-ignored)
docs/
  architecture.md, decisions/
```

## Status

| Done | Next |
|---|---|
| Import with validation report, dedupe, idempotent re-import | Labelled task conversations to measure quality |
| Deterministic facts, SLA, safety net, priority with reasons | Multi-account / bonus-abuse signal (missed by the model on the task files) |
| Strict LLM contract, fail-closed evidence check, prompt-injection fencing | Screenshots, one-page brief and demo video |
| Analysis cache, work items, status history | |
| Three-pane inbox, evidence pills, player dossier, pulse indicator | |
| Gold set and `eval` command (no LLM calls) | |
| Gemini provider: retries, parallel calls, $1 spending cap with a ledger | |
| Team lead SLA lanes and head-of-VIP view | |
| Task files: `task_v1` adapter, analysed by Gemini | |
| Player signals: account restrictions, payment problems, deposit trends | |

## Data and secrets

Only synthetic data is committed (`data/sample/`). Files supplied with the task go to
`data/input/`, which is git-ignored. Secrets live in `backend/.env`, which is also git-ignored.
