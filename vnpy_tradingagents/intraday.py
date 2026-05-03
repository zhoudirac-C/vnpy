from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol
from uuid import uuid4

from vnpy.trader.object import BarData

from .runtime import TradingAgentsRuntimeController
from .signals import IntradayAdvice
from .worker import TradingAgentsWorkerRequest, TradingAgentsWorkerResponse


@dataclass(frozen=True)
class IntradaySnapshot:
    """
    Compressed intraday context sent to TradingAgents.
    """

    vt_symbol: str
    generated_at: datetime
    interval: str
    bars: list[dict[str, Any]]
    indicators: dict[str, float]
    position: dict[str, Any]
    trading_rules: dict[str, Any]
    news_events: list[dict[str, Any]]

    def to_context(self) -> dict[str, Any]:
        """
        Convert snapshot into a provider-independent worker context.
        """
        return {
            "intraday": {
                "vt_symbol": self.vt_symbol,
                "generated_at": self.generated_at.isoformat(),
                "interval": self.interval,
                "bars": self.bars,
                **self.indicators,
            },
            "position": self.position,
            "trading_rules": self.trading_rules,
            "news_events": self.news_events,
        }


class IntradaySnapshotBuilder:
    """
    Build compact intraday snapshots from vn.py minute bars.
    """

    def __init__(self, window_size: int = 20) -> None:
        """"""
        self.window_size: int = window_size

    def build(
        self,
        vt_symbol: str,
        bars: Sequence[BarData],
        generated_at: datetime | None = None,
        position: dict[str, Any] | None = None,
        trading_rules: dict[str, Any] | None = None,
        news_events: list[dict[str, Any]] | None = None,
    ) -> IntradaySnapshot:
        """
        Compress recent bars into a bounded snapshot.
        """
        if not bars:
            raise ValueError("bars must not be empty")

        window: list[BarData] = list(bars[-self.window_size :])
        last_bar: BarData = window[-1]
        snapshot_at: datetime = generated_at or last_bar.datetime

        return IntradaySnapshot(
            vt_symbol=vt_symbol,
            generated_at=snapshot_at,
            interval=_bar_interval(last_bar),
            bars=[_bar_to_dict(bar) for bar in window],
            indicators=_build_indicators(window),
            position=position or {},
            trading_rules=trading_rules or {},
            news_events=news_events or [],
        )


class Worker(Protocol):
    """
    Worker client protocol.
    """

    def run(self, request: TradingAgentsWorkerRequest) -> TradingAgentsWorkerResponse:
        pass


class IntradayAdviceStorage(Protocol):
    """
    Storage protocol for intraday advice output.
    """

    def save_intraday_advice(self, advice: IntradayAdvice) -> None:
        pass


class IntradayAgentJob:
    """
    Runtime-guarded job that turns snapshots into intraday advice.
    """

    def __init__(
        self,
        runtime: TradingAgentsRuntimeController,
        worker: Worker,
        storage: IntradayAdviceStorage,
        valid_for: timedelta = timedelta(minutes=15),
    ) -> None:
        """"""
        self.runtime: TradingAgentsRuntimeController = runtime
        self.worker: Worker = worker
        self.storage: IntradayAdviceStorage = storage
        self.valid_for: timedelta = valid_for

    def run(self, snapshot: IntradaySnapshot) -> IntradayAdvice | None:
        """
        Invoke TradingAgents and persist advice when the global switch allows it.
        """
        if not self.runtime.can_generate_report():
            return None

        request: TradingAgentsWorkerRequest = TradingAgentsWorkerRequest(
            run_id=f"intraday-{uuid4().hex}",
            vt_symbol=snapshot.vt_symbol,
            trade_date=snapshot.generated_at.date().isoformat(),
            mode="intraday_advice",
            context=snapshot.to_context(),
        )
        response: TradingAgentsWorkerResponse = self.worker.run(request)
        advice: IntradayAdvice = IntradayAdvice(
            vt_symbol=response.vt_symbol,
            action=response.action,
            confidence=response.confidence,
            valid_until=snapshot.generated_at + self.valid_for,
            source_run_id=response.run_id,
        )

        self.storage.save_intraday_advice(advice)
        self.runtime.mark_success(response.run_id)
        return advice


def _bar_interval(bar: BarData) -> str:
    """"""
    if bar.extra and bar.extra.get("snapshot_interval"):
        return str(bar.extra["snapshot_interval"])
    return bar.interval.value if bar.interval else ""


def _bar_to_dict(bar: BarData) -> dict[str, Any]:
    """"""
    return {
        "datetime": bar.datetime.isoformat(),
        "open": bar.open_price,
        "high": bar.high_price,
        "low": bar.low_price,
        "close": bar.close_price,
        "volume": bar.volume,
        "turnover": bar.turnover,
    }


def _build_indicators(bars: Sequence[BarData]) -> dict[str, float]:
    """"""
    closes: list[float] = [bar.close_price for bar in bars]
    volume: float = sum(bar.volume for bar in bars)
    turnover: float = sum(bar.turnover for bar in bars)

    return {
        "last_price": bars[-1].close_price,
        "ma_close": sum(closes) / len(closes),
        "vwap": turnover / volume if volume else 0,
        "window_volume": volume,
        "window_high": max(bar.high_price for bar in bars),
        "window_low": min(bar.low_price for bar in bars),
    }
