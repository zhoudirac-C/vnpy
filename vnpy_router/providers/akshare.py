from collections.abc import Callable
from datetime import datetime
from importlib import import_module
from types import ModuleType

import pandas as pd

from vnpy.trader.constant import Interval
from vnpy.trader.object import BarData, HistoryRequest

from .base import BaseProvider


class AkshareProvider(BaseProvider):
    """
    AKShare provider with lazy dependency loading.
    """

    name: str = "akshare"

    def __init__(self) -> None:
        """"""
        self.akshare: ModuleType | None = None

    def init(self, output: Callable = print) -> bool:
        """
        Import AKShare lazily so the router can work without it installed.
        """
        if self.akshare:
            return True

        try:
            self.akshare = import_module("akshare")
            return True
        except ModuleNotFoundError:
            output("akshare is not installed; AkshareProvider is disabled")
            return False

    def query_bar_history(
        self,
        req: HistoryRequest,
        output: Callable = print,
    ) -> list[BarData]:
        """
        Query A-share bar history from AKShare.
        """
        if not self.init(output):
            return []

        if req.interval not in {Interval.DAILY, Interval.WEEKLY}:
            output(f"AkshareProvider does not support interval: {req.interval}")
            return []

        if not self.akshare:
            return []

        period: str = "weekly" if req.interval == Interval.WEEKLY else "daily"
        start: str = req.start.strftime("%Y%m%d")
        end_dt: datetime = req.end or datetime.now()
        end: str = end_dt.strftime("%Y%m%d")

        try:
            df = self.akshare.stock_zh_a_hist(
                symbol=req.symbol,
                period=period,
                start_date=start,
                end_date=end,
                adjust="",
            )
        except Exception as exc:
            output(f"AkshareProvider query failed: {exc}")
            return []

        return self._to_bars(req, df)

    def _to_bars(self, req: HistoryRequest, df: pd.DataFrame) -> list[BarData]:
        """"""
        if df.empty:
            return []

        rename_map: dict[str, str] = {
            "日期": "datetime",
            "开盘": "open",
            "最高": "high",
            "最低": "low",
            "收盘": "close",
            "成交量": "volume",
            "成交额": "turnover",
        }
        df = df.rename(columns=rename_map)
        df["datetime"] = pd.to_datetime(df["datetime"])

        bars: list[BarData] = []
        for row in df.itertuples(index=False):
            bar = BarData(
                symbol=req.symbol,
                exchange=req.exchange,
                datetime=row.datetime.to_pydatetime(),
                interval=req.interval,
                volume=float(getattr(row, "volume", 0) or 0),
                turnover=float(getattr(row, "turnover", 0) or 0),
                open_interest=0,
                open_price=float(row.open),
                high_price=float(row.high),
                low_price=float(row.low),
                close_price=float(row.close),
                gateway_name=self.name,
            )
            bar.extra = {
                "provider_name": self.name,
                "provider_endpoint": "stock_zh_a_hist",
            }
            bars.append(bar)

        return bars
