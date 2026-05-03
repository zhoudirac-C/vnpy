from datetime import datetime

from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import HistoryRequest
from vnpy.trader.setting import SETTINGS


def test_get_datafeed_loads_router_datafeed(monkeypatch):
    """get_datafeed should load vnpy_router when datafeed.name is router."""
    from vnpy.trader import datafeed as datafeed_module

    monkeypatch.setitem(SETTINGS, "datafeed.name", "router")
    monkeypatch.setattr(datafeed_module, "datafeed", None)

    datafeed = datafeed_module.get_datafeed()

    from vnpy_router import Datafeed

    assert isinstance(datafeed, Datafeed)


def test_datafeed_builds_only_configured_local_file_provider(monkeypatch, tmp_path):
    """Datafeed should not instantiate AKShare when only local_file is enabled."""
    from vnpy_router import datafeed as datafeed_module

    def fail_akshare_provider():
        raise AssertionError("AkshareProvider should not be built")

    monkeypatch.setitem(SETTINGS, "router.local_path", str(tmp_path))
    monkeypatch.setitem(SETTINGS, "router.providers", "local_file")
    monkeypatch.setattr(datafeed_module, "AkshareProvider", fail_akshare_provider)

    datafeed = datafeed_module.Datafeed()

    assert [provider.name for provider in datafeed.router.providers] == ["local_file"]


def test_datafeed_honors_configured_provider_order(monkeypatch, tmp_path):
    """Datafeed should use configured provider order for router fallback."""
    from vnpy_router import datafeed as datafeed_module

    class FakeAkshareProvider:
        name = "akshare"

        def init(self, output=print):
            return True

        def query_bar_history(self, req, output=print):
            return []

    monkeypatch.setitem(SETTINGS, "router.local_path", str(tmp_path))
    monkeypatch.setitem(SETTINGS, "router.providers", '["akshare", "local_file"]')
    monkeypatch.setattr(datafeed_module, "AkshareProvider", FakeAkshareProvider)

    datafeed = datafeed_module.Datafeed()

    assert [provider.name for provider in datafeed.router.providers] == [
        "akshare",
        "local_file",
    ]


def test_local_file_provider_returns_bar_data(tmp_path):
    """LocalFileProvider should map CSV rows into vn.py BarData."""
    csv_file = tmp_path / "600519.SSE_d.csv"
    csv_file.write_text(
        "\n".join(
            [
                "datetime,open,high,low,close,volume,turnover,open_interest",
                "2024-01-02,1680,1690,1670,1688,1000,1688000,0",
                "2024-01-03,1688,1700,1680,1695,1200,2034000,0",
            ]
        ),
        encoding="utf-8",
    )

    from vnpy_router.providers.local_file import LocalFileProvider

    provider = LocalFileProvider(base_path=tmp_path)
    req = HistoryRequest(
        symbol="600519",
        exchange=Exchange.SSE,
        interval=Interval.DAILY,
        start=datetime(2024, 1, 3),
        end=datetime(2024, 1, 3),
    )

    bars = provider.query_bar_history(req)

    assert len(bars) == 1
    bar = bars[0]
    assert bar.vt_symbol == "600519.SSE"
    assert bar.interval == Interval.DAILY
    assert bar.datetime == datetime(2024, 1, 3)
    assert bar.open_price == 1688
    assert bar.high_price == 1700
    assert bar.low_price == 1680
    assert bar.close_price == 1695
    assert bar.volume == 1200
    assert bar.turnover == 2034000
    assert bar.gateway_name == "local_file"
    assert bar.extra["provider_name"] == "local_file"
    assert bar.extra["provider_endpoint"].endswith("600519.SSE_d.csv")


def test_quality_checker_reports_invalid_bar():
    """DataQualityChecker should flag impossible OHLC relationships."""
    from vnpy.trader.object import BarData
    from vnpy_router.quality import QualityStatus, check_bar_data

    bar = BarData(
        symbol="600519",
        exchange=Exchange.SSE,
        datetime=datetime(2024, 1, 2),
        interval=Interval.DAILY,
        open_price=10,
        high_price=9,
        low_price=8,
        close_price=10,
        volume=100,
        gateway_name="local_file",
    )

    report = check_bar_data("local_file", [bar])

    assert report.status == QualityStatus.FAILED
    assert report.issues[0].code == "invalid_high_price"


def test_postgres_snapshot_storage_saves_bar_with_provider_metadata():
    """PostgresSnapshotStorage should persist provider metadata with bar data."""
    from vnpy.trader.object import BarData
    from vnpy_router.storage import PostgresSnapshotStorage

    connection = FakeConnection()
    storage = PostgresSnapshotStorage(connection)
    bar = BarData(
        symbol="600519",
        exchange=Exchange.SSE,
        datetime=datetime(2024, 1, 2),
        interval=Interval.DAILY,
        open_price=1680,
        high_price=1690,
        low_price=1670,
        close_price=1688,
        volume=1000,
        turnover=1688000,
        gateway_name="local_file",
    )
    bar.extra = {
        "provider_name": "local_file",
        "provider_endpoint": "/tmp/600519.SSE_d.csv",
        "provider_version": "hash:abc",
        "quality_status": "passed",
    }

    storage.save_bar_snapshots([bar])

    assert connection.committed
    sql, params = connection.cursor_obj.executed[-1]
    assert "INSERT INTO market_bar_snapshot" in sql
    assert "ON CONFLICT" in sql
    assert params["vt_symbol"] == "600519.SSE"
    assert params["provider_name"] == "local_file"
    assert params["provider_endpoint"] == "/tmp/600519.SSE_d.csv"
    assert params["provider_version"] == "hash:abc"
    assert params["quality_status"] == "passed"


def test_postgres_snapshot_schema_contains_provider_columns():
    """PostgreSQL schema should include provider traceability columns."""
    from vnpy_router.storage import MARKET_BAR_SNAPSHOT_SCHEMA, RESEARCH_SNAPSHOT_SCHEMA

    assert "CREATE TABLE IF NOT EXISTS market_bar_snapshot" in MARKET_BAR_SNAPSHOT_SCHEMA
    assert "provider_name TEXT NOT NULL" in MARKET_BAR_SNAPSHOT_SCHEMA
    assert "provider_endpoint TEXT" in MARKET_BAR_SNAPSHOT_SCHEMA
    assert "quality_status TEXT" in MARKET_BAR_SNAPSHOT_SCHEMA
    for table_name in [
        "fundamental_snapshot",
        "valuation_snapshot",
        "industry_snapshot",
        "benchmark_snapshot",
        "portfolio_snapshot",
    ]:
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in RESEARCH_SNAPSHOT_SCHEMA

    assert RESEARCH_SNAPSHOT_SCHEMA.count("provider_name TEXT NOT NULL") == 5
    assert RESEARCH_SNAPSHOT_SCHEMA.count("provider_version TEXT") == 5
    assert RESEARCH_SNAPSHOT_SCHEMA.count("pulled_at TIMESTAMPTZ DEFAULT now()") == 5
    assert RESEARCH_SNAPSHOT_SCHEMA.count("quality_status TEXT") == 5
    assert RESEARCH_SNAPSHOT_SCHEMA.count("payload JSONB NOT NULL") == 5


def test_postgres_snapshot_storage_create_schema_includes_research_snapshots():
    """PostgresSnapshotStorage should create market and research snapshot tables."""
    from vnpy_router.storage import PostgresSnapshotStorage

    connection = FakeConnection()
    storage = PostgresSnapshotStorage(connection)

    storage.create_schema()

    sql = connection.cursor_obj.executed[0][0]
    assert connection.committed
    assert "CREATE TABLE IF NOT EXISTS market_bar_snapshot" in sql
    assert "CREATE TABLE IF NOT EXISTS fundamental_snapshot" in sql
    assert "CREATE TABLE IF NOT EXISTS portfolio_snapshot" in sql


def test_postgres_snapshot_reader_loads_bar_snapshots_with_filters():
    """PostgresSnapshotReader should load market bars for TradingAgents context."""
    from vnpy_router.storage import PostgresSnapshotReader

    connection = FakeConnection(
        fetchall_result=[
            {
                "vt_symbol": "600519.SSE",
                "symbol": "600519",
                "exchange": "SSE",
                "interval": "d",
                "datetime": datetime(2024, 1, 3),
                "open_price": 1688,
                "high_price": 1700,
                "low_price": 1680,
                "close_price": 1695,
                "volume": 1200,
                "turnover": 2034000,
                "open_interest": 0,
                "provider_name": "local_file",
                "provider_endpoint": "/tmp/600519.SSE_d.csv",
                "provider_version": "hash:abc",
                "adjustment": "none",
                "quality_status": "passed",
                "quality_report_id": "qr-1",
            }
        ]
    )
    reader = PostgresSnapshotReader(connection)

    rows = reader.load_bar_snapshots(
        vt_symbol="600519.SSE",
        start=datetime(2024, 1, 1),
        end=datetime(2024, 1, 3),
        interval="d",
        provider_name="local_file",
    )

    sql, params = connection.cursor_obj.executed[0]
    assert "FROM market_bar_snapshot" in sql
    assert "interval = %(interval)s" in sql
    assert "provider_name = %(provider_name)s" in sql
    assert params["vt_symbol"] == "600519.SSE"
    assert params["interval"] == "d"
    assert params["provider_name"] == "local_file"
    assert rows == [
        {
            "vt_symbol": "600519.SSE",
            "symbol": "600519",
            "exchange": "SSE",
            "interval": "d",
            "datetime": "2024-01-03T00:00:00",
            "open_price": 1688,
            "high_price": 1700,
            "low_price": 1680,
            "close_price": 1695,
            "volume": 1200,
            "turnover": 2034000,
            "open_interest": 0,
            "provider_name": "local_file",
            "provider_endpoint": "/tmp/600519.SSE_d.csv",
            "provider_version": "hash:abc",
            "adjustment": "none",
            "quality_status": "passed",
            "quality_report_id": "qr-1",
        }
    ]


def test_postgres_snapshot_reader_loads_latest_payload_snapshot():
    """PostgresSnapshotReader should load latest payload snapshot with provider metadata."""
    from vnpy_router.storage import PostgresSnapshotReader

    connection = FakeConnection(
        fetchone_result={
            "as_of": datetime(2024, 1, 3),
            "provider_name": "akshare",
            "provider_version": "2024-01-03",
            "quality_status": "passed",
            "payload": {
                "pe": 25.2,
                "roe": 0.18,
            },
        }
    )
    reader = PostgresSnapshotReader(connection)

    snapshot = reader.load_latest_snapshot(
        snapshot_type="fundamentals",
        vt_symbol="600519.SSE",
        as_of=datetime(2024, 1, 4),
    )

    sql, params = connection.cursor_obj.executed[0]
    assert "FROM fundamental_snapshot" in sql
    assert "as_of <= %(as_of)s" in sql
    assert params["vt_symbol"] == "600519.SSE"
    assert snapshot == {
        "pe": 25.2,
        "roe": 0.18,
        "_snapshot_type": "fundamentals",
        "_as_of": "2024-01-03T00:00:00",
        "_provider_name": "akshare",
        "_provider_version": "2024-01-03",
        "_quality_status": "passed",
    }


def test_postgres_snapshot_reader_returns_none_for_missing_or_deferred_snapshot():
    """PostgresSnapshotReader should degrade cleanly when a snapshot is missing."""
    from vnpy_router.storage import PostgresSnapshotReader

    reader = PostgresSnapshotReader(FakeConnection(fetchone_result=None))

    assert (
        reader.load_latest_snapshot(
            snapshot_type="fundamentals",
            vt_symbol="600519.SSE",
            as_of=datetime(2024, 1, 4),
        )
        is None
    )
    assert (
        reader.load_latest_snapshot(
            snapshot_type="news",
            vt_symbol="600519.SSE",
            as_of=datetime(2024, 1, 4),
        )
        is None
    )


def test_akshare_provider_missing_dependency_degrades(monkeypatch):
    """AkshareProvider should degrade to empty data when akshare is missing."""
    import importlib

    real_import_module = importlib.import_module

    def fake_import_module(name: str, package: str | None = None):
        if name == "akshare":
            raise ModuleNotFoundError(name)
        return real_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    from vnpy_router.providers.akshare import AkshareProvider

    messages: list[str] = []
    provider = AkshareProvider()
    req = HistoryRequest(
        symbol="600519",
        exchange=Exchange.SSE,
        interval=Interval.DAILY,
        start=datetime(2024, 1, 1),
        end=datetime(2024, 1, 3),
    )

    assert not provider.init(output=messages.append)
    assert provider.query_bar_history(req, output=messages.append) == []
    assert any("akshare" in message.lower() for message in messages)


class FakeCursor:
    """Tiny DB-API cursor fake for storage unit tests."""

    def __init__(
        self,
        fetchall_result: list[dict] | None = None,
        fetchone_result: dict | None = None,
    ) -> None:
        self.executed: list[tuple[str, dict]] = []
        self.fetchall_result: list[dict] = fetchall_result or []
        self.fetchone_result: dict | None = fetchone_result

    def execute(self, sql: str, params: dict | None = None) -> None:
        self.executed.append((sql, params or {}))

    def fetchall(self) -> list[dict]:
        return self.fetchall_result

    def fetchone(self) -> dict | None:
        return self.fetchone_result

    def close(self) -> None:
        return


class FakeConnection:
    """Tiny DB-API connection fake for storage unit tests."""

    def __init__(
        self,
        fetchall_result: list[dict] | None = None,
        fetchone_result: dict | None = None,
    ) -> None:
        self.cursor_obj = FakeCursor(fetchall_result, fetchone_result)
        self.committed = False

    def cursor(self) -> FakeCursor:
        return self.cursor_obj

    def commit(self) -> None:
        self.committed = True
