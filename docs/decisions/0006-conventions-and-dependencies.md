# Decision record: languages, provider and dependencies

- Status: accepted (Denys, 2026-11-19)
- Date: 2026-11-19
- Scope: whole repository

## Problem

The harness defaults to Ukrainian code comments and requires approval for dependencies. The
repository is public and will be read by the employer.

## Decision

- Identifiers, code comments and docstrings: English (override of the harness default).
- Product language (reasons, next actions, LLM summaries, UI): Russian.
- LLM provider: Gemini behind `app/analysis/llm`, swappable; `fake` provider for offline use.
- Harness connection: project `AGENTS.md` + `CLAUDE.md` with a link to the global harness;
  the harness itself and the personal profile are not copied into this public repository.
- Dependencies approved: fastapi, uvicorn, pydantic, pydantic-settings, sqlalchemy, pyyaml;
  dev: pytest, httpx2 (required by the current Starlette TestClient), ruff.

## Consequences

- Benefits: a reviewer reads code and docs in one language; the product speaks the language of
  the task.
- Costs/risks: Russian product strings live in code (`priority.py`, prompts); acceptable for one
  language, would need i18n for more.
- Revisit when: a second product language is needed, or a new dependency is proposed.

## Alternatives not chosen

- Ukrainian comments: harness default, rejected for an employer-facing repository.
- Copying the full harness into the repository: would publish the personal profile.
