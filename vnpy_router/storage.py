from collections.abc import Mapping, Sequence
from datetime import datetime
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


RESEARCH_SNAPSHOT_SCHEMA: str = """
CREATE TABLE IF NOT EXISTS fundamental_snapshot (
    vt_symbol TEXT NOT NULL,
    as_of TIMESTAMPTZ NOT NULL,
    provider_name TEXT NOT NULL,
    provider_version TEXT,
    pulled_at TIMESTAMPTZ DEFAULT now(),
    quality_status TEXT,
    payload JSONB NOT NULL,
    PRIMARY KEY (vt_symbol, as_of, provider_name)
);

CREATE TABLE IF NOT EXISTS valuation_snapshot (
    vt_symbol TEXT NOT NULL,
    as_of TIMESTAMPTZ NOT NULL,
    provider_name TEXT NOT NULL,
    provider_version TEXT,
    pulled_at TIMESTAMPTZ DEFAULT now(),
    quality_status TEXT,
    payload JSONB NOT NULL,
    PRIMARY KEY (vt_symbol, as_of, provider_name)
);

CREATE TABLE IF NOT EXISTS industry_snapshot (
    vt_symbol TEXT NOT NULL,
    as_of TIMESTAMPTZ NOT NULL,
    provider_name TEXT NOT NULL,
    provider_version TEXT,
    pulled_at TIMESTAMPTZ DEFAULT now(),
    quality_status TEXT,
    payload JSONB NOT NULL,
    PRIMARY KEY (vt_symbol, as_of, provider_name)
);

CREATE TABLE IF NOT EXISTS benchmark_snapshot (
    vt_symbol TEXT NOT NULL,
    as_of TIMESTAMPTZ NOT NULL,
    provider_name TEXT NOT NULL,
    provider_version TEXT,
    pulled_at TIMESTAMPTZ DEFAULT now(),
    quality_status TEXT,
    payload JSONB NOT NULL,
    PRIMARY KEY (vt_symbol, as_of, provider_name)
);

CREATE TABLE IF NOT EXISTS portfolio_snapshot (
    vt_symbol TEXT NOT NULL,
    as_of TIMESTAMPTZ NOT NULL,
    provider_name TEXT NOT NULL,
    provider_version TEXT,
    pulled_at TIMESTAMPTZ DEFAULT now(),
    quality_status TEXT,
    payload JSONB NOT NULL,
    PRIMARY KEY (vt_symbol, as_of, provider_name)
);
"""


SNAPSHOT_SCHEMA: str = MARKET_BAR_SNAPSHOT_SCHEMA + RESEARCH_SNAPSHOT_SCHEMA


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

    def fetchall(self) -> list[Mapping[str, Any]]:
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
            cursor.execute(SNAPSHOT_SCHEMA)
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


class PostgresSnapshotReader:
    """
    PostgreSQL snapshot reader for TradingAgents and replay contexts.
    """

    def __init__(self, connection: Connection) -> None:
        """"""
        self.connection: Connection = connection

    def load_bar_snapshots(
        self,
        vt_symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "",
        provider_name: str = "",
    ) -> list[dict[str, Any]]:
        """
        Load market bar snapshots from PostgreSQL.
        """
        where_clauses: list[str] = [
            "vt_symbol = %(vt_symbol)s",
            "datetime >= %(start)s",
            "datetime <= %(end)s",
        ]
        params: dict[str, Any] = {
            "vt_symbol": vt_symbol,
            "start": start,
            "end": end,
        }

        if interval:
            where_clauses.append("interval = %(interval)s")
            params["interval"] = interval

        if provider_name:
            where_clauses.append("provider_name = %(provider_name)s")
            params["provider_name"] = provider_name

        sql: str = SELECT_MARKET_BAR_SNAPSHOT_SQL.format(
            where_clause=" AND ".join(where_clauses)
        )
        cursor: Cursor = self.connection.cursor()
        try:
            cursor.execute(sql, params)
            return [_bar_row_to_dict(row) for row in cursor.fetchall()]
        finally:
            cursor.close()


SELECT_MARKET_BAR_SNAPSHOT_SQL: str = """
SELECT
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
FROM market_bar_snapshot
WHERE {where_clause}
ORDER BY datetime ASC;
"""


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


def _bar_row_to_dict(row: Mapping[str, Any]) -> dict[str, Any]:
    """
    Convert a SQL row into a JSON-friendly snapshot dictionary.
    """
    data: dict[str, Any] = dict(row)
    value: Any = data.get("datetime")
    if isinstance(value, datetime):
        data["datetime"] = value.isoformat()
    return data
