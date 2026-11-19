# VIP Pulse AI

AI-assisted triage of VIP manager ↔ player conversations: finds unanswered requests and
service problems, prioritises follow-up and suggests next actions — every conclusion is
linked to the exact source messages.

> Status: **work in progress** — stage 1 (backend foundation). See `docs/` for design notes.

## Quick start (Windows PowerShell)

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item ..\.env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000/health> or the interactive docs at <http://127.0.0.1:8000/docs>.

macOS / Linux: same steps with `python3 -m venv .venv` and `.venv/bin/python`.

## Checks

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

## Data policy

Only synthetic data is committed (`data/sample/`). Files supplied with the task go to
`data/input/`, which is git-ignored. Secrets live in `backend/.env`, which is git-ignored too.
