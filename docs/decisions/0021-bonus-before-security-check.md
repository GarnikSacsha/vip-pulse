# 0021. A bonus before the security check is a manager mistake

Date: 2026-11-20. Status: accepted (Denys).

## Context

On the task files the most dangerous mistake was not counted: in a conversation that went to
security (a bonus requested for another account paid with the same card), the manager had
already credited the bonus. The analysis listed no manager mistake there.

## Decision

- `app.policy.safety.credit_before_security_check`, code only, no model: for a conversation
  routed to security, every manager message after the first player message with a fraud or
  shared-account signal that offers or credits a bonus. When only the analysis saw the risk,
  the anchor is the first player message.
- Offer words and refusals are the same as for «Бонус уязвимому игроку» (`offers`,
  `mentions_offer`). Crediting verbs («начислю», «начислим», …) are new, in
  `safety.credit_words` in `thresholds.yaml`, and count unless denied right before («не начислю»).
- The API returns it in `rule_errors` as `offer_before_security_check` with the manager message;
  the team lead sees «Бонус до проверки безопасности (код)» linked to it.

## Known limits

- «не начислю бонус» still counts as an offer through the word «бонус»: the offer rules
  deliberately treat «не» before an offer word as not a refusal («не забудьте бонус»).
- New wording needs new words in the list.
