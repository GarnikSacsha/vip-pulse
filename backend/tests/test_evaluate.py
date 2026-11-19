"""Quality check of the analysis against hand labels: scoring only, no LLM calls."""

from pathlib import Path

import pytest

from app.analysis.evaluate import GoldLabel, evaluate, load_gold
from app.cli import main

GOLD = Path(__file__).resolve().parents[2] / "data" / "sample" / "gold.yaml"


def _result(**overrides: object) -> dict:
    base = {
        "category": "withdrawal",
        "sentiment": "negative",
        "urgency": "high",
        "summary": "s",
        "requires_action": True,
        "next_action": "n",
        "needs_escalation": False,
        "safety_flag": "none",
        "evidence_message_ids": ["m-1"],
        "confidence": 0.9,
    }
    return base | overrides


LABEL = GoldLabel(
    category=["withdrawal"],
    requires_action=[True],
    safety_flag=["none"],
    sentiment=["negative", "neutral"],
    cite=["m-1", "m-2"],
)


def test_gold_file_covers_the_sample() -> None:
    gold = load_gold(GOLD)
    assert set(gold) == {f"d-00{i}" for i in (1, 2, 3, 4, 5, 6, 7, 9)} | {"d-010"}
    assert gold["d-004"].safety_flag == ["responsible_gaming"]


def test_every_field_scores_against_the_acceptable_answers() -> None:
    report = evaluate({"c1": _result(sentiment="neutral")}, {"c1": LABEL})
    assert report.scores == {
        "category": (1, 1),
        "requires_action": (1, 1),
        "safety_flag": (1, 1),
        "sentiment": (1, 1),
        "evidence": (1, 1),
    }
    assert report.mismatches == []


def test_mismatches_name_the_conversation_field_and_answers() -> None:
    report = evaluate(
        {"c1": _result(category="deposit", evidence_message_ids=["m-9"])}, {"c1": LABEL}
    )
    assert report.scores["category"] == (0, 1)
    assert report.scores["evidence"] == (0, 1)
    assert ("c1", "category", "deposit", "withdrawal") in report.mismatches
    assert ("c1", "evidence", "m-9", "m-1 | m-2") in report.mismatches


def test_failed_or_missing_analysis_counts_as_wrong_everywhere() -> None:
    report = evaluate({"c1": None}, {"c1": LABEL, "c2": LABEL})
    assert report.failed == ["c1", "c2"]
    assert report.scores["category"] == (0, 2)


def test_safety_misses_are_listed_separately() -> None:
    gold = {
        "c1": GoldLabel(
            category=["responsible_gaming"],
            requires_action=[True],
            safety_flag=["responsible_gaming"],
            sentiment=["negative"],
            cite=[],
        )
    }
    report = evaluate({"c1": _result(category="responsible_gaming")}, gold)
    assert report.safety_misses == ["c1"]


def test_cli_scores_the_stored_analyses(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    sample = GOLD.parent
    db = f"sqlite:///{(tmp_path / 'eval.db').as_posix()}"
    assert (
        main(
            [
                "import",
                "--players",
                str(sample / "players.csv"),
                "--dialogs",
                str(sample / "dialogs.json"),
                "--database-url",
                db,
            ]
        )
        == 0
    )
    assert main(["triage", "--database-url", db]) == 0
    capsys.readouterr()

    assert main(["eval", "--gold", str(GOLD), "--database-url", db]) == 0
    out = capsys.readouterr().out
    assert "9 conversations" in out
    assert "simulated" in out  # the offline heuristic is never reported as a model
    assert "category" in out and "safety_flag" in out
