# 0019. Manager mistakes counted by code from message times

Date: 2026-11-20. Status: accepted (Denys).

## Context

Timing mistakes do not need a model: message times are exact. Before this, the team lead saw
only the bonus rule and, after a paid re-run, what the analysis found.

## Decision

- `app.policy.facts.late_replies`: every manager answer given later than the channel's SLA
  (`sla.response_hours`, `sla.channel_response_hours` in `thresholds.yaml`), in any conversation,
  closed ones included. The evidence is the first player message the manager was late on, then
  the late answer.
- «Игрок ждёт дольше SLA»: the conversation is in «Горит» now (decision 0017); the evidence is the
  first unanswered player message.
- The API returns them per item as `rule_errors` with the hours; «Ошибки менеджеров» lists them
  per manager labelled «посчитано кодом», and they count in «Ошибки» and in the KPI.

## Consequences

- A conversation in «Горит» is also a mistake of its manager. This is deliberate: the lead sees
  who is late, not only what is late.
