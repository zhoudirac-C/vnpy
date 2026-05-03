from collections.abc import Sequence
from typing import Protocol, Any

from vnpy.trader.object import BarData


MARKET_BAR_SNAPSHOT_SCHEMA: str = """
CREATE TABLE IF NOT EXISTS market_bar_snapshot (
    vt_symbol TEXT NOT NULL,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    interval TEXT NOT NULL,
    datetime TIMESTAMPTZ NOT NULL,
    open_price DOUBLE PRECISION NOT NULL,
    high_price DOUBLE PRECISION NOT NULL,
    low_price DOUBLE PRECISION NOT NULL,
    close_price DOUBLE PRECISION NOT NULL,
    volume DOUBLE PRECISION NOT NULL,
    turnover DOUBLE PRECISION NOT NULL,
    open_interest DOUBLE PRECISION NOT NULL,
    provider_name TEXT NOT NULL,
    provider_endpoint TEXT,
    provider_version TEXT,
    adjustment TEXT,
    pulled_at TIMESTAMPTZ DEFAULT now(),
    quality_status TEXT,
    quality_report_id TEXT,
    PRIMARY KEY (vt_symbol, interval, datetime, provider_name)
);
"""


UPSERT_MARKET_BAR_SNAPSHOT_SQL: str = """
INSERT INTO market_bar_snapshot (
    vt_symbol,
    symbol,
    exchange,
    interval,
    datetime,
    open_price,
    high_price,
    low_price,
    close_price,
    volume,
    turnover,
    open_interest,
    provider_name,
    provider_endpoint,
    provider_version,
    adjustment,
    quality_status,
    quality_report_id
) VALUES (
    %(vt_symbol)s,
    %(symbol)s,
    %(exchange)s,
    %(interval)s,
    %(datetime)s,
    %(open_price)s,
    %(high_price)s,
    %(low_price)s,
    %(close_price)s,
    %(volume)s,
    %(turnover)s,
    %(open_interest)s,
    %(provider_name)s,
    %(provider_endpoint)s,
    %(provider_version)s,
    %(adjustment)s,
    %(quality_status)s,
    %(quality_report_id)s
)
ON CONFLICT (vt_symbol, interval, datetime, provider_name)
DO UPDATE SET
    open_price = EXCLUDED.open_price,
    high_price = EXCLUDED.high_price,
    low_price = EXCLUDED.low_price,
    close_price = EXCLUDED.close_price,
    volume = EXCLUDED.volume,
    turnover = EXCLUDED.turnover,
    open_interest = EXCLUDED.open_interest,
    provider_endpoint = EXCLUDED.provider_endpoint,
    provider_version = EXCLUDED.provider_version,
    adjustment = EXCLUDED.adjustment,
    pulled_at = now(),
    quality_status = EXCLUDED.quality_status,
    quality_report_id = EXCLUDED.quality_report_id;
"""


class Cursor(Protocol):
    """
    Minimal DB-API cursor protocol used by storage.
    """

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> None:
        pass

    def close(self) -> None:
        pass


class Connection(Protocol):
    """
    Minimal DB-API connection protocol used by storage.
    """

    def cursor(self) -> Cursor:
        pass

    def commit(self) -> None:
        pass


class PostgresSnapshotStorage:
    """
    PostgreSQL snapshot storage using a DB-API compatible connection.
    """

    def __init__(self, connection: Connection) -> None:
        """"""
        self.connection: Connection = connection

    def create_schema(self) -> None:
        """
        Create required snapshot tables.
        """
        cursor: Cursor = self.connection.cursor()
        try:
            cursor.execute(MARKET_BAR_SNAPSHOT_SCHEMA)
            self.connection.commit()
        finally:
            cursor.close()

    def save_bar_snapshots(self, bars: Sequence[BarData]) -> None:
        """
        Save bar snapshots with provider metadata.
        """
        cursor: Cursor = self.connection.cursor()
        try:
            for bar in bars:
                cursor.execute(UPSERT_MARKET_BAR_SNAPSHOT_SQL, _bar_to_params(bar))
            self.connection.commit()
        finally:
            cursor.close()


def _bar_to_params(bar: BarData) -> dict[str, Any]:
    """
    Convert BarData into SQL params.
    """
    extra: dict[str, Any] = bar.extra or {}
    provider_name: str = extra.get("provider_name") or bar.gateway_name

    return {
        "vt_symbol": bar.vt_symbol,
        "symbol": bar.symbol,
        "exchange": bar.exchange.value,
        "interval": bar.interval.value if bar.interval else "",
        "datetime": bar.datetime,
        "open_price": bar.open_price,
        "high_price": bar.high_price,
        "low_price": bar.low_price,
        "close_price": bar.close_price,
        "volume": bar.volume,
        "turnover": bar.turnover,
        "open_interest": bar.open_interest,
        "provider_name": provider_name,
        "provider_endpoint": extra.get("provider_endpoint"),
        "provider_version": extra.get("provider_version"),
        "adjustment": extra.get("adjustment"),
        "quality_status": extra.get("quality_status"),
        "quality_report_id": extra.get("quality_report_id"),
    }
