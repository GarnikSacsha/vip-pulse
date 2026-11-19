# Decision record: SQLite for local persistence

- Status: accepted
- Date: 2026-11-19
- Scope: storage (`backend/app/db.py`, `backend/app/models.py`)

## Problem

Imported data, and later analyses and tasks, must survive restarts and support re-import
without duplicates. The budget is about 10 hours and the reviewer must run the project from a clone.

## Evidence

- The dataset is 150–250 players with their conversations: a few MB at most.
- One user at a time in the demo; no concurrent writers.
- The Linear brief allows SQLite for the demo and PostgreSQL only as an option for deployment.

## Decision

SQLite file via SQLAlchemy 2 (`DATABASE_URL`). Timestamps are stored as naive UTC through a
`UTCDateTime` type and restored as tz-aware. Re-import upserts by source id.

## Consequences

- Benefits: zero setup for the reviewer, one file, SQLAlchemy keeps PostgreSQL possible.
- Costs/risks: no concurrent writers; no migrations tool yet (tables are created on start).
- Revisit when: deployment needs a managed database, or the schema starts changing after real data.

## Alternatives not chosen

- PostgreSQL in Docker: extra setup for the reviewer, no benefit at this size.
- JSON files: no queries for the views, no safe upsert.
