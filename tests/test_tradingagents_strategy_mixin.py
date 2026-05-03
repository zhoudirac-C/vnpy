from datetime import datetime

from vnpy_tradingagents.fusion import RuleSignal
from vnpy_tradingagents.policy import SignalDecision
from vnpy_tradingagents.runtime import TradingAgentsMode, TradingAgentsRuntimeController
from vnpy_tradingagents.signals import IntradayAdvice, RatingSignal
from vnpy_tradingagents.strategy_mixin import TradingAgentsStrategyMixin


def test_strategy_mixin_returns_rule_signal_when_ai_disabled():
    """Strategy mixin should leave deterministic strategy output untouched when AI is off."""
    strategy = DemoStrategy()
    strategy.init_ai_signal_support(
        runtime=TradingAgentsRuntimeController(),
        signal_reader=FakeSignalReader(),
    )

    fused = strategy.fuse_ai_signal(
        rule_signal=RuleSignal("buy", 0.7, "breakout"),
        vt_symbol="600519.SSE",
        now=datetime(2024, 1, 3, 10),
    )

    assert fused.action == "buy"
    assert fused.ai_decision == SignalDecision.IGNORE
    assert not fused.ai_used
    assert strategy.signal_reader.advice_calls == []


def test_strategy_mixin_loads_and_fuses_ai_signals_when_enabled():
    """Strategy mixin should share one AI signal read/fusion path for strategies."""
    runtime = TradingAgentsRuntimeController()
    runtime.enable(mode=TradingAgentsMode.PAPER_ONLY)
    reader = FakeSignalReader(
        rating=RatingSignal("600519.SSE", "Buy", 0.8, "rating-1"),
        advice=IntradayAdvice(
            "600519.SSE",
            "buy",
            0.75,
            datetime(2024, 1, 3, 10, 15),
            "advice-1",
        ),
    )
    strategy = DemoStrategy()
    strategy.init_ai_signal_support(runtime=runtime, signal_reader=reader)

    fused = strategy.fuse_ai_signal(
        rule_signal=RuleSignal("buy", 0.7, "breakout"),
        vt_symbol="600519.SSE",
        now=datetime(2024, 1, 3, 10),
    )

    assert fused.ai_used
    assert fused.source_run_ids == ["rating-1", "advice-1"]


def test_strategy_mixin_blocks_rule_buy_on_bearish_rating():
    """Strategy mixin should apply the shared policy to bearish long-horizon ratings."""
    runtime = TradingAgentsRuntimeController()
    runtime.enable(mode=TradingAgentsMode.PAPER_ONLY)
    strategy = DemoStrategy()
    strategy.init_ai_signal_support(
        runtime=runtime,
        signal_reader=FakeSignalReader(
            rating=RatingSignal("600519.SSE", "Sell", 0.9, "rating-1"),
            advice=IntradayAdvice(
                "600519.SSE",
                "buy",
                0.8,
                datetime(2024, 1, 3, 10, 15),
                "advice-1",
            ),
        ),
    )

    fused = strategy.fuse_ai_signal(
        rule_signal=RuleSignal("buy", 0.7),
        vt_symbol="600519.SSE",
        now=datetime(2024, 1, 3, 10),
    )

    assert fused.action == "hold"
    assert fused.blocked_reason == "ai_block_buy"


class DemoStrategy(TradingAgentsStrategyMixin):
    """Tiny class that uses TradingAgentsStrategyMixin methods."""


class FakeSignalReader:
    """Signal reader fake."""

    def __init__(
        self,
        rating: RatingSignal | None = None,
        advice: IntradayAdvice | None = None,
    ) -> None:
        self.rating = rating
        self.advice = advice
        self.rating_calls = []
        self.advice_calls = []

    def load_latest_intraday_advice(self, vt_symbol: str, at: datetime):
        self.advice_calls.append((vt_symbol, at))
        return self.advice

    def load_latest_rating_signal(self, vt_symbol: str, trade_date: str):
        self.rating_calls.append((vt_symbol, trade_date))
        return self.rating
