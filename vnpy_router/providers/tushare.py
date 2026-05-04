import importlib
import os
from collections.abc import Callable
from datetime import datetime
from types import ModuleType

import pandas as pd

from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import BarData, HistoryRequest
from vnpy.trader.setting import SETTINGS

from .base import BaseProvider
from .capability import ProviderCapability, ProviderCostLevel


class TuShareProvider(BaseProvider):
    """
    TuShare provider for production-grade daily/index/fundamental snapshots.
    """

    name: str = "tushare"
    capability: ProviderCapability = ProviderCapability(
        name=name,
        intervals=frozenset({Interval.DAILY, Interval.WEEKLY}),
        fields=frozenset({"open", "high", "low", "close", "volume", "turnover"}),
        adjustments=frozenset({"none", "qfq", "hfq"}),
        supports_tick=False,
        realtime=False,
        history=True,
        cost_level=ProviderCostLevel.LOW,
        metadata={
            "endpoints": ["pro_bar", "daily_basic", "income", "balancesheet"],
            "requires_token": True,
        },
    )

    def __init__(
        self,
        token: str | None = None,
        adjustment: str = "",
        provider_version: str = "",
    ) -> None:
        """"""
        self.token: str = _resolve_token(token)
        self.adjustment: str = adjustment
        self.provider_version: str = provider_version or "tushare:pro_bar"
        self.tushare: ModuleType | None = None

    def init(self, output: Callable = print) -> bool:
        """
        Initialize TuShare lazily and keep token out of metadata/logs.
        """
        if not self.token:
            output("TuShareProvider token is not configured; provider is degraded")
            return False

        if self.tushare:
            return True

        try:
            self.tushare = importlib.import_module("tushare")
        except ModuleNotFoundError:
            output("tushare is not installed; TuShareProvider is disabled")
            return False

        set_token = getattr(self.tushare, "set_token", None)
        if callable(set_token):
            set_token(self.token)
        return True

    def query_bar_history(
        self,
        req: HistoryRequest,
        output: Callable = print,
    ) -> list[BarData]:
        """
        Query historical bar data from TuShare pro_bar.
        """
        if not self.init(output):
            return []

        if req.interval not in {Interval.DAILY, Interval.WEEKLY}:
            output(f"TuShareProvider does not support interval: {req.interval}")
            return []

        if not self.tushare:
            return []

        try:
            df = self.tushare.pro_bar(
                ts_code=_to_ts_code(req.symbol, req.exchange),
                adj=self.adjustment,
                start_date=req.start.strftime("%Y%m%d"),
                end_date=(req.end or datetime.now()).strftime("%Y%m%d"),
                freq=_to_freq(req.interval),
            )
        except Exception as exc:
            output(f"TuShareProvider query failed: {exc}")
            return []

        return self._to_bars(req, df)

    def _to_bars(self, req: HistoryRequest, df: pd.DataFrame) -> list[BarData]:
        """
        Convert TuShare dataframe rows into vn.py BarData.
        """
        if df.empty:
            return []

        df = df.copy()
        df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d")
        df = df.sort_values("trade_date")

        bars: list[BarData] = []
        for row in df.itertuples(index=False):
            bar = BarData(
                symbol=req.symbol,
                exchange=req.exchange,
                datetime=row.trade_date.to_pydatetime(),
                interval=req.interval,
                volume=float(getattr(row, "vol", 0) or 0),
                turnover=float(getattr(row, "amount", 0) or 0),
                open_interest=0,
                open_price=float(row.open),
                high_price=float(row.high),
                low_price=float(row.low),
                close_price=float(row.close),
                gateway_name=self.name,
            )
            bar.extra = {
                "provider_name": self.name,
                "provider_endpoint": "pro_bar",
                "provider_version": self.provider_version,
                "adjustment": self.adjustment or "none",
            }
            bars.append(bar)

        return bars


def _resolve_token(token: str | None) -> str:
    """
    Resolve TuShare token from explicit config, vn.py settings, or environment.
    """
    if token is not None:
        return token.strip()
    return str(
        SETTINGS.get("router.tushare.token")
        or SETTINGS.get("tushare.token")
        or os.environ.get("TUSHARE_TOKEN", "")
    ).strip()


def _to_ts_code(symbol: str, exchange: Exchange) -> str:
    """
    Convert vn.py symbol/exchange into TuShare ts_code.
    """
    suffix: str = {
        Exchange.SSE: "SH",
        Exchange.SZSE: "SZ",
        Exchange.BSE: "BJ",
    }.get(exchange, exchange.value)
    return f"{symbol}.{suffix}"


def _to_freq(interval: Interval) -> str:
    """
    Convert vn.py interval into TuShare pro_bar frequency.
    """
    if interval == Interval.WEEKLY:
        return "W"
    return "D"
