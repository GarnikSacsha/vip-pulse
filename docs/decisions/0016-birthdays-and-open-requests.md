# 0016. Birthdays as a reason to write; win-back defers to an open request

Date: 2026-11-20. Status: accepted (Denys).

## Context

The brief says the manager congratulates players. `players.csv` has birthdays, but nothing used
them. Separately, the win-back list told a player with a stuck payout «другое казино?» while
their withdrawal request waited in the queue.

## Decision

- `/api/birthdays?manager=` and a block «Повод написать: день рождения» on «Кого вернуть».
  The window is ± `winback.birthday_window_days` (7) around the data date shown in the header,
  never the system clock. The nearest occurrence is used, so the window crosses the new year;
  29 February counts as 28 February in a common year. Self-excluded and limited accounts are
  left out. The step is fixed: «Поздравить лично, без бонуса и промо».
- A win-back card checks the queue: if the player has an active conversation that needs the
  manager (P0/P1, or the player waits for an answer that is needed), the card shows «Сначала
  закрой открытый запрос: <тема>, ждёт <время>» with a link, instead of the win-back step.
  The most urgent request is picked: priority first, then the longest wait.
