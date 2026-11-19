"""Adapter for the format of the task files (data/input/, git-ignored).

players.csv: player_id, brand, geo, language, status, manager, vip_since, account_status,
             deposits / withdrawals / bonuses metrics, last_login_at, birthday, favorite_game
dialogs.json: {"as_of": date, "dialogs": [{dialog_id, player_id, manager, channel,
                                           messages: [{from, sent_at, text}]}]}

Differences from sample_v1, handled here so the domain model stays the same:
- messages have no ids: they get "<dialog_id>-<n>", 1-based in file order, stable on re-import;
- timestamps have no timezone: UTC is assumed and reported once per file;
- the manager is a name, used as manager_id; `status` (VIP / pre-VIP) is the segment;
- `geo` is exposed as country and `vip_since` as registered_at for the dossier;
  every other column stays in attributes.
"""

import csv
from pathlib import Path
from typing import Any, ClassVar

from app.ingestion.adapters.sample_v1 import SampleV1Adapter, _clean
from app.ingestion.base import ParsedSource
from app.ingestion.report import IssueLevel
from app.schemas.domain import Player

_MAPPED = ("player_id", "manager", "status")


class TaskV1Adapter(SampleV1Adapter):
    name: ClassVar[str] = "task_v1"

    def _read_players(self, path: Path, out: ParsedSource) -> None:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row_no, row in enumerate(csv.DictReader(handle), start=2):  # 1 = header
                out.players_read += 1
                player_id = _clean(row.get("player_id"))
                if not player_id:
                    self._issue(
                        out, IssueLevel.ERROR, "players", f"row {row_no}", "missing player_id"
                    )
                    continue
                extra = {k: v for k, v in row.items() if k and k not in _MAPPED and v}
                if "geo" in extra:
                    extra["country"] = extra["geo"]
                if "vip_since" in extra:
                    extra["registered_at"] = extra["vip_since"]
                out.players.append(
                    Player(
                        player_id=player_id,
                        display_name=None,
                        manager_id=_clean(row.get("manager")),
                        segment=_clean(row.get("status")),
                        attributes=extra,
                    )
                )

    def _prepare(self, payload: Any, path: Path, out: ParsedSource) -> Any:
        if not isinstance(payload, dict) or not isinstance(payload.get("dialogs"), list):
            return payload  # the generic checks report the shape error
        naive = 0
        dialogs = []
        for raw in payload["dialogs"]:
            if not isinstance(raw, dict):
                dialogs.append(raw)
                continue
            dialog_id = str(raw.get("dialog_id") or "").strip()
            messages = []
            for n, msg in enumerate(raw.get("messages") or [], start=1):
                if not isinstance(msg, dict):
                    messages.append(msg)
                    continue
                stamp = msg.get("sent_at")
                if isinstance(stamp, str) and _naive(stamp):
                    naive += 1
                    stamp = stamp.strip() + "+00:00"
                messages.append(
                    {
                        "id": f"{dialog_id}-{n}" if dialog_id else "",
                        "sender": msg.get("from"),
                        "timestamp": stamp,
                        "text": msg.get("text"),
                    }
                )
            dialogs.append({**raw, "messages": messages})
        if naive:
            self._issue(
                out,
                IssueLevel.WARNING,
                "dialogs",
                path.name,
                f"{naive} timestamps without timezone, assumed UTC",
            )
        return {**payload, "dialogs": dialogs}


def _naive(stamp: str) -> bool:
    text = stamp.strip()
    if text.endswith("Z"):
        return False
    tail = text[10:]  # after the date: a sign here starts an offset
    return "+" not in tail and "-" not in tail
