"""Command line entrypoint.

python -m app.cli import --players PLAYERS.csv --dialogs DIALOGS.json [--dry-run]
python -m app.cli triage [--limit N]   # analyse, save work items, print the queue
"""

import argparse
import sys
from pathlib import Path

from app.analysis.llm import get_provider
from app.api.queue import list_queue
from app.api.schemas import QueueItem
from app.config import get_settings
from app.db import init_db, make_engine, session_scope
from app.ingestion.adapters import ADAPTERS, get_adapter
from app.ingestion.pipeline import ingest
from app.ingestion.report import ImportReport
from app.ingestion.store import load_conversations, save_bundle
from app.policy.config import PolicyConfig
from app.policy.facts import dataset_as_of
from app.tasks.service import RunInProgress, run_triage


def _print_report(report: ImportReport) -> None:
    print(f"adapter:        {report.adapter}")
    print(f"players:        {report.players_kept} kept / {report.players_read} read")
    print(f"conversations:  {report.conversations_kept} kept / {report.conversations_read} read")
    print(f"messages:       {report.messages_kept} kept")
    print(f"issues:         {len(report.errors)} errors, {len(report.warnings)} warnings")
    for issue in report.issues:
        print(f"  [{issue.level.value:7}] {issue.source}:{issue.ref} - {issue.reason}")


def cmd_import(args: argparse.Namespace) -> int:
    for path in (args.players, args.dialogs):
        if not path.is_file():
            print(f"file not found: {path}", file=sys.stderr)
            return 2
    bundle = ingest(get_adapter(args.adapter), args.players, args.dialogs)
    _print_report(bundle.report)
    if args.dry_run:
        print("dry run: nothing saved")
        return 0
    engine = make_engine(args.database_url)
    init_db(engine)
    for session in session_scope(engine):
        stored = save_bundle(session, bundle)
    print(
        f"saved:          players +{stored.players_created} ~{stored.players_updated}, "
        f"conversations +{stored.conversations_created} ~{stored.conversations_updated}"
    )
    return 0


def _short(text: str | None, width: int) -> str:
    text = " ".join((text or "-").split())
    return text if len(text) <= width else text[: width - 1] + "…"


def _print_queue(items: list[QueueItem]) -> None:
    header = (
        f"{'P':3} {'conv':6} {'player':7} {'channel':9} {'category':19} {'wait':>6}  {'route':14}"
    )
    print(header + "  next action")
    print("-" * (len(header) + 40))
    for item in items:
        category = item.category.value if item.category else "(failed)"
        wait = f"{item.wait_hours:.0f}h" if item.wait_hours is not None else "-"
        marks = " [review]" if item.requires_review else ""
        marks += "".join(f" [{q}]" for q in item.quality_flags)
        print(
            f"{item.priority.value:3} {item.conversation_id:6} "
            f"{item.player.player_id:7} {item.channel.value:9} "
            f"{category:19} {wait:>6}  {item.route.value:14}  "
            f"{_short(item.next_action, 60)}{marks}"
        )
        print(f"{'':4}why: " + "; ".join(r.text for r in item.reasons))


def cmd_triage(args: argparse.Namespace) -> int:
    settings = get_settings()
    cfg = PolicyConfig.load(args.policy or settings.policy_path)
    engine = make_engine(args.database_url)
    init_db(engine)
    provider = get_provider(settings)
    for session in session_scope(engine):
        if not load_conversations(session):
            print("no conversations in the database; run `import` first", file=sys.stderr)
            return 1
        try:
            summary = run_triage(session, provider, cfg)
        except RunInProgress:
            print("a triage run is already in progress", file=sys.stderr)
            return 1
        items = list_queue(session)
        as_of = dataset_as_of(load_conversations(session))
    print(f"as of {as_of:%Y-%m-%d %H:%M} UTC · provider {provider.name}:{provider.model}")
    print(
        f"analysed {summary.analysed}, reused {summary.reused}, failed {summary.failed} · "
        f"tasks +{summary.created} ~{summary.updated}, reopened {summary.reopened}"
    )
    if summary.budget_left_usd is not None:
        print(f"LLM spend this run ${summary.spent_usd:.4f}, left ${summary.budget_left_usd:.4f}")
    if summary.budget_exhausted:
        print("spending limit reached: some conversations were not analysed (LLM_BUDGET_USD)")
    print()
    _print_queue(items[: args.limit] if args.limit else items)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vip-pulse")
    sub = parser.add_subparsers(dest="command", required=True)

    imp = sub.add_parser("import", help="import players.csv + dialogs.json into the database")
    imp.add_argument("--players", type=Path, required=True)
    imp.add_argument("--dialogs", type=Path, required=True)
    imp.add_argument("--adapter", default="sample_v1", choices=sorted(ADAPTERS))
    imp.add_argument("--database-url", default=None, help="defaults to DATABASE_URL")
    imp.add_argument("--dry-run", action="store_true", help="validate only, do not save")
    imp.set_defaults(func=cmd_import)

    tri = sub.add_parser(
        "triage", help="analyse stored conversations, save work items and print the queue"
    )
    tri.add_argument("--database-url", default=None, help="defaults to DATABASE_URL")
    tri.add_argument("--policy", default=None, help="thresholds YAML, defaults to POLICY_PATH")
    tri.add_argument("--limit", type=int, default=0, help="show only the first N items")
    tri.set_defaults(func=cmd_triage)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
