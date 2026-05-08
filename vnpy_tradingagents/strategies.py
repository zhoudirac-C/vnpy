from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .fusion import FusedSignal
from .policy import SignalDecision
from .risk import (
    DecisionAuditStorage,
    OrderIntent,
    PreOrderDecisionResult,
    PreOrderDecisionService,
    RiskRuleSet,
)
from .runtime import TradingAgentsRuntimeController
from .signals import PortfolioIntent


EXECUTABLE_ACTIONS: frozenset[str] = frozenset(
    {
        "buy",
        "sell",
        "reduce",
        "cover",
        "add",
        "increase",
        "open_long",
        "exit",
        "close_long",
    }
)


class TradeIntentReader(Protocol):
    """
    Read persisted AI trade intents for independent AI strategies.
    """

    def load_latest_trade_intent(
        self,
        vt_symbol: str,
        trade_date: str,
    ) -> PortfolioIntent | None:
        pass


@dataclass(frozen=True)
class AiStrategyDecisionContext:
    """
    Runtime context needed to convert an AI intent into an audited order intent.
    """

    vt_symbol: str
    trade_time: datetime
    price: float
    volume: float
    live: bool = True
    current_position: float = 0
    daily_traded_value: float = 0
    drawdown: float = 0
    cancel_count: int = 0
    limit_up: float | None = None
    limit_down: float | None = None


@dataclass(frozen=True)
class TradingAgentsStrategyDecision:
    """
    Decision result returned by independent AI strategy evaluators.
    """

    trade_intent: PortfolioIntent | None
    order_intent: OrderIntent | None
    fused_signal: FusedSignal | None
    decision: PreOrderDecisionResult | None
    ignored_reason: str = ""


class TradingAgentsSignalStrategy:
    """
    Independent AI strategy that consumes stored TradingAgents trade intents.
    """

    def __init__(
        self,
        runtime: TradingAgentsRuntimeController,
        signal_reader: TradeIntentReader,
        rules: RiskRuleSet,
        audit_storage: DecisionAuditStorage,
        decision_id_factory: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.runtime: TradingAgentsRuntimeController = runtime
        self.signal_reader: TradeIntentReader = signal_reader
        self.decision_service: PreOrderDecisionService = PreOrderDecisionService(
            rules=rules,
            audit_storage=audit_storage,
            decision_id_factory=decision_id_factory,
            clock=clock,
        )

    def evaluate(self, context: AiStrategyDecisionContext) -> TradingAgentsStrategyDecision:
        """
        Read the latest AI intent and pass executable actions through hard risk.
        """
        if not self.runtime.can_use_signal(context.live):
            return ignored("ai_signal_disabled")

        intent = self.signal_reader.load_latest_trade_intent(
            context.vt_symbol,
            context.trade_time.date().isoformat(),
        )
        return evaluate_ai_trade_intent(
            trade_intent=intent,
            context=context,
            decision_service=self.decision_service,
        )


def evaluate_ai_trade_intent(
    trade_intent: PortfolioIntent | None,
    context: AiStrategyDecisionContext,
    decision_service: PreOrderDecisionService,
) -> TradingAgentsStrategyDecision:
    """
    Convert one stored AI trade intent into an audited risk decision.
    """
    if trade_intent is None:
        return ignored("no_ai_signal")

    action = trade_intent.action.strip().lower()
    if action not in EXECUTABLE_ACTIONS:
        return TradingAgentsStrategyDecision(
            trade_intent=trade_intent,
            order_intent=None,
            fused_signal=None,
            decision=None,
            ignored_reason="non_executable_action",
        )

    order_intent = OrderIntent(
        vt_symbol=context.vt_symbol,
        action=action,
        price=context.price,
        volume=context.volume,
        current_position=context.current_position,
        daily_traded_value=context.daily_traded_value,
        drawdown=context.drawdown,
        cancel_count=context.cancel_count,
        limit_up=context.limit_up,
        limit_down=context.limit_down,
    )
    fused_signal = FusedSignal(
        action=action,
        confidence=1.0,
        ai_decision=SignalDecision.ALLOW,
        ai_used=True,
        source_run_ids=[trade_intent.source_run_id],
    )
    decision = decision_service.evaluate(order_intent, fused_signal)
    return TradingAgentsStrategyDecision(
        trade_intent=trade_intent,
        order_intent=order_intent,
        fused_signal=fused_signal,
        decision=decision,
    )


def ignored(reason: str) -> TradingAgentsStrategyDecision:
    """
    Build an ignored strategy decision without side effects.
    """
    return TradingAgentsStrategyDecision(
        trade_intent=None,
        order_intent=None,
        fused_signal=None,
        decision=None,
        ignored_reason=reason,
    )
