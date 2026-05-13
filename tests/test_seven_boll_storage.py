from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from peewee import SqliteDatabase

from vnpy_seven_boll.scanner import SevenBollScanResult, SevenBollScanSummary


def test_schema_init_includes_seven_boll_scan_tables() -> None:
    from vnpy_tradingagents.schema_init import initialize_postgres_schema, schema_status

    database = FakePeeweeDatabase()

    result = initialize_postgres_schema(database)
    status = schema_status(database)

    assert "seven_boll_scan_run" in result.created_or_existing_tables
    assert "seven_boll_scan_result" in result.created_or_existing_tables
    assert status.tables["seven_boll_scan_run"] == "ready"
    assert status.tables["seven_boll_scan_result"] == "ready"


def test_seven_boll_storage_saves_scan_results_without_raw_bars() -> None:
    from vnpy_seven_boll.storage import PeeweeSevenBollScanRepository

    database = SqliteDatabase(":memory:")
    repository = PeeweeSevenBollScanRepository(database)
    repository.create_schema()

    first = _summary("run-1", datetime(2024, 1, 2, 15, 5))
    second = _summary("run-2", datetime(2024, 1, 2, 15, 6))

    repository.save_scan_summary(first)
    repository.save_scan_summary(second)

    latest = repository.load_latest_summary()
    history = repository.list_scan_runs(limit=10)

    assert latest is not None
    assert latest.run_id == "run-2"
    assert latest.buy_candidates[0].interval == "d"
    assert latest.buy_candidates[0].concept == "白酒"
    assert latest.buy_candidates[0].signal_types == ("trend_pullback_long",)
    assert [summary.run_id for summary in history] == ["run-2", "run-1"]
    assert "concept" in repository.result_model._meta.fields
    assert set(database.get_tables()) == {
        "seven_boll_scan_run",
        "seven_boll_scan_result",
    }


def test_seven_boll_storage_uses_postgresql_compatible_upsert() -> None:
    """PostgreSQL does not support Peewee replace(), so run rows use on_conflict update."""
    source = Path("vnpy_seven_boll/storage.py").read_text(encoding="utf-8")

    assert ".replace(" not in source
    assert ".on_conflict(" in source
    assert "conflict_target=[self.run_model.scan_run_id]" in source


def _summary(run_id: str, started_at: datetime) -> SevenBollScanSummary:
    result = SevenBollScanResult(
        vt_symbol="600519.SSE",
        name="贵州茅台",
        concept="白酒",
        action="buy_watch",
        score=80,
        buy_score=80,
        sell_score=0,
        signal_types=("trend_pullback_long",),
        reasons=("test_reason",),
        risks=("test_risk",),
        close=100,
        zscore=1,
        bandwidth_percentile=20,
        mid_slope=1,
        rail_zone="upper2_to_upper1",
        regime="trend_up",
        bar_datetime=started_at,
        interval="d",
    )
    return SevenBollScanSummary(
        run_id=run_id,
        started_at=started_at,
        finished_at=started_at + timedelta(seconds=2),
        status="completed",
        total_symbols=1,
        scanned_symbols=1,
        skipped_symbols=0,
        buy_candidates=[result],
        sell_candidates=[],
        errors=[],
    )


class FakePeeweeDatabase:
    def __init__(self) -> None:
        self.existing_tables = set()
        self.created_models = []
        self.connected = False
        self.safe = None
        self.executed_sql = []

    def connect(self, reuse_if_open=False) -> None:
        self.connected = reuse_if_open

    def create_tables(self, models, safe=False) -> None:
        self.created_models = list(models)
        self.safe = safe
        for model in models:
            self.existing_tables.add(model._meta.table_name)

    def execute_sql(self, sql, params=None):
        self.executed_sql.append(sql)

    def get_tables(self):
        return sorted(self.existing_tables)
