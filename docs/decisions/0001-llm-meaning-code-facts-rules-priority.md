# Decision record: LLM gives meaning, code gives facts, rules give priority

- Status: accepted
- Date: 2026-11-19
- Scope: analysis and policy (`backend/app/analysis`, `backend/app/policy`)

## Problem

Who decides how urgent a conversation is? The task gives no evaluation rules, and during the
defense we must explain every priority and change a rule live.

## Evidence

- An LLM miscounts time and is not reproducible run to run; wait time and SLA are plain arithmetic.
- The defense includes "make a small change live": a threshold in YAML changes in seconds, a
  prompt change needs re-analysis and is hard to explain.
- `tests/test_policy.py` covers every rule deterministically without any model.

## Decision

- Code computes facts: who wrote last, pending messages, wait time, SLA breach (`facts.py`).
- The LLM returns meaning only: category, sentiment, urgency, summary, next action, safety flag,
  evidence message ids, confidence (`LLMAnalysis`). It has no `priority` field; extra fields are rejected.
- `priority.py` combines both into P0–P3, a route and a list of reasons. Thresholds live in
  `thresholds.yaml` and are marked as illustrative assumptions.

## Consequences

- Benefits: explainable decisions, unit-testable rules, a live threshold change for the defense,
  the provider can be swapped without changing priorities.
- Costs/risks: rules can miss nuance that a model would catch; mitigated by `urgency` and
  `needs_escalation` from the model, which raise priority through explicit rules.
- Revisit when: the gold set shows that rules systematically disagree with human labels.

## Alternatives not chosen

- The LLM outputs priority directly: not explainable, not reproducible, hard to tune live.
- Rules only, no LLM: violates the task ("an LLM works inside") and cannot read meaning.
