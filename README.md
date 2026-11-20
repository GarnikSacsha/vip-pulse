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

One-page brief (in Russian): [docs/brief.md](docs/brief.md).

## Who it is for

| Role | What they get |
|---|---|
| **VIP manager** (primary) | "Who do I answer first and what do I say?" A three-pane inbox: the queue sorted by urgency and waiting time, the conversation, and its analysis with the reason for each priority, a suggested next step and numbered links to the messages that justify it. «Связаться лично» alerts (e.g. a possible second account). «Кого вернуть» (`/winback`): silent and slipping players, including those never contacted; a card points to the player's open request first; birthdays near the data date as a reason to write (no promo). The «Игрок» tab shows every `players.csv` column: account status, money, activity, personal. |
| Team lead (`/lead`) | SLA lanes (Горит / Скоро нарушится / Ждёт / У специалиста / Всё ок), escalations, manager mistakes by manager (bonus rules in code plus mistakes the analysis finds, each linked to the message), workload per manager with a mistakes column and a link to their queue. |
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
- **Manager mistakes:** rules count what they can (a bonus to a vulnerable or restricted player,
  a reply later than the channel SLA, a player waiting past the SLA now; labelled «посчитано
  кодом», [0019](docs/decisions/0019-rule-counted-mistakes.md)). The analysis adds the rest from a closed list (brush-off reply, rude tone, wrong
  information, question left unanswered, wrong name, broken promise, pressure to keep playing),
  each citing the manager's message; an answer without such a citation is rejected.

- **One source for waiting:** «the player waits for the manager» is decided once
  ([0017](docs/decisions/0017-one-source-for-waiting.md)): a «спасибо» the analysis marks as needing
  no answer is never a wait or an SLA breach, and an escalated case waits for the specialist.
  «Просрочен ответ» is exactly the «Горит» lane.

**Roles are a demo, not authorisation.** The header switcher («Я: менеджер» / «Тимлид» /
«Руководитель», labelled «демо-режим») only filters what the browser shows: a manager sees their
own queue and win-back list (escalated cases show a neutral step; the lead sees the analysis);
the head of VIP sees «Обзор», «Команда» and a read-only queue
([0018](docs/decisions/0018-head-read-only-queue.md)). The API has no sign-in and serves every
player to any caller ([0015](docs/decisions/0015-demo-roles.md)).

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
3. **Open d-001, tab «Игрок»:** the player card (account, money, activity, personal; a dash where
   the sample has no column) and both of the player's conversations with the tone trend. On the
   «Разбор» tab, «Ошибки менеджера» shows «Обещал вернуться и не вернулся» with a pill to the message.
4. **Take an item in progress, then resolve it:** the history records who did what, with the note.
5. **Team (`/lead`):** d-001 is in the «Горит» lane, d-004 and d-009 are «У специалиста»;
   «Ошибки менеджеров» lists, per manager, d-004 (bonus) and d-001 (waiting past the SLA) as
   «посчитано кодом», d-001 and d-005 by the analysis, each linked to the message;
   mgr-01 opens their own queue. **Overview (`/overview`):** 5 of 9 conversations need action,
   2 of 3 players waiting for a manager are inside the SLA, and the page says the categories come from the demo
   heuristic.
6. **Switch the role** in the header to «Я: mgr-01»: only their queue and «Кого вернуть» remain.
7. **Change a threshold** in `thresholds.yaml` (for example `critical_wait_hours: 24 → 48`) and run
   `app.cli triage` again, or `POST /api/triage/run` from `/docs`: the API re-reads the file, so
   no restart is needed. Priorities change, cached analyses are reused, nothing is re-sent to the
   model.

The CLI prints the same queue the browser shows:

```
P0  d-001  p-001   telegram  withdrawal             27h  manager         Проверить статус вывода у платёжной команды…
    why: Финансовый запрос без ответа 27 ч (порог эскалации финансового запроса: 24 ч); Рекомендована эскалация (эвристика fake, без модели)
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
| GET | `/api/winback?manager=` | Players to win back: tier, reasons, next step, latest conversation, open request to answer first |
| GET | `/api/birthdays?manager=` | Birthdays within ± `winback.birthday_window_days` of the data date; restricted accounts left out |
| GET | `/api/overview` | Totals, workload per manager, categories, channels, routes, analysis coverage |
| GET | `/api/conversations/{id}` | Messages (evidence and pending marked), analysis, task, reasons, facts |
| PATCH | `/api/tasks/{id}` | Change status (`open`, `in_progress`, `resolved`) with an optional note |
| GET | `/api/tasks/{id}/audit` | Status history |
| POST | `/api/triage/run` | Re-run analysis with the current `thresholds.yaml`; cached conversations are not re-sent; reports spend; 409 while a run is in progress. JSON only (415 otherwise), so a page on another site cannot start a paid run |
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

40 conversations, 50 players (`data/input/`, not in Git), analysed by `gemini-3.8-flash` with
prompt v4 on 2026-11-20 for $0.062, 40/40 valid answers (all runs on this database: $0.115 of
the $0.96 cap).

- **Queue:** 10 × P0, 7 × P1, 6 × P2, 17 × P3; 6 conversations routed to the responsible-gaming
  specialist, 1 to security. 10 conversations are in «Горит»; «Просрочен ответ», the per-channel
  and the per-manager overdue numbers all equal 10 ([decision 0017](docs/decisions/0017-one-source-for-waiting.md)).
- **Manager mistakes: 36 in 18 conversations** (managers are compared by conversations,
  [0020](docs/decisions/0020-mistakes-by-conversation.md)). By rule: 3 bonuses to a vulnerable or
  restricted player (a bonus for a player writing about heavy losses, cashback for a player asking
  to be blocked, a deposit bonus and a hint at a higher limit for a player who set a limit),
  1 bonus credited before the security check ([0021](docs/decisions/0021-bonus-before-security-check.md)),
  2 replies later than the channel SLA, 10 players waiting past the SLA now. By the model, each citing the manager's
  message: 7 questions left unanswered, 5 pressure to keep playing, 4 brush-off replies, 2 rude
  tone, 1 broken promise, 1 wrong name. A manager who refused bonuses and set a limit is not
  flagged.
- **A request for a bonus on another account paid with the same card** (possible
  multi-accounting): with prompt v3 the model gave it a low priority and the rule raised
  «Связаться лично» (P1). With prompt v4 the model flags it as fraud, so it goes to security as P0
  and the alert yields to security, as decided in [0012](docs/decisions/0012-alerts-and-winback.md).
- **Who to win back:** 14 players, 4 urgent (no login for 2–4 weeks or stopped depositing; two of
  them have no conversation yet), 5 with a sharp deposit drop, 5 active VIPs never contacted. Two
  players with a sharp deposit rise are left out: that is a harm-risk signal, not a reason for promo.

## Measuring analysis quality

`data/sample/gold.yaml` holds hand labels for the 9 sample conversations (every acceptable answer
per field). `eval` scores the analyses already stored by `triage`; it makes no LLM calls.

```powershell
.\.venv\Scripts\python.exe -m app.cli eval --gold ..\data\sample\gold.yaml
```

Result on 2026-11-20, prompt v4 (category, needs action, safety flag, tone, evidence, manager
mistakes):

| Analyses by | Category | Action | Safety flag | Tone | Evidence | Mistakes |
|---|---|---|---|---|---|---|
| Gemini (`gemini-3.8-flash`) | 9/9 | 9/9 | 9/9 | 9/9 | 9/9 | 8/9 |
| Offline heuristic (`fake`) | 9/9 | 9/9 | 9/9 | 8/9 | 9/9 | 9/9 |

Gemini missed the unanswered «когда проверят документы?» in d-005. The heuristic's two mistake
rules were written for these examples, so its 9/9 says nothing about quality.

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
  lib/          formatting, labels, data loading hook, demo roles
frontend/public/fonts/  self-hosted Inter Variable and JetBrains Mono (OFL)
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
| Deterministic facts, SLA, safety net, priority with reasons | Model field for bonus abuse, checked by code (keywords are a safety net only) |
| Strict LLM contract, fail-closed evidence check, prompt-injection fencing | Screenshots and demo video |
| One-page brief ([docs/brief.md](docs/brief.md)) | Sign-in and real roles checked in the API |
| Manager mistakes with evidence, specialist lane, demo roles | Reply draft for the manager to review only, never sent automatically |
| Full player card, birthdays, win-back linked to the queue | |
| One source for waiting; mistakes counted by code; head of VIP read-only queue | |
| Analysis cache, work items, status history | |
| Three-pane inbox, evidence pills, player dossier, pulse indicator | |
| Gold set and `eval` command (no LLM calls) | |
| Gemini provider: retries, parallel calls, $1 spending cap with a ledger | |
| Team lead SLA lanes and head-of-VIP view | |
| Task files: `task_v1` adapter, analysed by Gemini | |
| Player signals: account restrictions, payment problems, deposit trends | |
| «Связаться лично» alerts, «Кого вернуть» list | |

## Known limitations

- **Keywords are a safety net, not understanding.** Offers, crediting verbs, responsible-gaming
  and fraud phrases live in `thresholds.yaml`; new wording needs new entries. «не начислю бонус»
  still counts as an offer through the word «бонус» (the offer rules treat «не» before an offer
  word as not a refusal: «не забудьте бонус»).
- **A player's product feedback can be lost in the next step.** When the analysis notes feedback
  (slow app, no search) but the next step is about something else, nothing reminds the manager to
  thank the player and pass the feedback on. Fixing it needs a model field, not a rule.
- **Thresholds are assumptions**: SLA hours, money escalation, deposit drop and spike (ratio and
  a $1 000 minimum rise), win-back days, birthday window.
- **Roles are a demo filter**, not sign-in and permissions.
- **Times without a time zone are taken as UTC**; account status is a snapshot of the export.

## Data and secrets

Only synthetic data is committed (`data/sample/`). Files supplied with the task go to
`data/input/`, which is git-ignored. Secrets live in `backend/.env`, which is also git-ignored.
