# 0015. Demo roles: a view switcher, not authorisation

Date: 2026-11-20. Status: accepted (Denys).

## Context

All three roles saw every page and every player. A manager should open the app and see only
their own players. Real sign-in and permissions are out of the MVP scope.

## Decision

- A switcher in the header: «Все разделы», «Я: <менеджер>» for each manager in `players.csv`
  (`/api/meta.managers`), «Тимлид», «Руководитель», with a visible «демо-режим» label.
- The choice lives in `localStorage` (`vip-pulse-role`, read and written in try/catch); without
  storage it applies until reload. Default: «Все разделы», the earlier behaviour.
- Manager: «Очередь» and «Кого вернуть», both filtered to their players with the existing
  `manager` filter; the filter cannot be removed. Team lead: «Очередь» (everyone) and «Команда».
  Head of VIP: «Обзор» and «Команда». A page outside the role opens the role's first page.

## Consequences

- This is a simulation for the demo. The API still serves every player to anyone who calls it;
  a link to another manager's conversation still opens. Real roles need sign-in and checks in
  the API, which is the next step after the MVP.
