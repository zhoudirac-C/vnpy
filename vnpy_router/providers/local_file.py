from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import pandas as pd

from vnpy.trader.constant import Interval
from vnpy.trader.object import BarData, HistoryRequest

from .base import BaseProvider
from .capability import ProviderCapability, ProviderCostLevel


class LocalFileProvider(BaseProvider):
    """
    Local CSV provider for offline tests and manually supplied data.

    Expected filename: {vt_symbol}_{interval}.csv, for example 600519.SSE_d.csv.
    """

    name: str = "local_file"
    capability: ProviderCapability = ProviderCapability(
        name=name,
        intervals=frozenset(
            {
                Interval.MINUTE,
                Interval.HOUR,
                Interval.DAILY,
                Interval.WEEKLY,
            }
        ),
        fields=frozenset(
            {
                "open",
                "high",
                "low",
                "close",
                "volume",
                "turnover",
                "open_interest",
            }
        ),
        adjustments=frozenset({"none", "qfq", "hfq"}),
        supports_tick=False,
        realtime=False,
        cost_level=ProviderCostLevel.MANUAL,
    )

    def __init__(self, base_path: str | Path) -> None:
        """"""
        self.base_path: Path = Path(base_path)

    def query_bar_history(
        self,
        req: HistoryRequest,
        output: Callable = print,
    ) -> list[BarData]:
        """
        Query historical bar data from a local CSV file.
        """
        if not req.interval:
            output("LocalFileProvider requires HistoryRequest.interval")
            return []

        file_path: Path = self._get_file_path(req)
        if not file_path.exists():
            output(f"LocalFileProvider file not found: {file_path}")
            return []

        df = pd.read_csv(file_path)
        if df.empty:
            return []

        df["datetime"] = pd.to_datetime(df["datetime"])
        start: datetime = req.start.replace(tzinfo=None)
        end: datetime = (req.end or datetime.max).replace(tzinfo=None)
        df = df[(df["datetime"] >= start) & (df["datetime"] <= end)]
        df = df.sort_values("datetime")

        bars: list[BarData] = []
        for row in df.itertuples(index=False):
            bar = BarData(
                symbol=req.symbol,
                exchange=req.exchange,
                datetime=row.datetime.to_pydatetime(),
                interval=req.interval,
                volume=float(getattr(row, "volume", 0) or 0),
                turnover=float(getattr(row, "turnover", 0) or 0),
                open_interest=float(getattr(row, "open_interest", 0) or 0),
                open_price=float(row.open),
                high_price=float(row.high),
                low_price=float(row.low),
                close_price=float(row.close),
                gateway_name=self.name,
            )
            bar.extra = {
                "provider_name": self.name,
                "provider_endpoint": str(file_path),
            }
            bars.append(bar)

        return bars

    def _get_file_path(self, req: HistoryRequest) -> Path:
        """"""
        interval: Interval = req.interval or Interval.DAILY
        return self.base_path.joinpath(f"{req.vt_symbol}_{interval.value}.csv")
