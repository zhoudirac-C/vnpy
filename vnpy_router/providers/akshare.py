from collections.abc import Callable, Iterator, Sequence
from datetime import datetime
from importlib import import_module
from types import ModuleType
from typing import Any

import pandas as pd

from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import BarData, HistoryRequest

from .base import BaseProvider
from .capability import ProviderCapability, ProviderCostLevel


DEFAULT_ENDPOINTS: tuple[str, ...] = (
    "stock_zh_a_hist",
    "stock_zh_a_hist_tx",
    "stock_zh_a_daily",
)

ENDPOINT_INTERVALS: dict[str, frozenset[Interval]] = {
    "stock_zh_a_hist": frozenset({Interval.DAILY, Interval.WEEKLY}),
    "stock_zh_a_hist_tx": frozenset({Interval.DAILY}),
    "stock_zh_a_daily": frozenset({Interval.DAILY}),
}


class AkshareProvider(BaseProvider):
    """
    AKShare provider with lazy dependency loading.
    """

    name: str = "akshare"
    capability: ProviderCapability = ProviderCapability(
        name=name,
        intervals=frozenset({Interval.DAILY, Interval.WEEKLY}),
        fields=frozenset({"open", "high", "low", "close", "volume", "turnover"}),
        adjustments=frozenset({"none", "qfq", "hfq"}),
        supports_tick=False,
        realtime=False,
        history=True,
        cost_level=ProviderCostLevel.FREE,
        realtime_notes="AKShare is a research/history provider here; realtime quotes and trading should use a vn.py Gateway.",
        metadata={
            "production_scope": "research_history",
            "supported_market": "A-share",
            "supported_intervals": ["daily", "weekly"],
            "endpoints": list(DEFAULT_ENDPOINTS),
            "unsupported_intervals": ["minute", "hour", "tick"],
            "unsupported_realtime": ["tick", "orderbook", "broker_position", "trading"],
        },
    )

    def __init__(
        self,
        endpoints: Sequence[str] | None = None,
        adjustment: str = "",
        provider_version: str = "",
    ) -> None:
        """"""
        configured_endpoints: tuple[str, ...] = tuple(
            endpoint.strip() for endpoint in (endpoints or DEFAULT_ENDPOINTS) if endpoint.strip()
        )
        self.endpoints: tuple[str, ...] = configured_endpoints or DEFAULT_ENDPOINTS
        self.adjustment: str = _to_akshare_adjustment(adjustment)
        self.provider_version: str = provider_version or "akshare:multi_endpoint"
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
        if req.interval not in {Interval.DAILY, Interval.WEEKLY}:
            output(f"AkshareProvider does not support interval: {req.interval}")
            return []

        if not self.init(output):
            return []

        if not self.akshare:
            return []

        period: str = "weekly" if req.interval == Interval.WEEKLY else "daily"
        start: str = req.start.strftime("%Y%m%d")
        end_dt: datetime = req.end or datetime.now()
        end: str = end_dt.strftime("%Y%m%d")

        for endpoint in self._iter_supported_endpoints(req.interval, output):
            try:
                df = self._query_endpoint(endpoint, req, period, start, end)
            except Exception as exc:
                output(f"AkshareProvider {endpoint} query failed: {exc}")
                continue

            bars: list[BarData] = self._to_bars(req, df, endpoint, output)
            if bars:
                return bars

            output(f"AkshareProvider {endpoint} returned no usable bars")

        return []

    def _iter_supported_endpoints(
        self,
        interval: Interval,
        output: Callable,
    ) -> Iterator[str]:
        """
        Yield configured AKShare endpoints that can serve the requested interval.
        """
        seen: set[str] = set()
        for endpoint in self.endpoints:
            if endpoint in seen:
                continue
            seen.add(endpoint)

            intervals: frozenset[Interval] | None = ENDPOINT_INTERVALS.get(endpoint)
            if intervals is None:
                output(f"AkshareProvider unknown endpoint skipped: {endpoint}")
                continue
            if interval not in intervals:
                output(f"AkshareProvider {endpoint} does not support interval: {interval}")
                continue
            yield endpoint

    def _query_endpoint(
        self,
        endpoint: str,
        req: HistoryRequest,
        period: str,
        start: str,
        end: str,
    ) -> pd.DataFrame:
        """
        Query one AKShare endpoint using the symbol format it expects.
        """
        if not self.akshare:
            return pd.DataFrame()

        if endpoint == "stock_zh_a_hist":
            return self.akshare.stock_zh_a_hist(
                symbol=req.symbol,
                period=period,
                start_date=start,
                end_date=end,
                adjust=self.adjustment,
            )

        market_symbol: str = _to_market_symbol(req.symbol, req.exchange)
        if endpoint == "stock_zh_a_hist_tx":
            return self.akshare.stock_zh_a_hist_tx(
                symbol=market_symbol,
                start_date=start,
                end_date=end,
                adjust=self.adjustment,
            )
        if endpoint == "stock_zh_a_daily":
            return self.akshare.stock_zh_a_daily(
                symbol=market_symbol,
                start_date=start,
                end_date=end,
                adjust=self.adjustment,
            )

        raise ValueError(f"unsupported AKShare endpoint: {endpoint}")

    def _to_bars(
        self,
        req: HistoryRequest,
        df: pd.DataFrame,
        endpoint: str,
        output: Callable,
    ) -> list[BarData]:
        """"""
        if df.empty:
            return []

        df = df.copy()
        if _datetime_column_missing(df):
            df = df.reset_index()
        rename_map: dict[str, str] = {
            "日期": "datetime",
            "date": "datetime",
            "index": "datetime",
            "datetime": "datetime",
            "开盘": "open",
            "open": "open",
            "最高": "high",
            "high": "high",
            "最低": "low",
            "low": "low",
            "收盘": "close",
            "close": "close",
            "成交量": "volume",
            "volume": "volume",
            "成交额": "turnover",
            "turnover": "turnover",
        }
        df = df.rename(columns=rename_map)
        if "volume" not in df.columns and "amount" in df.columns:
            df["volume"] = df["amount"]
        if "turnover" not in df.columns:
            df["turnover"] = 0

        required_columns: tuple[str, ...] = ("datetime", "open", "high", "low", "close")
        missing_columns: list[str] = [
            column for column in required_columns if column not in df.columns
        ]
        if missing_columns:
            output(
                f"AkshareProvider {endpoint} missing columns: {','.join(missing_columns)}"
            )
            return []

        df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
        for column in ("open", "high", "low", "close", "volume", "turnover"):
            df[column] = pd.to_numeric(df[column], errors="coerce")

        df = df.dropna(subset=required_columns)
        if df.empty:
            return []

        end_dt: datetime = req.end or datetime.now()
        df = df[
            (df["datetime"] >= pd.Timestamp(req.start))
            & (df["datetime"] <= pd.Timestamp(end_dt))
        ]
        if df.empty:
            return []

        valid_mask = (
            (df["high"] >= df["low"])
            & (df["high"] >= df["open"])
            & (df["high"] >= df["close"])
            & (df["low"] <= df["open"])
            & (df["low"] <= df["close"])
        )
        df = df[valid_mask]
        if df.empty:
            output(f"AkshareProvider {endpoint} returned invalid OHLC rows")
            return []

        df = df.sort_values("datetime").drop_duplicates(subset=["datetime"], keep="last")

        bars: list[BarData] = []
        for _, row in df.iterrows():
            bar = BarData(
                symbol=req.symbol,
                exchange=req.exchange,
                datetime=row["datetime"].to_pydatetime(),
                interval=req.interval,
                volume=_optional_float(row.get("volume")),
                turnover=_optional_float(row.get("turnover")),
                open_interest=0,
                open_price=float(row["open"]),
                high_price=float(row["high"]),
                low_price=float(row["low"]),
                close_price=float(row["close"]),
                gateway_name=self.name,
            )
            bar.extra = {
                "provider_name": self.name,
                "provider_endpoint": endpoint,
                "provider_version": self.provider_version,
                "adjustment": self.adjustment or "none",
            }
            bars.append(bar)

        return bars


def _to_akshare_adjustment(adjustment: str) -> str:
    """
    Convert user-facing adjustment text into AKShare's argument value.
    """
    normalized: str = adjustment.strip().lower()
    if normalized in {"", "none"}:
        return ""
    if normalized in {"qfq", "hfq"}:
        return normalized
    return ""


def _to_market_symbol(symbol: str, exchange: Exchange) -> str:
    """
    Convert vn.py symbol/exchange to endpoints that expect sh/sz/bj prefixes.
    """
    prefix: str = {
        Exchange.SSE: "sh",
        Exchange.SZSE: "sz",
        Exchange.BSE: "bj",
    }.get(exchange, "")
    if not prefix:
        raise ValueError(f"unsupported AKShare market-prefix exchange: {exchange}")
    return f"{prefix}{symbol}"


def _datetime_column_missing(df: pd.DataFrame) -> bool:
    """
    Return whether AKShare returned dates in the dataframe index instead of a column.
    """
    if {"datetime", "日期", "date"} & set(df.columns):
        return False
    index_name = str(df.index.name or "").lower()
    return index_name in {"datetime", "date", "日期"} or isinstance(
        df.index,
        pd.DatetimeIndex,
    )


def _optional_float(value: Any) -> float:
    """
    Convert optional numeric dataframe values into a finite float fallback.
    """
    if value is None or pd.isna(value):
        return 0
    return float(value)
