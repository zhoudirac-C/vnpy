from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
import json
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

CREATE TABLE IF NOT EXISTS alpha_factor_snapshot (
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


PAYLOAD_SNAPSHOT_TABLES: dict[str, str] = {
    "fundamentals": "fundamental_snapshot",
    "valuation": "valuation_snapshot",
    "industry": "industry_snapshot",
    "benchmark": "benchmark_snapshot",
    "portfolio": "portfolio_snapshot",
    "alpha_factor": "alpha_factor_snapshot",
}

DEFERRED_SNAPSHOT_TYPES: frozenset[str] = frozenset({"news", "sentiment"})


SELECT_LATEST_PAYLOAD_SNAPSHOT_SQL: str = """
SELECT
    as_of,
    provider_name,
    provider_version,
    quality_status,
    payload
FROM {table_name}
WHERE vt_symbol = %(vt_symbol)s
  AND as_of <= %(as_of)s
ORDER BY as_of DESC, pulled_at DESC
LIMIT 1;
"""


UPSERT_PAYLOAD_SNAPSHOT_SQL: str = """
INSERT INTO {table_name} (
    vt_symbol,
    as_of,
    provider_name,
    provider_version,
    quality_status,
    payload
) VALUES (
    %(vt_symbol)s,
    %(as_of)s,
    %(provider_name)s,
    %(provider_version)s,
    %(quality_status)s,
    %(payload)s
)
ON CONFLICT (vt_symbol, as_of, provider_name)
DO UPDATE SET
    provider_version = EXCLUDED.provider_version,
    pulled_at = now(),
    quality_status = EXCLUDED.quality_status,
    payload = EXCLUDED.payload;
"""


class Cursor(Protocol):
    """
    Minimal DB-API cursor protocol used by storage.
    """

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> None:
        pass

    def fetchall(self) -> list[Mapping[str, Any]]:
        pass

    def fetchone(self) -> Mapping[str, Any] | None:
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


@dataclass(frozen=True)
class PayloadSnapshot:
    """
    Provider-traced research snapshot persisted as JSON payload.
    """

    snapshot_type: str
    vt_symbol: str
    as_of: datetime
    provider_name: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    provider_version: str = ""
    quality_status: str = ""


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

    def save_payload_snapshot(self, snapshot: PayloadSnapshot) -> None:
        """
        Save a provider-traced research payload snapshot.
        """
        table_name: str | None = PAYLOAD_SNAPSHOT_TABLES.get(snapshot.snapshot_type)
        if table_name is None:
            raise ValueError(f"Unsupported payload snapshot type: {snapshot.snapshot_type}")

        cursor: Cursor = self.connection.cursor()
        try:
            cursor.execute(
                UPSERT_PAYLOAD_SNAPSHOT_SQL.format(table_name=table_name),
                _payload_snapshot_params(snapshot),
            )
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

    def load_latest_snapshot(
        self,
        snapshot_type: str,
        vt_symbol: str,
        as_of: datetime,
    ) -> dict[str, Any] | None:
        """
        Load the latest research snapshot payload at or before as_of.
        """
        if snapshot_type in DEFERRED_SNAPSHOT_TYPES:
            return None

        table_name: str | None = PAYLOAD_SNAPSHOT_TABLES.get(snapshot_type)
        if table_name is None:
            return None

        sql: str = SELECT_LATEST_PAYLOAD_SNAPSHOT_SQL.format(table_name=table_name)
        cursor: Cursor = self.connection.cursor()
        try:
            cursor.execute(sql, {"vt_symbol": vt_symbol, "as_of": as_of})
            row: Mapping[str, Any] | None = cursor.fetchone()
            if row is None:
                return None
            return _payload_row_to_dict(snapshot_type, row)
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


def _payload_row_to_dict(snapshot_type: str, row: Mapping[str, Any]) -> dict[str, Any]:
    """
    Convert a JSONB payload snapshot row into toolkit context.
    """
    payload: Any = row.get("payload")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            pass

    if isinstance(payload, Mapping):
        data: dict[str, Any] = dict(payload)
    else:
        data = {"payload": payload}

    as_of: Any = row.get("as_of")
    data["_snapshot_type"] = snapshot_type
    data["_as_of"] = as_of.isoformat() if isinstance(as_of, datetime) else as_of
    data["_provider_name"] = row.get("provider_name")
    data["_provider_version"] = row.get("provider_version")
    data["_quality_status"] = row.get("quality_status")
    return data


def _payload_snapshot_params(snapshot: PayloadSnapshot) -> dict[str, Any]:
    """
    Convert payload snapshots into SQL params.
    """
    return {
        "snapshot_type": snapshot.snapshot_type,
        "vt_symbol": snapshot.vt_symbol,
        "as_of": snapshot.as_of,
        "provider_name": snapshot.provider_name,
        "provider_version": snapshot.provider_version,
        "quality_status": snapshot.quality_status,
        "payload": json.dumps(snapshot.payload, ensure_ascii=False, sort_keys=True),
    }
