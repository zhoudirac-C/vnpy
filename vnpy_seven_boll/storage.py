"""
Persistence for seven-rail Bollinger scan runs and results.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from .models import build_seven_boll_extension_models
from .scanner import SevenBollScanResult, SevenBollScanSummary


class PeeweeSevenBollScanRepository:
    """
    Peewee repository that stores scan results, not raw K-line bars.
    """

    def __init__(self, database: Any) -> None:
        self.database = database
        models = build_seven_boll_extension_models(database)
        self.run_model = models[0]
        self.result_model = models[1]

    def create_schema(self) -> None:
        """
        Create seven-boll scan tables idempotently.
        """
        self.database.connect(reuse_if_open=True)
        self.database.create_tables([self.run_model, self.result_model], safe=True)
        self._ensure_result_schema()

    def save_scan_summary(self, summary: SevenBollScanSummary, scan_type: str = "manual") -> None:
        """
        Save one scan run and its result rows.
        """
        self.database.connect(reuse_if_open=True)
        candidates = summary.all_candidates
        run_payload = {
            "scan_run_id": summary.run_id,
            "scan_type": scan_type,
            "status": summary.status,
            "started_at": summary.started_at,
            "finished_at": summary.finished_at,
            "total_symbols": summary.total_symbols,
            "scanned_symbols": summary.scanned_symbols,
            "skipped_symbols": summary.skipped_symbols,
            "buy_count": len(summary.buy_candidates),
            "sell_count": len(summary.sell_candidates),
            "errors_json": _json_dumps(summary.errors),
        }
        update_payload = {
            key: value
            for key, value in run_payload.items()
            if key != "scan_run_id"
        }
        self.run_model.insert(**run_payload).on_conflict(
            conflict_target=[self.run_model.scan_run_id],
            update=update_payload,
        ).execute()

        self.result_model.delete().where(self.result_model.scan_run_id == summary.run_id).execute()
        for index, result in enumerate(candidates, start=1):
            self.result_model.insert(**self._result_payload(summary.run_id, index, result)).execute()

    def load_latest_summary(self) -> SevenBollScanSummary | None:
        """
        Load the newest scan run with candidate rows.
        """
        row = (
            self.run_model.select()
            .order_by(self.run_model.finished_at.desc(), self.run_model.started_at.desc())
            .first()
        )
        if row is None:
            return None
        return self._summary_from_run(row)

    def list_scan_runs(self, limit: int = 50) -> list[SevenBollScanSummary]:
        """
        List newest scan runs with result rows.
        """
        rows = (
            self.run_model.select()
            .order_by(self.run_model.finished_at.desc(), self.run_model.started_at.desc())
            .limit(limit)
        )
        return [self._summary_from_run(row) for row in rows]

    def _summary_from_run(self, row: Any) -> SevenBollScanSummary:
        result_rows = (
            self.result_model.select()
            .where(self.result_model.scan_run_id == row.scan_run_id)
            .order_by(self.result_model.score.desc(), self.result_model.vt_symbol.asc())
        )
        buy_candidates: list[SevenBollScanResult] = []
        sell_candidates: list[SevenBollScanResult] = []
        for result_row in result_rows:
            result = self._result_from_row(result_row)
            if result.action == "buy_watch":
                buy_candidates.append(result)
            elif result.action == "sell_watch":
                sell_candidates.append(result)

        return SevenBollScanSummary(
            run_id=row.scan_run_id,
            started_at=row.started_at,
            finished_at=row.finished_at,
            status=row.status,
            total_symbols=row.total_symbols,
            scanned_symbols=row.scanned_symbols,
            skipped_symbols=row.skipped_symbols,
            buy_candidates=buy_candidates,
            sell_candidates=sell_candidates,
            errors=tuple(_json_loads(row.errors_json)),
        )

    def _result_payload(
        self,
        scan_run_id: str,
        index: int,
        result: SevenBollScanResult,
    ) -> dict[str, Any]:
        return {
            "result_id": f"{scan_run_id}:{index:04d}:{result.vt_symbol}",
            "scan_run_id": scan_run_id,
            "vt_symbol": result.vt_symbol,
            "name": result.name,
            "concept": result.concept or None,
            "action": result.action,
            "score": result.score,
            "buy_score": result.buy_score,
            "sell_score": result.sell_score,
            "signal_types_json": _json_dumps(result.signal_types),
            "reasons_json": _json_dumps(result.reasons),
            "risks_json": _json_dumps(result.risks),
            "close": result.close,
            "zscore": result.zscore,
            "bandwidth_percentile": result.bandwidth_percentile,
            "mid_slope": result.mid_slope,
            "rail_zone": result.rail_zone,
            "regime": result.regime,
            "bar_datetime": _as_datetime(result.bar_datetime),
            "interval": result.interval,
            "analysis_run_id": result.report_run_id or None,
            "analysis_status": None,
        }

    def _result_from_row(self, row: Any) -> SevenBollScanResult:
        return SevenBollScanResult(
            vt_symbol=row.vt_symbol,
            name=row.name,
            concept=row.concept or "",
            action=row.action,
            score=row.score,
            buy_score=row.buy_score,
            sell_score=row.sell_score,
            signal_types=tuple(_json_loads(row.signal_types_json)),
            reasons=tuple(_json_loads(row.reasons_json)),
            risks=tuple(_json_loads(row.risks_json)),
            close=row.close,
            zscore=row.zscore,
            bandwidth_percentile=row.bandwidth_percentile,
            mid_slope=row.mid_slope,
            rail_zone=row.rail_zone,
            regime=row.regime,
            bar_datetime=row.bar_datetime,
            interval=row.interval,
            report_run_id=row.analysis_run_id or "",
        )

    def _ensure_result_schema(self) -> None:
        """
        Add post-initial result columns without a standalone migration runner.
        """
        self._ensure_column("seven_boll_scan_result", "concept", "TEXT")

    def _ensure_column(self, table_name: str, column_name: str, definition: str) -> None:
        try:
            columns = self.database.get_columns(table_name)
            if any(getattr(column, "name", "") == column_name for column in columns):
                return
        except Exception:
            pass

        execute_sql = getattr(self.database, "execute_sql", None)
        if not callable(execute_sql):
            return

        try:
            execute_sql(
                f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {definition}'
            )
        except Exception as exc:
            message = str(exc).lower()
            if "duplicate" not in message and "already exists" not in message:
                raise


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_loads(value: str) -> list[Any]:
    if not value:
        return []
    loaded = json.loads(value)
    return list(loaded if isinstance(loaded, list) else [loaded])


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))
