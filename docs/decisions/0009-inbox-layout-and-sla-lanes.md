# 0009. Inbox layout, evidence pills and SLA lanes

Date: 2026-11-19. Status: accepted (Denys approved the direction in `design/README.md`).

## Context

The browser slice had a queue page and a separate conversation page. A manager clearing a queue
lost the list on every click, the link between a conclusion and its messages was a colour only,
and the team lead saw overdue work as one flat list.

## Decision

- **Three-pane inbox** at `/queue/:id`: queue, conversation, analysis. On narrow screens the panes
  take turns. `j` / `k` move through the queue, except inside text fields. `/conversations/:id`
  redirects, so older links keep working.
- **Evidence pills.** Messages cited by the analysis or still waiting for a reply are numbered in
  timeline order. The summary carries pills for cited messages, the wait fact carries pills for
  pending ones. Hover or focus on a pill highlights and scrolls to the message; hover on a cited
  message lights its pills. The model gives one evidence list per analysis, so the pills sit on
  the summary rather than on each sentence.
- **SLA lane per work item**, computed in `app/policy/sla.py`: `breached` exactly when the item is
  overdue (the triage's SLA reasons, so it agrees with the priority), `at_risk` past
  `sla.at_risk_share` of the channel SLA (0.75, in `thresholds.yaml`), `waiting`, `ok`. The model
  never decides a lane.
- **Pulse indicator**: the ring fills with the share of the SLA waited; only `at_risk` pulses,
  under `prefers-reduced-motion` nothing moves; a breach is solid red.
- **Player dossier** as a tab of the right pane, from `/api/queue?player=`: profile, tone across
  conversations (shown from two analysed conversations), every conversation.
- **Stand-in output** of the `fake` provider is hatched and labelled «демо» in the analysis card.
- **Fonts**: Inter Variable (with the optical-size axis, so headings get the Display cut) and
  JetBrains Mono, self-hosted under OFL. No request leaves the app.

## Consequences

- `list_queue` now needs the policy explicitly; the API, the overview and the CLI pass it.
- The lane uses today's thresholds for `at_risk` but the triage's decision for `breached`. After a
  threshold change, an item can show `at_risk` with a wait above the new SLA until triage re-runs.
- The dossier relies on optional `country` / `registered_at` profile columns; a real-data adapter
  maps its columns to these names or leaves them empty.

## Independent review (2026-11-19)

No critical or high findings. Fixed with tests:

- Medium: between lg and xl the conversation pane scrolled the whole inbox; the right side now
  scrolls on its own, each pane from xl.
- Medium: the dossier showed stand-in tone without a label; rows carry «демо», the trend is hatched
  and says it comes from the demo heuristic.
- Low: counters and list refresh after a status change; `j`/`k` continue from the old position when
  the selection leaves the list; dossier links keep the filters and the open tab; lane hint no
  longer hard-codes 75 %; tab panels wired with arrow keys; a focused pill keeps its highlight.

Accepted for the MVP (low): the queue's view tabs are filters styled as tabs; on a phone with a
conversation open the page has no h1; a cited message lights its pills on hover only (keyboard
users reach the same link from the pills).
