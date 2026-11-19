# Decision record: "now" is the latest message in the dataset

- Status: accepted
- Date: 2026-11-19
- Scope: facts and SLA (`backend/app/policy/facts.py`)

## Problem

Wait time and SLA need a current time. The supplied conversations are historical demo data.

## Evidence

Using the wall clock would make every conversation weeks overdue, so every waiting player would
become P0/P1 and the queue would stop meaning anything.

## Decision

`dataset_as_of()` returns the latest message timestamp across the imported conversations and
is used as "now". `triage()` accepts an explicit `as_of` to override it. The CLI prints the
reference time in its header.

## Consequences

- Benefits: priorities on demo data look like a real working day.
- Costs/risks: a conversation that ends long before the others still looks long-waiting, which
  is correct relative to the dataset. With live data `as_of` must become the wall clock.
- Revisit when: data starts arriving continuously (live integrations).

## Alternatives not chosen

- Wall clock: makes the demo meaningless.
- A fixed date in config: easy to forget and wrong for a new dataset.
