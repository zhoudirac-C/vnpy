from datetime import datetime

from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import BarData, TickData


def test_intraday_collector_builds_snapshot_from_minute_bars():
    """Collector should turn Gateway minute bars into IntradaySnapshot."""
    from vnpy_tradingagents.intraday_collector import IntradaySnapshotCollector

    collector = IntradaySnapshotCollector(
        position_provider=lambda vt_symbol: {"volume": 100},
        trading_rules_provider=lambda vt_symbol: {"discipline": "no_chase"},
    )
    collector.update_bar(make_bar(close=10))
    collector.update_bar(make_bar(close=11, at=datetime(2024, 1, 3, 9, 31)))

    snapshot = collector.build_snapshot("600519.SSE")

    assert snapshot.vt_symbol == "600519.SSE"
    assert snapshot.indicators["last_price"] == 11
    assert snapshot.position == {"volume": 100}
    assert snapshot.trading_rules == {"discipline": "no_chase"}
    assert snapshot.to_context()["intraday"]["bars"][-1]["close"] == 11


def test_intraday_collector_builds_snapshot_from_tick():
    """Collector should support tick input when minute bars are unavailable."""
    from vnpy_tradingagents.intraday_collector import IntradaySnapshotCollector

    collector = IntradaySnapshotCollector()
    collector.update_tick(make_tick(last_price=10.5))

    snapshot = collector.build_snapshot("600519.SSE")

    assert snapshot.interval == "tick"
    assert snapshot.indicators["last_price"] == 10.5
    assert snapshot.bars[-1]["close"] == 10.5


def test_intraday_collector_saves_snapshot_when_storage_is_configured():
    """Collector should persist generated snapshots for replay reuse."""
    from vnpy_tradingagents.intraday_collector import IntradaySnapshotCollector

    storage = RecordingSnapshotStorage()
    collector = IntradaySnapshotCollector(storage=storage)
    collector.update_bar(make_bar(close=10))

    snapshot = collector.build_snapshot("600519.SSE")

    assert storage.saved == [snapshot]


def test_postgres_intraday_snapshot_storage_saves_snapshot():
    """PostgreSQL storage should persist IntradaySnapshot as JSON context."""
    from vnpy_tradingagents.intraday_collector import (
        PostgresIntradaySnapshotStorage,
    )
    from vnpy_tradingagents.intraday import IntradaySnapshot

    connection = FakeConnection()
    storage = PostgresIntradaySnapshotStorage(connection)
    snapshot = IntradaySnapshot(
        vt_symbol="600519.SSE",
        generated_at=datetime(2024, 1, 3, 9, 31),
        interval="1m",
        bars=[{"close": 10}],
        indicators={"last_price": 10},
        position={"volume": 100},
        trading_rules={"discipline": "no_chase"},
        news_events=[],
    )

    storage.save_snapshot(snapshot)

    sql, params = connection.cursor_obj.executed[0]
    assert "INSERT INTO intraday_snapshot" in sql
    assert params["vt_symbol"] == "600519.SSE"
    assert '"last_price": 10' in params["context"]
    assert connection.committed


def make_bar(close: float, at: datetime | None = None) -> BarData:
    """Create minute bar fixture."""
    return BarData(
        symbol="600519",
        exchange=Exchange.SSE,
        datetime=at or datetime(2024, 1, 3, 9, 30),
        interval=Interval.MINUTE,
        open_price=close,
        high_price=close,
        low_price=close,
        close_price=close,
        volume=100,
        turnover=close * 100,
        gateway_name="sim",
    )


def make_tick(last_price: float) -> TickData:
    """Create tick fixture."""
    return TickData(
        symbol="600519",
        exchange=Exchange.SSE,
        datetime=datetime(2024, 1, 3, 9, 30),
        last_price=last_price,
        volume=100,
        turnover=last_price * 100,
        gateway_name="sim",
    )


class RecordingSnapshotStorage:
    """Storage fake."""

    def __init__(self) -> None:
        self.saved = []

    def save_snapshot(self, snapshot) -> None:
        self.saved.append(snapshot)


class FakeCursor:
    """Tiny DB-API cursor fake."""

    def __init__(self) -> None:
        self.executed = []

    def execute(self, sql, params=None) -> None:
        self.executed.append((sql, params or {}))

    def close(self) -> None:
        return


class FakeConnection:
    """Tiny DB-API connection fake."""

    def __init__(self) -> None:
        self.cursor_obj = FakeCursor()
        self.committed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self) -> None:
        self.committed = True
