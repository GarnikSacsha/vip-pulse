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
  Frontend: React 19 + TypeScript (strict) + Vite + Tailwind v4, Node 24.
- Persistence: SQLite file (`DATABASE_URL`), local only.
- External providers: Gemini (REST, stdlib HTTP) behind `app/analysis/llm`; `fake` provider offline.
- Approved dependencies: fastapi, uvicorn, pydantic, pydantic-settings, sqlalchemy, pyyaml;
  dev: pytest, httpx2, ruff.
  Frontend (approved 2026-11-19): react, react-dom, react-router; dev: vite,
  @vitejs/plugin-react, typescript, @types/react(-dom), tailwindcss, @tailwindcss/vite, vitest,
  jsdom, @testing-library/{react,user-event,jest-dom}, eslint, @eslint/js, typescript-eslint,
  eslint-plugin-react-hooks, globals. Exact versions, each published at least 14 days before
  install. Anything else needs approval.
- Supported local environment: Windows + PowerShell. CI: Ubuntu, Python 3.12 and 3.14.

## Repository map

- Entry points: `backend/app/main.py` (API factory), `backend/app/cli.py` (`import`, `triage`),
  `frontend/src/main.tsx` (UI)
- Domain contracts: `backend/app/schemas/`
- Ingestion: `backend/app/ingestion/` (one adapter per source format in `adapters/`)
- Policy (facts, safety, priority, `thresholds.yaml`): `backend/app/policy/`
- LLM analysis (prompt, providers, validation): `backend/app/analysis/`
- HTTP API (FastAPI routers and response models): `backend/app/api/`
- Work items, triage runs, audit: `backend/app/tasks/`
- UI (React): `frontend/src/` (`api/` typed client mirroring `backend/app/api/schemas.py`)
- Tests: `backend/tests/` (pytest), `frontend/src/**/*.test.ts(x)` (vitest)
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
Build/package:       not applicable for the backend
```

Frontend, from `frontend/` (the API must run on :8000; Vite proxies `/api`):

```text
Install:             npm ci
Develop:             npm run dev        (http://localhost:5173)
Lint:                npm run lint
Typecheck:           npm run typecheck
Tests:               npm test
Build:               npm run build
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

- Stage 1 (backend foundation): PR #1, merged. Built before the harness was read: tests were
  written after the code, no RED evidence. Corrective commits in the same PR.
- Stage 2a (browser slice): PR #2, merged. Persisted analyses, tasks + audit, REST API, React UI.
- Stage 2b: Gemini provider, spending cap, bounded concurrency: PR #3, merged.
- Stage 2c (team lead and head-of-VIP views): PR #4, merged.
- Stage 3 (UI design from `design/README.md`): PR #5, merged. Fonts are self-hosted assets in
  `frontend/public/fonts/` (approved by Denys, 2026-11-19), not npm packages.
- Gold set and `eval` command: PR #6, merged. Task-file adapter `task_v1`: PR #7, merged.
- Player signals (decision 0011): PR #8, merged. Alerts, «Кого вернуть», brief: PR #9, merged.
- Manager audit fixes (decisions 0013–0021): PR #10, merged. Task files re-analysed with prompt v4
  on 2026-11-20 ($0.062, approved by Denys).
- Screenshots (synthetic sample only, public repo): PR #11. The demo video script is kept
  locally, outside Git (Denys, 2026-11-20); the video is recorded by Denys.
- Deadline: task received 2026-11-18, submission 2026-11-20.
- Strict TDD with RED/GREEN evidence recorded in every PR.
- Commit map: written before each stage; one atomic GREEN commit per coherent outcome.
- Local-commit authorization: granted for agreed stages.
- Push authorization: granted after each step (Denys, 2026-11-19).
- Pull requests: Draft PRs into `main` only. **Merge requires Denys's explicit approval.**
- Never commit directly to `main`.

## Safety and permissions

- Excluded from Git: `.env`, `data/input/*`, `*.db`, `*.sqlite*`, caches, `node_modules/`.
  CI job "No secrets or real data" enforces the first two.
- Data class: task files are fictional but belong to the employer → treat as internal; do not
  publish them; describe results only in aggregate (the repository is public). Sending them to
  Gemini: approved by Denys 2026-11-19 on a billed key (decision 0008). The task database runs with
  `LLM_BUDGET_USD=0.96` so the total across databases stays under $1.
- Paid LLM calls: total cap $1 (`LLM_BUDGET_USD`, Denys, 2026-11-19), enforced in code by the
  spending meter and the `llm_calls` ledger. Raising it needs Denys's approval.
- Production credentials: none. Network: GitHub, Linear, npm registry (installs)
  and (stage 2, approved) Gemini API only.
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
