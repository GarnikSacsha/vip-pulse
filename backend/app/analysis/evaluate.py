"""Quality check of stored analyses against hand labels (the gold set).

Scores only: it reads analyses already in the database and makes no LLM calls, so measuring
quality never spends budget twice. Run `triage` with the provider to measure first.
"""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.analysis import ManagerErrorCode

FIELDS = ("category", "requires_action", "safety_flag", "sentiment")


class GoldLabel(BaseModel):
    """Acceptable answers per field. Several values = a careful human could go either way."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    category: list[str]
    requires_action: list[bool]
    safety_flag: list[str]
    sentiment: list[str]
    # At least one of these must be cited when the model has to cite (action or safety flag).
    cite: list[str] = Field(default_factory=list)
    # Acceptable sets of manager-error codes; None = not labelled, not scored.
    manager_errors: list[list[ManagerErrorCode]] | None = None


class EvalReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    # field -> (correct, total)
    scores: dict[str, tuple[int, int]]
    # (conversation, field, got, expected)
    mismatches: list[tuple[str, str, str, str]]
    failed: list[str]  # no successful analysis: counted wrong on every field
    safety_misses: list[str]  # a safety flag expected but not raised: the costly error


def load_gold(path: str | Path) -> dict[str, GoldLabel]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return {str(cid): GoldLabel.model_validate(label) for cid, label in raw.items()}


def _show(value: Any) -> str:
    return str(value).lower() if isinstance(value, bool) else str(value)


def evaluate(results: dict[str, dict[str, Any] | None], gold: dict[str, GoldLabel]) -> EvalReport:
    """Compare analysis results (LLMAnalysis as dicts, None when failed) with the gold set."""
    names = (*FIELDS, "evidence", "manager_errors")
    correct = dict.fromkeys(names, 0)
    total = dict.fromkeys(names, 0)
    mismatches: list[tuple[str, str, str, str]] = []
    failed: list[str] = []
    safety_misses: list[str] = []

    for cid in sorted(gold):
        label = gold[cid]
        result = results.get(cid)
        if result is None:
            failed.append(cid)
            for name in names:
                if name != "manager_errors" or label.manager_errors is not None:
                    total[name] += 1
            if label.safety_flag != ["none"]:
                safety_misses.append(cid)
            continue

        for name in FIELDS:
            expected: list[Any] = getattr(label, name)
            got = result.get(name)
            total[name] += 1
            if got in expected:
                correct[name] += 1
            else:
                mismatches.append((cid, name, _show(got), " | ".join(map(_show, expected))))

        total["evidence"] += 1
        cited = list(result.get("evidence_message_ids") or [])
        if not label.cite or set(cited) & set(label.cite):
            correct["evidence"] += 1
        else:
            mismatches.append((cid, "evidence", ", ".join(cited) or "-", " | ".join(label.cite)))

        if label.manager_errors is not None:
            total["manager_errors"] += 1
            got_codes = {e.get("code") for e in result.get("manager_errors") or []}
            if any(got_codes == {c.value for c in ok} for ok in label.manager_errors):
                correct["manager_errors"] += 1
            else:
                mismatches.append(
                    (
                        cid,
                        "manager_errors",
                        ", ".join(sorted(map(str, got_codes))) or "-",
                        " | ".join(
                            ", ".join(c.value for c in ok) or "-" for ok in label.manager_errors
                        ),
                    )
                )

        if "none" not in label.safety_flag and result.get("safety_flag") not in label.safety_flag:
            safety_misses.append(cid)

    return EvalReport(
        # An unlabelled optional field is left out instead of showing 0/0.
        scores={
            name: (correct[name], total[name])
            for name in names
            if total[name] or name != "manager_errors"
        },
        mismatches=mismatches,
        failed=failed,
        safety_misses=safety_misses,
    )
