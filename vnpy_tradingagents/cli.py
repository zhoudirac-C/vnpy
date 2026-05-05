import argparse
import json
import sys
from typing import Any

from .readiness import ProductionReadinessChecker
from .schema_init import initialize_postgres_schema, schema_status
from vnpy_router.peewee import VnpyPostgresConfigError, VnpyPostgresDependencyError


def main(argv: list[str] | None = None) -> int:
    """
    CLI for TradingAgents production schema and readiness operations.
    """
    parser = argparse.ArgumentParser(prog="vnpy-tradingagents")
    subparsers = parser.add_subparsers(dest="command")

    schema_parser = subparsers.add_parser("schema")
    schema_subparsers = schema_parser.add_subparsers(dest="schema_command")

    for command in ("init", "status"):
        schema_subparsers.add_parser(command)

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
    try:
        if args.schema_command == "init":
            result = initialize_postgres_schema()
            print(json.dumps({"tables": result.created_or_existing_tables}))
            return 0

        if args.schema_command == "status":
            status = schema_status()
            print(json.dumps({"tables": status.tables}, ensure_ascii=False, sort_keys=True))
            return 0
    except (VnpyPostgresConfigError, VnpyPostgresDependencyError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

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


if __name__ == "__main__":
    raise SystemExit(main())
