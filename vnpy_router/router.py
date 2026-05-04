from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Protocol, Any

from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import BarData, HistoryRequest

from .providers.base import BaseProvider
from .providers.capability import ProviderCapability, unsupported_reason


class SnapshotReader(Protocol):
    """
    Read cached market data snapshots.
    """

    def load_bar_snapshots(
        self,
        vt_symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "",
        provider_name: str = "",
    ) -> Sequence[Mapping[str, Any]]:
        pass


class SnapshotStorage(Protocol):
    """
    Persist provider market data snapshots.
    """

    def save_bar_snapshots(self, bars: Sequence[BarData]) -> None:
        pass


class DataProviderRouter:
    """
    Route historical data requests across multiple providers.
    """

    def __init__(
        self,
        providers: Sequence[BaseProvider] | None = None,
        snapshot_reader: SnapshotReader | None = None,
        snapshot_storage: SnapshotStorage | None = None,
    ) -> None:
        """"""
        self.providers: list[BaseProvider] = list(providers or [])
        self.snapshot_reader: SnapshotReader | None = snapshot_reader
        self.snapshot_storage: SnapshotStorage | None = snapshot_storage

    def init(self, output: Callable = print) -> bool:
        """
        Initialize all providers and return whether any provider is usable.
        """
        active: bool = False
        for provider in self.providers:
            active = provider.init(output) or active
        return active

    def query_bar_history(
        self,
        req: HistoryRequest,
        output: Callable = print,
    ) -> list[BarData]:
        """
        Return data from the first provider that has bars for the request.
        """
        cached_bars: list[BarData] = self._query_snapshot_cache(req, output)
        if cached_bars:
            return cached_bars

        for provider in self.providers:
            capability: ProviderCapability | None = getattr(provider, "capability", None)
            if capability and not capability.supports_history_request(req):
                output(unsupported_reason(capability, req))
                continue

            try:
                bars: list[BarData] = provider.query_bar_history(req, output)
            except Exception as exc:
                output(f"{provider.name} provider failed: {exc}")
                continue

            if bars:
                self._save_snapshot_cache(bars, output)
                return bars

        return []

    def _query_snapshot_cache(
        self,
        req: HistoryRequest,
        output: Callable,
    ) -> list[BarData]:
        """
        Query PostgreSQL snapshot cache before live providers.
        """
        if not self.snapshot_reader or not req.interval:
            return []

        try:
            rows: Sequence[Mapping[str, Any]] = self.snapshot_reader.load_bar_snapshots(
                vt_symbol=req.vt_symbol,
                start=req.start,
                end=req.end or datetime.max,
                interval=req.interval.value,
            )
            bars: list[BarData] = [_snapshot_row_to_bar(row) for row in rows]
        except Exception as exc:
            output(f"snapshot cache load failed: {exc}")
            return []

        if bars:
            output(f"snapshot cache hit: {req.vt_symbol}")
        return bars

    def _save_snapshot_cache(
        self,
        bars: Sequence[BarData],
        output: Callable,
    ) -> None:
        """
        Persist provider result into PostgreSQL snapshot cache.
        """
        if not self.snapshot_storage:
            return

        try:
            self.snapshot_storage.save_bar_snapshots(bars)
        except Exception as exc:
            output(f"snapshot cache save failed: {exc}")


def _snapshot_row_to_bar(row: Mapping[str, Any]) -> BarData:
    """
    Convert a market_bar_snapshot row back into vn.py BarData.
    """
    provider_name: str = str(row.get("provider_name") or "snapshot_cache")
    bar = BarData(
        symbol=str(row["symbol"]),
        exchange=_to_exchange(row["exchange"]),
        datetime=_to_datetime(row["datetime"]),
        interval=_to_interval(row["interval"]),
        volume=float(row.get("volume") or 0),
        turnover=float(row.get("turnover") or 0),
        open_interest=float(row.get("open_interest") or 0),
        open_price=float(row["open_price"]),
        high_price=float(row["high_price"]),
        low_price=float(row["low_price"]),
        close_price=float(row["close_price"]),
        gateway_name=provider_name,
    )
    bar.extra = {
        "provider_name": provider_name,
        "provider_endpoint": row.get("provider_endpoint"),
        "provider_version": row.get("provider_version"),
        "adjustment": row.get("adjustment"),
        "quality_status": row.get("quality_status"),
        "quality_report_id": row.get("quality_report_id"),
    }
    return bar


def _to_exchange(value: Any) -> Exchange:
    """
    Normalize exchange from SQL value.
    """
    if isinstance(value, Exchange):
        return value
    return Exchange(str(value))


def _to_interval(value: Any) -> Interval:
    """
    Normalize interval from SQL value.
    """
    if isinstance(value, Interval):
        return value
    return Interval(str(value))


def _to_datetime(value: Any) -> datetime:
    """
    Normalize datetime from SQL value.
    """
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))
