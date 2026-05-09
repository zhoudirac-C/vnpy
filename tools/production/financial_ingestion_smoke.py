from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from vnpy.trader.setting import SETTINGS
from vnpy_router.financial_storage import PostgresFinancialStorage
from vnpy_router.peewee import connect_vnpy_postgres_adapter
from vnpy_router.storage import PostgresSnapshotStorage
from vnpy_tradingagents.financial_ingestion import (
    FinancialIngestionJob,
    build_financial_ingestion_provider,
)


DEFAULT_SYMBOLS: tuple[str, ...] = ("600519.SSE", "000001.SZSE", "688008.SSE")
VALIDATION_DIR = Path("docs/community/ops/validation_results")


def main() -> int:
    args = _parse_args()
    symbols = _split_symbols(args.symbols) or list(DEFAULT_SYMBOLS)
    settings = dict(SETTINGS)
    if args.providers:
        settings["financial.ingestion.providers"] = args.providers

    connection = connect_vnpy_postgres_adapter(settings)
    financial_storage = PostgresFinancialStorage(connection)
    financial_storage.create_schema()
    snapshot_storage = PostgresSnapshotStorage(connection)
    snapshot_storage.create_schema()

    job = FinancialIngestionJob(
        provider=build_financial_ingestion_provider(settings),
        storage=financial_storage,
        snapshot_storage=snapshot_storage,
        lookback_years=args.lookback_years,
    )
    summary = job.run(symbols)
    contexts = {
        symbol: financial_storage.load_financial_context(
            symbol,
            as_of=datetime.now(),
            max_periods=args.max_periods,
        )
        for symbol in symbols
    }
    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "symbols": symbols,
        "summary": {
            "statement_count": summary.statement_count,
            "indicator_count": summary.indicator_count,
            "document_count": summary.document_count,
            "payload_snapshot_count": summary.payload_snapshot_count,
            "degraded_sources": summary.degraded_sources,
            "errors": summary.errors,
        },
        "contexts": contexts,
    }

    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    if args.write_validation_doc:
        path = _write_validation_doc(result)
        print(f"validation_doc={path}")
    return 0 if not summary.errors else 2


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run financial ingestion production smoke.")
    parser.add_argument(
        "--symbols",
        default=",".join(DEFAULT_SYMBOLS),
        help="Comma/semicolon separated vt_symbols.",
    )
    parser.add_argument("--lookback-years", type=int, default=2)
    parser.add_argument("--max-periods", type=int, default=4)
    parser.add_argument(
        "--providers",
        default="",
        help="Override financial.ingestion.providers for this run.",
    )
    parser.add_argument("--write-validation-doc", action="store_true")
    return parser.parse_args()


def _split_symbols(raw: str) -> list[str]:
    text = raw.strip()
    if not text:
        return []
    for sep in (";", "，", "\n"):
        text = text.replace(sep, ",")
    return [item.strip().upper() for item in text.split(",") if item.strip()]


def _write_validation_doc(result: dict[str, Any]) -> Path:
    VALIDATION_DIR.mkdir(parents=True, exist_ok=True)
    path = VALIDATION_DIR / f"{datetime.now():%Y-%m-%d-%H%M%S}-financial-ingestion-smoke.md"
    summary = result["summary"]
    rows = [
        "| 指标 | 值 |",
        "| --- | --- |",
        f"| statement_count | {summary['statement_count']} |",
        f"| indicator_count | {summary['indicator_count']} |",
        f"| document_count | {summary['document_count']} |",
        f"| payload_snapshot_count | {summary['payload_snapshot_count']} |",
        f"| degraded_sources | {', '.join(summary['degraded_sources']) or '-'} |",
        f"| errors | {json.dumps(summary['errors'], ensure_ascii=False) or '-'} |",
    ]
    context_rows = [
        "| 股票 | 财报质量 | 报表数 | 指标数 | 官方文档数 |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for symbol, context in result["contexts"].items():
        context_rows.append(
            "| "
            + " | ".join(
                [
                    symbol,
                    str(context.get("quality_status", "-")),
                    str(len(context.get("statements") or {})),
                    str(len(context.get("indicators") or [])),
                    str(len(context.get("documents") or [])),
                ]
            )
            + " |"
        )

    text = "\n\n".join(
        [
            "# Financial Ingestion Smoke",
            f"- generated_at: `{result['generated_at']}`",
            f"- symbols: `{', '.join(result['symbols'])}`",
            "\n".join(rows),
            "\n".join(context_rows),
            "## Raw Result\n\n```json\n"
            + json.dumps(result, ensure_ascii=False, indent=2, default=str)
            + "\n```",
        ]
    )
    path.write_text(text, encoding="utf-8")
    return path


if __name__ == "__main__":
    raise SystemExit(main())
