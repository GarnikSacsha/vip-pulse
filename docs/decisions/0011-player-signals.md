# 0011. Player signals from the profile

Date: 2026-11-19. Status: accepted (Denys asked for it after the first run on the task files).

## Context

`players.csv` in the task files carries the account status and payment metrics. The first run
showed what ignoring them costs: offers to a player with a deposit limit were not flagged, and a
large withdrawal waiting for payout did not change the priority.

## Decision

Signals are computed in code (`app/policy/player.py`) from the player's attributes, with
thresholds in `thresholds.yaml` under `player:`. The LLM never sees or decides them.

| Signal | Effect |
|---|---|
| `account_status = self_excluded` | RG specialist, P0, no offers, human review |
| `account_status = limit_set` | no offers, human review |
| manager offer to a restricted player | quality flag `offer_to_restricted_player`, at least P1 |
| `failed_deposits_7d >= 3`, `pending_withdrawal_usd >= 1000` | reason; P1 if the player waits, else P2 |
| deposits < 0.5 × previous 30 days | churn reason, P2 |
| deposits >= 1.7 × previous 30 days | harm-risk reason, P2, human review |

Offer detection is keyword-based with refinements found on the task files and in review:

- A refusal right before the offer word («без», «никаких», "no", "without") or a retold request
  («ты просил …», "you asked for …") is not an offer. Other negations («не пропустите бонус»)
  are, and one real offer in a message is enough. A careful manager is not flagged.
- "Reload" and suggestions to raise a limit count as offers.

An offer after a responsible-gaming signal that only the analysis found (no keyword hit) is now
flagged too: offers after the player messages the analysis cites; offers before them are not.
That reason carries the analysis source label (AI or demo heuristic).

Known limits (accepted for the MVP):

- The account status is a snapshot at export time and applies to the whole conversation: an offer
  sent before the limit was set is flagged too. The files have no date of the status change.
- `self_excluded` replaces a security route: responsible gaming outranks fraud, as in the keyword
  net. Money signals reach P1 only when the player waits for an answer that is needed.

## Consequences

- On the task files, with Gemini: 3 manager mistakes flagged (two offers after a player said
  they lost too much or asked to be blocked, one reload offer to a player with a limit), the
  careful manager is not. 6 conversations go to the RG specialist.
- Keyword lists stay a safety net, not understanding: new wording needs new entries. The model
  covers meaning; the code covers the rules that must hold even when the model is wrong.
- Attribute names are those of the task format; another format maps its columns in its adapter.
