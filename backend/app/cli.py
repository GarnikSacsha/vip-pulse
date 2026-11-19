"""Command line entrypoint.

python -m app.cli import --players PLAYERS.csv --dialogs DIALOGS.json [--dry-run]
python -m app.cli triage [--limit N]
"""

import argparse
import sys
from pathlib import Path

from app.analysis.llm import get_provider
from app.config import get_settings
from app.db import init_db, make_engine, session_scope
from app.ingestion.adapters import ADAPTERS, get_adapter
from app.ingestion.pipeline import ingest
from app.ingestion.report import ImportReport
from app.ingestion.store import load_conversations, load_players, save_bundle
from app.policy.config import PolicyConfig
from app.triage import TriageItem, triage


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


def _print_queue(items: list[TriageItem]) -> None:
    header = (
        f"{'P':3} {'conv':6} {'player':7} {'channel':9} {'category':19} {'wait':>6}  {'route':14}"
    )
    print(header + "  next action")
    print("-" * (len(header) + 40))
    for item in items:
        d, f = item.decision, item.facts
        result = item.analysis.result
        category = result.category.value if result else "(failed)"
        wait = f"{f.wait_hours:.0f}h" if f.wait_hours is not None else "-"
        marks = " [review]" if d.requires_human_review else ""
        marks += "".join(f" [{q}]" for q in d.quality_flags)
        print(
            f"{d.priority.value:3} {item.conversation.conversation_id:6} "
            f"{item.conversation.player_id:7} {item.conversation.channel.value:9} "
            f"{category:19} {wait:>6}  {d.route.value:14}  {_short(d.next_action, 60)}{marks}"
        )
        print(f"{'':4}why: " + "; ".join(r.text for r in d.reasons))


def cmd_triage(args: argparse.Namespace) -> int:
    settings = get_settings()
    cfg = PolicyConfig.load(args.policy or settings.policy_path)
    engine = make_engine(args.database_url)
    init_db(engine)
    for session in session_scope(engine):
        conversations, players = load_conversations(session), load_players(session)
    if not conversations:
        print("no conversations in the database; run `import` first", file=sys.stderr)
        return 1
    provider = get_provider(settings)
    items = triage(conversations, players, provider, cfg)
    as_of = items[0].facts.as_of
    print(f"as of {as_of:%Y-%m-%d %H:%M} UTC · provider {provider.name}:{provider.model}")
    print(f"{len(items)} conversations\n")
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

    tri = sub.add_parser("triage", help="analyse stored conversations and print the work queue")
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
