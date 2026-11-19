# UI direction

Status: agreed direction (Denys, 2026-11-19). Not implemented yet. References: [references.md](references.md).

## Starting point

The current UI is a light, calm palette where colour carries meaning only (priority, warnings,
evidence), with a queue list page and a separate conversation page. The base is sound, but it reads
as a generic admin panel. Two changes: the layout, and one recognisable signature detail.

## Chosen combination

| Role | View | Direction |
| --- | --- | --- |
| VIP manager | Main working screen | **A. Three-pane inbox** + **D. Pulse indicator** + evidence pills |
| Team lead | Oversight | **B. SLA lanes** |
| Head of VIP | Player context | **C. Player dossier**, as the right panel inside A, not a separate page |

No new dependencies: everything builds on the existing components and `@theme` tokens in
`frontend/src/index.css`.

## A. Three-pane inbox (Front, Superhuman, Linear Inbox)

```text
┌ Очередь ──────┬ Переписка ─────────────┬ Разбор ─────────┐
│▌P0 Иван К. 4ч │ 10:02 игрок: где вывод │ Категория: вывод│
│▌P1 Анна  1ч   │ 10:40 игрок: ау?  [2]◄─┼─ ждёт ответа [2]│
│ P2 ...        │                        │ Шаг: ...        │
└───────────────┴────────────────────────┴─────────────────┘
```

- The manager never leaves the page: the queue on the left, the timeline in the centre, the analysis
  card on the right.
- Keyboard: `j`/`k` or arrows to move between conversations.
- On narrow screens the panes collapse to the current list → detail navigation.

## Evidence pills (two-way highlight)

- Every conclusion in the analysis card carries numbered pills `[1] [2]` that point to message ids.
- Hovering or focusing a pill highlights the message in the timeline and scrolls to it. Hovering a
  cited message highlights the pills that cite it.
- Pills must work from the keyboard (focus = hover) and have an accessible label.

## B. SLA lanes (team lead)

- Columns: «Горит» / «Скоро нарушится» / «Ждёт» / «Всё ок».
- Each card shows a bar for the time left before the SLA is breached, plus the assigned manager.
- Lane membership is computed by `app/policy/` thresholds, never by the LLM.

## C. Player dossier

- Player value, a sentiment-trend sparkline, all conversations as a timeline with analysis markers.
- Lives as the right panel of A (tab or expandable section), not as a separate route.

## D. Pulse indicator (signature detail)

- Wait time is shown as a ring or bar that fills as the wait approaches the SLA.
- Near the limit it pulses subtly; after a breach it is solid red, no animation.
- Only genuinely urgent conversations animate. Respect `prefers-reduced-motion`.
- This makes the product name visible in the interface itself, not only in the logo.

## Typography

Finding: `--font-sans` names `"Inter"`, but no font file is loaded (`index.html` has no font link,
`public/` is empty). On a machine without Inter installed the UI falls back to Segoe UI or Roboto.

Hard constraint: full **Cyrillic** support, since the product language is Russian.

| Option | Character | Cyrillic | Licence |
| --- | --- | --- | --- |
| **Inter Variable + Inter Display** (chosen default) | Linear's choice; neutral, very readable in dense UI | Excellent | OFL, free |
| Geist + Geist Mono | Vercel; more technical, "engineering" feel | Yes (redesigned Cyrillic) | OFL, free |
| Onest / Golos Text | Designed with Cyrillic first | Native | OFL, free |
| SF Pro (Apple) | Not usable: Apple licenses it for Apple platforms, not for the web | — | — |
| Söhne, Suisse Int'l, Aeonik | "Expensive site" look (Stripe, OpenAI) | Partly | Paid, needs budget approval |

Rules:

- Body text: Inter Variable at 13–14 px, emphasis at weight 500–550 rather than bold.
- Headings: Inter Display (optical size for large text), slightly negative tracking.
- Numbers (wait times, counters): `tabular-nums`, already in use.
- Mono (message ids, evidence references): JetBrains Mono or Geist Mono, both with Cyrillic.
- Self-host the `woff2` files from the official releases in `frontend/public/fonts/` with
  `font-display: swap`. No Google Fonts request at runtime and no new npm package. Adding the font
  files still needs Denys's approval as a new asset.

## Simulated output

Cards produced by the `fake` provider get a diagonal hatch background and a «демо» label, so they can
never be mistaken for real model output, even without the top banner. Consistent with
`docs/decisions/0005-safety-net-and-simulated-output.md`.

## Not doing

- "Casino VIP" aesthetic (dark background, gold, luxury). It is a tool used all day: worse
  readability, and it pulls attention away from the content.
- Animation on anything that is not urgent.
