from dataclasses import dataclass, replace
from datetime import datetime
from typing import Protocol

from .fusion import FusedSignal, RuleSignal, SignalFusionService
from .risk import OrderIntent, PreOrderDecisionResult, PreOrderDecisionService
from .signals import IntradayAdvice, PortfolioIntent, RatingSignal


@dataclass(frozen=True)
class BacktestingSignalBundle:
    """
    AI signals read at a backtesting decision point.
    """

    rating: RatingSignal
    advice: IntradayAdvice
    portfolio_intents: list[PortfolioIntent]


@dataclass(frozen=True)
class BacktestingDecisionResult:
    """
    Backtesting decision result with signals, fusion and audit.
    """

    signal_bundle: BacktestingSignalBundle
    fused_signal: FusedSignal
    decision: PreOrderDecisionResult


class BacktestingSignalReader(Protocol):
    """
    Read persisted AI signals for historical timestamps.
    """

    def load_latest_rating_signal(self, vt_symbol: str, trade_date: str) -> RatingSignal:
        pass

    def load_latest_intraday_advice(self, vt_symbol: str, at: datetime) -> IntradayAdvice:
        pass

    def load_portfolio_intents(self, trade_date: str) -> list[PortfolioIntent]:
        pass


class BacktestingBridge:
    """
    Bridge vn.py backtests to AI signal fusion without accessing real gateways.
    """

    def __init__(
        self,
        signal_reader: BacktestingSignalReader,
        fusion_service: SignalFusionService,
        decision_service: PreOrderDecisionService,
    ) -> None:
        """"""
        self.signal_reader: BacktestingSignalReader = signal_reader
        self.fusion_service: SignalFusionService = fusion_service
        self.decision_service: PreOrderDecisionService = decision_service

    def evaluate_intraday(
        self,
        vt_symbol: str,
        trade_date: str,
        at: datetime,
        rule_signal: RuleSignal,
        order_intent: OrderIntent,
    ) -> BacktestingDecisionResult:
        """
        Read AI signals, fuse with rule signal, and run pre-order risk/audit.
        """
        bundle: BacktestingSignalBundle = self.load_signal_bundle(vt_symbol, trade_date, at)
        fused_signal: FusedSignal = self.fusion_service.fuse(
            rule_signal=rule_signal,
            rating=bundle.rating,
            advice=bundle.advice,
            now=at,
            live=False,
        )
        decision: PreOrderDecisionResult = self.decision_service.evaluate(
            intent=replace(order_intent, action=fused_signal.action),
            fused_signal=fused_signal,
        )
        return BacktestingDecisionResult(
            signal_bundle=bundle,
            fused_signal=fused_signal,
            decision=decision,
        )

    def load_signal_bundle(
        self,
        vt_symbol: str,
        trade_date: str,
        at: datetime,
    ) -> BacktestingSignalBundle:
        """
        Load rating, intraday advice and same-date portfolio intents.
        """
        intents: list[PortfolioIntent] = [
            intent
            for intent in self.signal_reader.load_portfolio_intents(trade_date)
            if intent.vt_symbol == vt_symbol
        ]
        return BacktestingSignalBundle(
            rating=self.signal_reader.load_latest_rating_signal(vt_symbol, trade_date),
            advice=self.signal_reader.load_latest_intraday_advice(vt_symbol, at),
            portfolio_intents=intents,
        )
