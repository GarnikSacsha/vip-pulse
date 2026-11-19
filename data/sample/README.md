# Synthetic sample data

Invented players and conversations, used for tests and offline demos. No real people.

The format (`sample_v1`) is our own until the real `players.csv` / `dialogs.json` arrive.
Then a new adapter in `backend/app/ingestion/adapters/` maps the real format into the same
domain model, and nothing else changes.

Each dialog covers one case on purpose:

| Dialog | Case |
|---|---|
| d-001 | Withdrawal: manager promised to come back, player still waiting a day later |
| d-002 | Deposit problem resolved, player confirmed (`wa`, `client` aliases) |
| d-003 | Birthday greeting, nothing pending |
| d-004 | Responsible-gaming request answered with a bonus offer (manager error) |
| d-005 | Verification: player follows up, waiting for an answer |
| d-006 | Duplicate message id and duplicate content (`e-mail`, `agent` aliases) |
| d-007 | Missing context: a single "?" |
| d-008 | Dialog for a player who is not in `players.csv` (rejected) |
| d-009 | Account security alert plus a bad timestamp and an unknown sender |
| d-010 | Win-back message with no reply |
| d-001 again | Duplicate `dialog_id` (rejected) |

`players.csv` also has a duplicate `player_id` and a row without an id.
