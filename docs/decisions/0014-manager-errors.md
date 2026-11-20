# 0014. Manager mistakes: closed taxonomy from the analysis, rules stay in code

Date: 2026-11-20. Status: accepted (Denys).

## Context

The brief asks what counts as a good contact and what counts as a mistake. «Ошибки менеджеров»
showed only one rule (a bonus offered to a vulnerable or restricted player). The model already
described other mistakes in free text (brush-off replies, a wrong name, an incomplete answer), but
nothing could count or link them.

## Decision

- `LLMAnalysis.manager_errors`: a list of `{code, evidence_message_ids}` with a closed list of
  codes: `canned_reply`, `rude_tone`, `wrong_info`, `incomplete_answer`, `wrong_name`,
  `broken_promise`, `retention_pressure`. Extra fields are rejected.
- Fail closed: each mistake must cite at least one message of this conversation and at least one
  of them must be the manager's. Otherwise the whole analysis is rejected, as with other evidence.
- Mistakes a rule can count stay in code and are not asked from the model: a bonus to a
  vulnerable or restricted player (`quality_flags`), a reply later than the SLA (SLA lanes).
- Prompt version `v4`. The cache key contains the prompt version and the schema, so every stored
  analysis is redone on the next run with a model; older stored analyses read as "no mistakes".
- The offline heuristic returns two of the codes (a broken promise, a question about "when" left
  without a date) and stays labelled `fake`.
- Team lead page: mistakes grouped by manager, with the type and a link that opens the
  conversation with the message highlighted (`?msg=`). All statuses count: a mistake in a closed
  conversation is still a mistake. The workload table has an «Ошибки» column.
- Gold set: `manager_errors` labels for the 9 synthetic conversations; `eval` scores them as sets.

## Consequences

- On the synthetic sample (2026-11-20): Gemini 8/9 on `manager_errors` (missed the incomplete
  answer in d-005), the offline heuristic 9/9; its rules were written for these examples, so that
  number says nothing about quality.
- The task database still holds analyses from prompt v3 until it is re-analysed with Gemini
  (about $0.05 for 40 conversations).
