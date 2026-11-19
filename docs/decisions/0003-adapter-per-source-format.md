# Decision record: one ingestion adapter per source format

- Status: accepted
- Date: 2026-11-19
- Scope: ingestion (`backend/app/ingestion`)

## Problem

The real `dialogs.json` and `players.csv` had not been received when work started, but the
rest of the system needs data to be built and tested.

## Evidence

- The task describes the files only in words; field names, ids, timestamp format and sender
  labels are unknown.
- Building against a guessed format risks rewriting everything later.

## Decision

- The internal domain model (`app/schemas/domain.py`) is ours and does not follow any file.
- Each source format gets an adapter in `app/ingestion/adapters/` that parses into that model
  and reports bad records instead of raising.
- Generic checks (duplicates, unknown players, message id clashes) live in `pipeline.py` and
  apply to every adapter.
- A synthetic `sample_v1` format in `data/sample/` covers known edge cases until real data arrives.

## Consequences

- Benefits: the real data needs one new adapter plus a data contract document; policy, analysis
  and tests stay unchanged.
- Costs/risks: `sample_v1` may differ from reality, so some edge cases may be missing; the
  data contract step in stage 2 must check the real files explicitly.
- Revisit when: the real files arrive (stage 2, first task).

## Alternatives not chosen

- Waiting for the data before writing code: wastes most of the 5-day window.
- Guessing the real format and parsing it directly everywhere: expensive to change.
