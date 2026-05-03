from datetime import datetime

from vnpy_tradingagents.policy import (
    AiSignalPolicy,
    IntradayAdvice,
    RatingSignal,
    SignalDecision,
)
from vnpy_tradingagents.runtime import TradingAgentsMode, TradingAgentsRuntimeController


def test_policy_blocks_signals_when_runtime_disabled():
    """AiSignalPolicy should ignore AI signals when TradingAgents is disabled."""
    policy = AiSignalPolicy(runtime=TradingAgentsRuntimeController())

    decision = policy.evaluate(
        rating=make_rating("Buy"),
        advice=make_advice("buy_on_pullback"),
        now=datetime(2024, 1, 3, 10, 10),
        live=False,
    )

    assert decision == SignalDecision.IGNORE


def test_policy_ignores_expired_intraday_advice():
    """Expired intraday advice should not be consumed by strategies."""
    runtime = TradingAgentsRuntimeController()
    runtime.enable(mode=TradingAgentsMode.PAPER_ONLY)
    policy = AiSignalPolicy(runtime=runtime)

    decision = policy.evaluate(
        rating=make_rating("Buy"),
        advice=make_advice("buy_on_pullback", valid_until=datetime(2024, 1, 3, 10, 0)),
        now=datetime(2024, 1, 3, 10, 10),
        live=False,
    )

    assert decision == SignalDecision.IGNORE


def test_policy_blocks_intraday_buy_when_long_term_rating_is_sell():
    """Long-term Sell/Underweight should block intraday buy advice."""
    runtime = TradingAgentsRuntimeController()
    runtime.enable(mode=TradingAgentsMode.PAPER_ONLY)
    policy = AiSignalPolicy(runtime=runtime)

    decision = policy.evaluate(
        rating=make_rating("Sell"),
        advice=make_advice("buy_on_pullback"),
        now=datetime(2024, 1, 3, 10, 10),
        live=False,
    )

    assert decision == SignalDecision.BLOCK_BUY


def test_policy_allows_valid_reduce_advice_under_sell_rating():
    """Sell rating can allow reduce or exit advice."""
    runtime = TradingAgentsRuntimeController()
    runtime.enable(mode=TradingAgentsMode.PAPER_ONLY)
    policy = AiSignalPolicy(runtime=runtime)

    decision = policy.evaluate(
        rating=make_rating("Sell"),
        advice=make_advice("reduce"),
        now=datetime(2024, 1, 3, 10, 10),
        live=False,
    )

    assert decision == SignalDecision.ALLOW


def test_policy_requires_live_enabled_for_live_consumption():
    """Live signal consumption should require explicit live mode."""
    runtime = TradingAgentsRuntimeController()
    runtime.enable(mode=TradingAgentsMode.PAPER_ONLY)
    policy = AiSignalPolicy(runtime=runtime)

    decision = policy.evaluate(
        rating=make_rating("Buy"),
        advice=make_advice("buy_on_pullback"),
        now=datetime(2024, 1, 3, 10, 10),
        live=True,
    )

    assert decision == SignalDecision.IGNORE


def make_rating(rating: str) -> RatingSignal:
    """Create a rating signal fixture."""
    return RatingSignal(
        vt_symbol="600519.SSE",
        rating=rating,
        confidence=0.8,
        source_run_id="run-1",
    )


def make_advice(
    action: str,
    valid_until: datetime | None = None,
) -> IntradayAdvice:
    """Create an intraday advice fixture."""
    return IntradayAdvice(
        vt_symbol="600519.SSE",
        action=action,
        confidence=0.7,
        valid_until=valid_until or datetime(2024, 1, 3, 10, 15),
        source_run_id="run-2",
    )
