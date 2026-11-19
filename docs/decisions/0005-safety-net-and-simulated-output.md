# Decision record: safety net in code, honest labelling of simulated analysis

- Status: accepted
- Date: 2026-11-19
- Scope: `backend/app/policy/safety.py`, `backend/app/policy/priority.py`, `backend/app/analysis`

## Problem

1. Responsible-gaming and fraud signals must not be lost when the LLM is down or misses them,
   and the tool must never push offers to a vulnerable player.
2. Until Gemini is connected, analysis comes from an offline heuristic. Its output must not look
   like AI analysis (harness rule: mocks are clearly labelled).

## Evidence

- Sample dialog d-004: the player asks to be blocked and the manager offers free spins.
- Before the fix, reasons from the fake provider said "AI рекомендует эскалацию"
  (fixed in `fix(policy): label analysis source in decision reasons`).

## Decision

- A keyword net (`thresholds.yaml` → `safety`) runs on player messages independently of the LLM.
  Either source raising a flag makes the case P0 and routes it to an RG specialist or security.
- For RG cases, advice mentioning offers is replaced with a safe template, and a manager offer
  after an RG signal is flagged as `offer_to_vulnerable_player`.
- Providers declare `simulated`. Every reason derived from the analysis carries its source:
  `(AI)` or `(эвристика fake, без модели)`. Keyword findings are code facts and are not labelled.

## Consequences

- Benefits: safety does not depend on the model; the demo is honest about what is real.
- Costs/risks: keywords produce false positives and miss paraphrases; they are a net, not a
  classifier. Keyword lists need review on real data.
- Revisit when: the gold set measures misses and false alarms on real conversations.

## Alternatives not chosen

- Trust the LLM alone for safety: a single point of failure on the most sensitive cases.
- Hide the fake provider behind the same "AI" wording: misleading, against the harness.
