from dataclasses import dataclass
from datetime import datetime

from .backtesting_bridge import BacktestingBridge, BacktestingDecisionResult, BacktestingSignalReader
from .fusion import RuleSignal, SignalFusionService
from .risk import OrderIntent, PreOrderDecisionService


@dataclass(frozen=True)
class BacktestingDecisionPoint:
    """
    One vn.py backtesting decision point where AI signals may be evaluated.
    """

    vt_symbol: str
    trade_date: str
    at: datetime
    rule_signal: RuleSignal
    order_intent: OrderIntent


class BacktestingAppBridge:
    """
    Thin app-facing adapter for vn.py backtesting paths.
    """

    def __init__(
        self,
        signal_reader: BacktestingSignalReader,
        fusion_service: SignalFusionService,
        decision_service: PreOrderDecisionService,
    ) -> None:
        """"""
        self.bridge: BacktestingBridge = BacktestingBridge(
            signal_reader=signal_reader,
            fusion_service=fusion_service,
            decision_service=decision_service,
        )

    def evaluate_decision(
        self,
        point: BacktestingDecisionPoint,
    ) -> BacktestingDecisionResult:
        """
        Evaluate one historical decision without Gateway/MainEngine access.
        """
        return self.bridge.evaluate_intraday(
            vt_symbol=point.vt_symbol,
            trade_date=point.trade_date,
            at=point.at,
            rule_signal=point.rule_signal,
            order_intent=point.order_intent,
        )
