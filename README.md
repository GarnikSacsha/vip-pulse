# VIP Pulse AI

[![CI](https://github.com/GarnikSacsha/vip-pulse/actions/workflows/ci.yml/badge.svg)](https://github.com/GarnikSacsha/vip-pulse/actions/workflows/ci.yml)

AI-assisted triage of VIP manager ↔ player conversations. It finds unanswered requests and
service problems, prioritises follow-up and suggests the next step. Every conclusion links to the
exact source messages, and responsible-gaming cases are routed to a human specialist.

> **Status: stage 1 of 4.** The backend foundation works end to end from the command line on
> synthetic data with an offline stand-in for the LLM. The Gemini provider, API and UI come next.
> See [docs/architecture.md](docs/architecture.md).

## How it decides

- **Facts in code:** who wrote last, how long the player is waiting, SLA breach.
- **Meaning from the LLM:** category, sentiment, next action, evidence message ids. The output is
  strictly validated, and an answer citing a message that does not exist is rejected.
- **Priority by explicit rules:** P0–P3 with a list of reasons, tunable in
  [`thresholds.yaml`](backend/app/policy/thresholds.yaml).
- **Safety first:** responsible-gaming and fraud signals are caught even without the LLM. Bonuses
  are never suggested to a vulnerable player, and a manager who offered one is flagged.

## Quick start (Windows PowerShell)

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item ..\.env.example .env

# import the synthetic sample (prints a validation report)
.\.venv\Scripts\python.exe -m app.cli import --players ..\data\sample\players.csv --dialogs ..\data\sample\dialogs.json

# prioritised work queue
.\.venv\Scripts\python.exe -m app.cli triage

# API: http://127.0.0.1:8000/docs (queue, conversation detail, meta)
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --reload
```

macOS / Linux: the same steps with `python3 -m venv .venv` and `.venv/bin/python`.

If the console shows broken Cyrillic, run `$env:PYTHONIOENCODING = "utf-8"` first.

Example output (offline `fake` provider):

```
P0  d-001  p-001   telegram  withdrawal             27h  manager         Проверить статус вывода у платёжной команды…
    why: Финансовый запрос без ответа 27 ч (порог 24 ч); Рекомендована эскалация (эвристика fake, без модели)
P0  d-004  p-004   telegram  responsible_gaming       -  rg_specialist   Передать специалисту по ответственной игре… [review] [offer_to_vulnerable_player]
    why: Сигнал ответственной игры у игрока; Менеджер предложил бонус игроку с сигналом ответственной игры; …
P3  d-002  p-002   whatsapp  deposit                22h  manager         -
    why: Игрок написал последним, но ответа не требуется (эвристика fake, без модели)
```

## Checks

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

CI runs the same checks on Python 3.12 and 3.14 and blocks commits that contain `.env` or task data.

## Project layout

```
backend/
  app/
    schemas/      Pydantic contracts: domain, taxonomy, strict LLM output
    ingestion/    format adapters, normalization, dedupe, import report, store
    policy/       facts, safety net, priority rules, thresholds.yaml
    analysis/     prompt, LLM providers, validation service
    triage.py     facts → analysis → policy → sorted queue
    cli.py        import / triage commands
  tests/
data/
  sample/         synthetic fixture, one edge case per dialog (committed)
  input/          real task files (git-ignored)
docs/
  architecture.md
```

## Data and secrets

Only synthetic data is committed (`data/sample/`). Files supplied with the task go to
`data/input/`, which is git-ignored. Secrets live in `backend/.env`, which is also git-ignored.
