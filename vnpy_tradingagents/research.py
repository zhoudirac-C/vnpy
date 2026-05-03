from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4

from vnpy.trader.object import BarData

from .runtime import TradingAgentsRuntimeController
from .worker import TradingAgentsWorkerRequest, TradingAgentsWorkerResponse


@dataclass(frozen=True)
class ResearchSnapshot:
    """
    Long-horizon research context sent to TradingAgents.
    """

    vt_symbol: str
    trade_date: str
    market: dict[str, Any]
    fundamentals: dict[str, Any]
    valuation: dict[str, Any]
    industry: dict[str, Any]
    benchmark: dict[str, Any]
    news_events: list[dict[str, Any]]
    portfolio_state: dict[str, Any]

    def to_context(self) -> dict[str, Any]:
        """
        Convert snapshot into a provider-independent worker context.
        """
        return {
            "research": {
                "vt_symbol": self.vt_symbol,
                "trade_date": self.trade_date,
            },
            "market": self.market,
            "fundamentals": self.fundamentals,
            "valuation": self.valuation,
            "industry": self.industry,
            "benchmark": self.benchmark,
            "news_events": self.news_events,
            "portfolio_state": self.portfolio_state,
        }


class ResearchSnapshotBuilder:
    """
    Build compact long-horizon research snapshots from market and research inputs.
    """

    def __init__(self, window_size: int = 60) -> None:
        """"""
        self.window_size: int = window_size

    def build(
        self,
        vt_symbol: str,
        trade_date: str,
        bar_groups: Mapping[str, Sequence[BarData]],
        fundamentals: dict[str, Any] | None = None,
        valuation: dict[str, Any] | None = None,
        industry: dict[str, Any] | None = None,
        benchmark: dict[str, Any] | None = None,
        news_events: list[dict[str, Any]] | None = None,
        portfolio_state: dict[str, Any] | None = None,
    ) -> ResearchSnapshot:
        """
        Compress multi-period market data and attach research snapshots.
        """
        if not bar_groups or not any(bar_groups.values()):
            raise ValueError("bar_groups must contain at least one bar")

        return ResearchSnapshot(
            vt_symbol=vt_symbol,
            trade_date=trade_date,
            market={
                name: _market_window_to_context(bars[-self.window_size :])
                for name, bars in bar_groups.items()
                if bars
            },
            fundamentals=fundamentals or {},
            valuation=valuation or {},
            industry=industry or {},
            benchmark=benchmark or {},
            news_events=news_events or [],
            portfolio_state=portfolio_state or {},
        )


class Worker(Protocol):
    """
    Worker client protocol.
    """

    def run(self, request: TradingAgentsWorkerRequest) -> TradingAgentsWorkerResponse:
        pass


class AgentStorage(Protocol):
    """
    Storage protocol for long-horizon worker output.
    """

    def save_worker_result(
        self,
        request: TradingAgentsWorkerRequest,
        response: TradingAgentsWorkerResponse,
    ) -> None:
        pass


class LongHorizonAgentJob:
    """
    Runtime-guarded job that turns research snapshots into long-horizon signals.
    """

    def __init__(
        self,
        runtime: TradingAgentsRuntimeController,
        worker: Worker,
        storage: AgentStorage,
    ) -> None:
        """"""
        self.runtime: TradingAgentsRuntimeController = runtime
        self.worker: Worker = worker
        self.storage: AgentStorage = storage

    def run(self, snapshot: ResearchSnapshot) -> TradingAgentsWorkerResponse | None:
        """
        Invoke TradingAgents and persist report, rating and portfolio intent.
        """
        if not self.runtime.can_generate_report():
            return None

        request: TradingAgentsWorkerRequest = TradingAgentsWorkerRequest(
            run_id=f"long-{uuid4().hex}",
            vt_symbol=snapshot.vt_symbol,
            trade_date=snapshot.trade_date,
            mode="long_horizon",
            context=snapshot.to_context(),
        )
        response: TradingAgentsWorkerResponse = self.worker.run(request)

        self.storage.save_worker_result(request, response)
        self.runtime.mark_success(response.run_id)
        return response


def _market_window_to_context(bars: Sequence[BarData]) -> dict[str, Any]:
    """"""
    closes: list[float] = [bar.close_price for bar in bars]
    volume: float = sum(bar.volume for bar in bars)

    return {
        "interval": _bar_interval(bars[-1]),
        "latest_close": bars[-1].close_price,
        "ma_close": sum(closes) / len(closes),
        "window_volume": volume,
        "window_high": max(bar.high_price for bar in bars),
        "window_low": min(bar.low_price for bar in bars),
        "bars": [_bar_to_dict(bar) for bar in bars],
    }


def _bar_interval(bar: BarData) -> str:
    """"""
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
