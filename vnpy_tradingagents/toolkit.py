from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, Any


@dataclass(frozen=True)
class SnapshotQuery:
    """
    Query window for building TradingAgents context.
    """

    vt_symbol: str
    start: datetime
    end: datetime


class SnapshotReader(Protocol):
    """
    Read-only snapshot source for MarketDataToolkit.
    """

    def load_bar_snapshots(
        self,
        vt_symbol: str,
        start: datetime,
        end: datetime,
    ) -> Sequence[dict[str, Any]]:
        pass

    def load_latest_snapshot(
        self,
        snapshot_type: str,
        vt_symbol: str,
        as_of: datetime,
    ) -> dict[str, Any] | None:
        pass


class MarketDataToolkit:
    """
    Read PostgreSQL snapshots and build TradingAgents input context.
    """

    snapshot_types: tuple[str, ...] = (
        "fundamentals",
        "news",
        "sentiment",
        "benchmark",
        "portfolio",
    )

    def __init__(self, reader: SnapshotReader) -> None:
        """"""
        self.reader: SnapshotReader = reader

    def build_context(self, query: SnapshotQuery) -> dict[str, Any]:
        """
        Build a provider-independent context dictionary.
        """
        degraded_sources: list[str] = []
        bars: Sequence[dict[str, Any]] = self.reader.load_bar_snapshots(
            query.vt_symbol,
            query.start,
            query.end,
        )
        context: dict[str, Any] = {
            "vt_symbol": query.vt_symbol,
            "window": {
                "start": query.start.isoformat(),
                "end": query.end.isoformat(),
            },
            "market": {
                "bars": list(bars),
            },
        }

        if not bars:
            degraded_sources.append("market")

        for snapshot_type in self.snapshot_types:
            snapshot: dict[str, Any] | None = self.reader.load_latest_snapshot(
                snapshot_type,
                query.vt_symbol,
                query.end,
            )
            context[snapshot_type] = snapshot or {}
            if snapshot is None:
                degraded_sources.append(snapshot_type)

        context["degraded_sources"] = degraded_sources
        return context
