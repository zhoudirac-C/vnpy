import argparse
import json
import sys
from typing import Any

from vnpy.trader.setting import SETTINGS

from .migrations import MigrationRunner
from .readiness import ProductionReadinessChecker
from .schema_init import DEFAULT_MIGRATIONS, initialize_postgres_schema


def main(argv: list[str] | None = None) -> int:
    """
    CLI for TradingAgents production schema and readiness operations.
    """
    parser = argparse.ArgumentParser(prog="vnpy-tradingagents")
    subparsers = parser.add_subparsers(dest="command")

    schema_parser = subparsers.add_parser("schema")
    schema_subparsers = schema_parser.add_subparsers(dest="schema_command")

    for command in ("init", "status"):
        command_parser = schema_subparsers.add_parser(command)
        command_parser.add_argument("--dsn", default="")

    readiness_parser = subparsers.add_parser("readiness")
    readiness_parser.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "schema":
        return _handle_schema(args)
    if args.command == "readiness":
        return _handle_readiness(args)

    parser.print_help(sys.stderr)
    return 2


def _handle_schema(args: argparse.Namespace) -> int:
    """
    Run schema init/status commands.
    """
    dsn: str = str(args.dsn or SETTINGS.get("router.postgres.dsn", "")).strip()
    if not dsn:
        print("PostgreSQL DSN is required. Pass --dsn or set router.postgres.dsn.", file=sys.stderr)
        return 2

    connection = _connect(dsn)
    if args.schema_command == "init":
        result = initialize_postgres_schema(connection)
        print(json.dumps({"applied": result.applied_versions, "skipped": result.skipped_versions}))
        return 0

    if args.schema_command == "status":
        applied = sorted(MigrationRunner(connection, DEFAULT_MIGRATIONS).applied_versions())
        print(json.dumps({"applied": applied}))
        return 0

    print("Unknown schema command", file=sys.stderr)
    return 2


def _handle_readiness(args: argparse.Namespace) -> int:
    """
    Run production readiness checks.
    """
    report = ProductionReadinessChecker().check()
    payload: dict[str, Any] = {
        "status": report.status.value,
        "items": [
            {"name": item.name, "status": item.status.value, "message": item.message}
            for item in report.items
        ],
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(payload["status"])
        for item in payload["items"]:
            print(f"{item['status']}\t{item['name']}\t{item['message']}")
    return 0 if report.status.value != "failed" else 1


def _connect(dsn: str):
    """
    Connect to PostgreSQL with psycopg.
    """
    try:
        psycopg = __import__("psycopg")
    except ModuleNotFoundError as exc:
        raise SystemExit("psycopg is required for schema commands") from exc

    try:
        rows = __import__("psycopg.rows", fromlist=["dict_row"])
    except ModuleNotFoundError as exc:
        raise SystemExit("psycopg.rows is required for schema commands") from exc

    return psycopg.connect(dsn, row_factory=rows.dict_row)


if __name__ == "__main__":
    raise SystemExit(main())
