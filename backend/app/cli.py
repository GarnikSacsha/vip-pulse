"""Command line entrypoint.

python -m app.cli import --players PLAYERS.csv --dialogs DIALOGS.json [--dry-run]
"""

import argparse
import sys
from pathlib import Path

from app.db import init_db, make_engine, session_scope
from app.ingestion.adapters import ADAPTERS, get_adapter
from app.ingestion.pipeline import ingest
from app.ingestion.report import ImportReport
from app.ingestion.store import save_bundle


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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
