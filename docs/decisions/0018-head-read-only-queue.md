# 0018. The head of VIP gets a read-only queue

Date: 2026-11-20. Status: accepted (Denys).

## Context

On «Обзор» the button «Открыть критичные» led to `/queue?priority=P0`, but the head-of-VIP role
had no queue, so the page bounced back to the overview.

## Options

- (a) A read-only queue for the head of VIP: the same inbox, no status actions.
- (b) Send the button to «Команда».

## Decision

(a). The head of VIP needs to drill down from a number to the conversation and its evidence;
«Команда» has no list of critical items. The role sees «Обзор», «Команда», «Очередь». In the
conversation, «Следующий шаг» shows «Режим просмотра: статус меняет менеджер или тимлид» instead
of the note and the action buttons. The start page `/` opens the role's first section.

A test renders every page of every role and checks that each internal link opens a section the
role can see. This is still a demo filter, not authorisation (decision 0015).
