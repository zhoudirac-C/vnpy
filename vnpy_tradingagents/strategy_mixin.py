from datetime import datetime
from typing import Protocol

from .fusion import FusedSignal, RuleSignal, SignalFusionService
from .policy import AiSignalPolicy, SignalDecision
from .runtime import TradingAgentsRuntimeController
from .signals import IntradayAdvice, RatingSignal


class SignalReader(Protocol):
    """
    Reader protocol for strategy-side AI signals.
    """

    def load_latest_intraday_advice(
        self,
        vt_symbol: str,
        at: datetime,
    ) -> IntradayAdvice | None:
        pass

    def load_latest_rating_signal(
        self,
        vt_symbol: str,
        trade_date: str,
    ) -> RatingSignal | None:
        pass


class TradingAgentsStrategyMixin:
    """
    Shared strategy-side helpers for reading and fusing TradingAgents signals.
    """

    ai_runtime: TradingAgentsRuntimeController
    signal_reader: SignalReader
    ai_fusion_service: SignalFusionService

    def init_ai_signal_support(
        self,
        runtime: TradingAgentsRuntimeController,
        signal_reader: SignalReader,
    ) -> None:
        """
        Initialize AI signal dependencies from strategy engine setup.
        """
        self.ai_runtime = runtime
        self.signal_reader = signal_reader
        self.ai_fusion_service = SignalFusionService(AiSignalPolicy(runtime))

    def load_ai_intraday_advice(
        self,
        vt_symbol: str,
        at: datetime,
        live: bool = False,
    ) -> IntradayAdvice | None:
        """
        Load latest intraday advice when AI signal use is allowed.
        """
        if not self.ai_runtime.can_use_signal(live):
            return None
        return self.signal_reader.load_latest_intraday_advice(vt_symbol, at)

    def load_ai_rating_signal(
        self,
        vt_symbol: str,
        trade_date: str,
        live: bool = False,
    ) -> RatingSignal | None:
        """
        Load latest long-horizon rating when AI signal use is allowed.
        """
        if not self.ai_runtime.can_use_signal(live):
            return None
        return self.signal_reader.load_latest_rating_signal(vt_symbol, trade_date)

    def fuse_ai_signal(
        self,
        rule_signal: RuleSignal,
        vt_symbol: str,
        now: datetime,
        live: bool = False,
    ) -> FusedSignal:
        """
        Fuse strategy signal with AI signals, or return rule signal unchanged.
        """
        rating: RatingSignal | None = self.load_ai_rating_signal(
            vt_symbol,
            now.date().isoformat(),
            live,
        )
        advice: IntradayAdvice | None = self.load_ai_intraday_advice(
            vt_symbol,
            now,
            live,
        )
        if rating is None or advice is None:
            return FusedSignal(
                action=rule_signal.action,
                confidence=rule_signal.confidence,
                ai_decision=SignalDecision.IGNORE,
                ai_used=False,
                blocked_reason="ai_unavailable",
                source_run_ids=[],
            )

        return self.ai_fusion_service.fuse(rule_signal, rating, advice, now, live)
