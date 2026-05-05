from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .gateway_policy import GatewayAccountMode, GatewayAiPolicy, GatewayProfile
from .performance_feedback import PerformanceFeedback, TradeFeedback
from .runtime import TradingAgentsRuntimeController

BUY_ACTIONS: frozenset[str] = frozenset({"buy", "add", "increase", "open_long", "cover", "close_short"})
SELL_ACTIONS: frozenset[str] = frozenset({"sell", "reduce", "decrease", "open_short", "close_long"})


@dataclass(frozen=True)
class SimulatedTrade:
    """
    Simulated fill produced by a paper account.
    """

    source_run_id: str
    vt_symbol: str
    trade_date: str
    action: str
    volume: float
    price: float
    slippage: float
    pnl: float


@dataclass(frozen=True)
class PaperAccountSnapshot:
    """
    Paper-account equity and risk snapshot used for performance feedback.
    """

    vt_symbol: str
    as_of: datetime
    portfolio_value: float
    previous_value: float
    benchmark_return: float
    turnover_rate: float
    max_drawdown: float


class FeedbackStorage(Protocol):
    """
    Store simulated trade feedback.
    """

    def save_trade_feedback(self, feedback: TradeFeedback) -> None:
        pass

    def save_performance_feedback(self, feedback: PerformanceFeedback) -> None:
        pass


class PaperAccountBridge:
    """
    Paper-account bridge that records simulated fills and positions.
    """

    def __init__(
        self,
        runtime: TradingAgentsRuntimeController,
        gateway_policy: GatewayAiPolicy,
        feedback_storage: FeedbackStorage,
    ) -> None:
        """"""
        self.runtime: TradingAgentsRuntimeController = runtime
        self.gateway_policy: GatewayAiPolicy = gateway_policy
        self.feedback_storage: FeedbackStorage = feedback_storage
        self.profile: GatewayProfile | None = None
        self.ai_enabled: bool = False
        self.positions: dict[str, float] = {}

    def configure(self, profile: GatewayProfile, ai_enabled: bool) -> None:
        """
        Apply gateway policy; AI is eligible only for simulation accounts by default.
        """
        self.profile = profile
        self.ai_enabled = ai_enabled
        self.gateway_policy.apply(self.runtime, profile, ai_enabled)

    def record_fill(self, trade: SimulatedTrade) -> None:
        """
        Record one simulated fill into position state and feedback storage.
        """
        if self.profile is None or self.profile.account_mode != GatewayAccountMode.SIMULATION:
            raise RuntimeError("paper bridge requires a simulation gateway profile")

        signed_volume = _signed_volume(trade.action, trade.volume)
        self.positions[trade.vt_symbol] = self.positions.get(trade.vt_symbol, 0) + signed_volume
        self.feedback_storage.save_trade_feedback(
            TradeFeedback(
                run_id=trade.source_run_id,
                vt_symbol=trade.vt_symbol,
                trade_date=trade.trade_date,
                action=trade.action,
                filled_volume=trade.volume,
                avg_price=trade.price,
                slippage=trade.slippage,
                pnl=trade.pnl,
                payload={
                    "account_mode": self.profile.account_mode.value,
                    "gateway_name": self.profile.gateway_name,
                    "ai_enabled": self.ai_enabled,
                },
            )
        )

    def record_account_snapshot(self, snapshot: PaperAccountSnapshot) -> None:
        """
        Record paper account performance feedback for later TradingAgents reflection.
        """
        if self.profile is None or self.profile.account_mode != GatewayAccountMode.SIMULATION:
            raise RuntimeError("paper bridge requires a simulation gateway profile")

        portfolio_return: float = _portfolio_return(
            snapshot.portfolio_value,
            snapshot.previous_value,
        )
        self.feedback_storage.save_performance_feedback(
            PerformanceFeedback(
                vt_symbol=snapshot.vt_symbol,
                as_of=snapshot.as_of,
                portfolio_return=portfolio_return,
                benchmark_return=snapshot.benchmark_return,
                alpha=portfolio_return - snapshot.benchmark_return,
                turnover_rate=snapshot.turnover_rate,
                max_drawdown=snapshot.max_drawdown,
                payload={
                    "account_mode": self.profile.account_mode.value,
                    "gateway_name": self.profile.gateway_name,
                    "ai_enabled": self.ai_enabled,
                    "portfolio_value": snapshot.portfolio_value,
                    "previous_value": snapshot.previous_value,
                },
            )
        )


def is_executable_trade_action(action: str) -> bool:
    """"""
    normalized = _normalize_action(action)
    return normalized in BUY_ACTIONS or normalized in SELL_ACTIONS


def _is_buy_action(action: str) -> bool:
    """"""
    return _normalize_action(action) in BUY_ACTIONS


def _signed_volume(action: str, volume: float) -> float:
    """"""
    normalized = _normalize_action(action)
    if normalized in BUY_ACTIONS:
        return volume
    if normalized in SELL_ACTIONS:
        return -volume
    raise ValueError(f"non-executable paper trade action: {action}")


def _normalize_action(action: str) -> str:
    """"""
    return action.strip().lower()


def _portfolio_return(portfolio_value: float, previous_value: float) -> float:
    """"""
    if previous_value == 0:
        return 0
    return (portfolio_value - previous_value) / previous_value
