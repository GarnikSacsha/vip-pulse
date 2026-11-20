# 0020. Compare managers by conversations with mistakes

Date: 2026-11-20. Status: accepted (Denys).

## Context

Two numbers had one name «Ошибки менеджеров»: the tile counted conversations with a mistake
(17 on the task files), the block counted mistakes (35). One conversation can hold three or four
mistakes, so comparing managers by the sum of mistakes was skewed.

## Decision

- The tile is «Диалоги с ошибками», «из N диалогов, включая закрытые». The block is «Ошибки
  менеджеров · M в K диалогах», grouped by manager, then by conversation («… · 4 ошибки: …»);
  each mistake still links to its message.
- «Нагрузка по менеджерам» compares by «Диалоги с ошибками» (`error_conversations`), with the
  number of mistakes next to it.
- Invariant (tested): tile = conversations in the block = sum of «Диалоги с ошибками» per manager.
- «Ответ позже SLA» and «Игрок ждёт дольше SLA» in one conversation stay two mistakes. They can
  never cite the same player message: a late reply is about a message the manager did answer;
  a current wait is about messages after the last manager reply. Two episodes, two mistakes.
