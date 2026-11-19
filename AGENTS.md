# Project operating instructions — VIP Pulse AI

Global contract: Denys's agent harness, <https://github.com/GarnikSacsha/denys-agent-harness>
(`AGENTS.md` + `.harness/START-HERE.md`). Read it before substantive work. This file adds the
project-specific rules and overrides it only where it says so explicitly.

## Project outcome

A VIP manager opens a prioritised queue of their player conversations and sees what needs an
answer, why, and the safe next step, with every conclusion linked to the source messages.
Team lead and head of VIP get thin oversight views over the same data.

## Current stage and scope

- Stage: take-home MVP (~10 h budget, 5 calendar days). Source brief: Linear project `P-CRA-14`.
- In scope: import of the supplied synthetic `players.csv` / `dialogs.json`, LLM analysis per
  conversation, deterministic priority policy, work queue, player timeline with evidence, three
  role views, README, a one-page brief, demo.
- Out of scope: real messenger integrations, auth/RBAC, sending messages to players, schedulers,
  RAG, a Telegram bot (stretch only).

## Stack and runtime

- Language/framework: Python 3.11+ (local: 3.14 via `py`), FastAPI, Pydantic v2, SQLAlchemy 2.
  Frontend (stage 3): React + TypeScript + Vite + Tailwind.
- Persistence: SQLite file (`DATABASE_URL`), local only.
- External providers: Gemini (stage 2) behind `app/analysis/llm`; `fake` provider offline.
- Approved dependencies: fastapi, uvicorn, pydantic, pydantic-settings, sqlalchemy, pyyaml;
  dev: pytest, httpx2, ruff. Anything else needs approval.
- Supported local environment: Windows + PowerShell. CI: Ubuntu, Python 3.12 and 3.14.

## Repository map

- Entry points: `backend/app/main.py` (API), `backend/app/cli.py` (`import`, `triage`)
- Domain contracts: `backend/app/schemas/`
- Ingestion: `backend/app/ingestion/` (one adapter per source format in `adapters/`)
- Policy (facts, safety, priority, `thresholds.yaml`): `backend/app/policy/`
- LLM analysis (prompt, providers, validation): `backend/app/analysis/`
- Tests: `backend/tests/`
- Configuration: `.env.example` → `backend/.env` (git-ignored)
- Data: `data/sample/` synthetic (committed), `data/input/` task files (git-ignored)
- Documentation: `README.md`, `docs/architecture.md`, `docs/decisions/`

## Real commands

Run from `backend/` in PowerShell (macOS/Linux: `.venv/bin/python`).

```text
Install:             py -m venv .venv; .\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Develop (API):       .\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --reload
Import sample:       .\.venv\Scripts\python.exe -m app.cli import --players ..\data\sample\players.csv --dialogs ..\data\sample\dialogs.json
Work queue:          .\.venv\Scripts\python.exe -m app.cli triage
Format/check format: .\.venv\Scripts\python.exe -m ruff format --check .
Lint:                .\.venv\Scripts\python.exe -m ruff check .
Typecheck:           not configured (no type checker approved yet)
Targeted test:       .\.venv\Scripts\python.exe -m pytest tests/test_policy.py -k <name>
Full tests:          .\.venv\Scripts\python.exe -m pytest
Build/package:       not applicable yet
```

`pytest` writes temp files to `backend/.pytest-tmp` (configured in `pyproject.toml`) because the
system temp directory on the dev machine cannot be cleaned by pytest.

## Architecture and conventions

- Identifiers, code comments and docstrings: **English** (approved override of the harness default).
- Product language (reasons, next actions, UI, LLM summaries): **Russian**.
- Formatter and linter: Ruff (`pyproject.toml`); tests: pytest.
- Facts (who wrote last, wait time, SLA) are computed in code. The LLM returns meaning only
  (category, sentiment, next action, evidence ids). Priority, routing and offer suppression are
  decided by `app/policy/priority.py`. The LLM never sets priority.
- LLM output is validated against `LLMAnalysis` (extra fields rejected); evidence must cite real
  message ids of the same conversation, otherwise the analysis fails closed.
- Output of the `fake` provider is labelled as such everywhere and never described as AI analysis.
- Thresholds are illustrative assumptions and live in `backend/app/policy/thresholds.yaml`.
- A new source format = a new adapter; the domain model does not change for it.
- Requirements source of truth: Linear `P-CRA-14` brief; decisions: `docs/decisions/`.

## Delivery stages

- Stage 1 (backend foundation): PR #1, Draft. Built before the harness was read: tests were
  written after the code, no RED evidence. Corrective commits in the same PR.
- Stage 2 (next): real-data adapter and data contract, Gemini provider, batch runner, persisted
  analyses, tasks + audit, REST API. Strict TDD with RED/GREEN evidence recorded in the PR.
- Commit map: written before each stage; one atomic GREEN commit per coherent outcome.
- Local-commit authorization: granted for agreed stages.
- Push authorization: granted after each step (Denys, 2026-11-19).
- Pull requests: Draft PRs into `main` only. **Merge requires Denys's explicit approval.**
- Never commit directly to `main`.

## Safety and permissions

- Excluded from Git: `.env`, `data/input/*`, `*.db`, `*.sqlite*`, caches, `node_modules/`.
  CI job "No secrets or real data" enforces the first two.
- Data class: task files are fictional but belong to the employer → treat as internal; do not
  publish them. Sending them to Gemini requires a recorded provider decision first.
- Paid LLM calls: none without an explicit budget (attempts and spending cap) from Denys.
- Production credentials: none. Network: GitHub, Linear and (stage 2, approved) Gemini API only.
- Linear: no new issues (workspace limit). Progress is tracked as ☐/☑ in the project description.

## Review gates

- Self-review after every stage: yes.
- Fresh independent review pass for: large diffs, LLM/provider integration, data handling.
- Blocking severities: critical, high. Medium requires a recorded decision.
- Required automated checks: `ruff check`, `ruff format --check`, `pytest`, CI hygiene job.
- Merge approval owner: Denys.

## Definition of done

- The requested behaviour works through the real path (CLI/API/UI as applicable).
- Relevant checks pass, or failures are reported exactly.
- User usefulness is evaluated separately from technical completion.
- No unrelated files, secrets or task data in the diff.
- README, `docs/` and this file match the verified state.
- Handoff in four parts: what works, what changed, which checks ran, what is open.
