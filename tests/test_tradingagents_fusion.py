from datetime import datetime

from vnpy_tradingagents.fusion import RuleSignal, SignalFusionService
from vnpy_tradingagents.policy import AiSignalPolicy, SignalDecision
from vnpy_tradingagents.signals import IntradayAdvice, RatingSignal
from vnpy_tradingagents.runtime import TradingAgentsMode, TradingAgentsRuntimeController


def test_fusion_allows_rule_confirmed_ai_buy():
    """SignalFusionService should allow AI buy advice only when rules also buy."""
    service = make_service(enabled=True)

    signal = service.fuse(
        rule_signal=RuleSignal(action="buy", confidence=0.9, reason="breakout"),
        rating=make_rating("Buy"),
        advice=make_advice("buy_on_pullback"),
        now=datetime(2024, 1, 3, 10, 10),
        live=False,
    )

    assert signal.action == "buy"
    assert signal.ai_decision == SignalDecision.ALLOW
    assert signal.ai_used
    assert signal.source_run_ids == ["run-rating", "run-advice"]


def test_fusion_does_not_turn_hold_into_buy_from_ai_only():
    """AI advice should not create a new buy without rule confirmation."""
    service = make_service(enabled=True)

    signal = service.fuse(
        rule_signal=RuleSignal(action="hold", confidence=0.6, reason="no_rule_signal"),
        rating=make_rating("Buy"),
        advice=make_advice("buy_on_pullback"),
        now=datetime(2024, 1, 3, 10, 10),
        live=False,
    )

    assert signal.action == "hold"
    assert signal.ai_decision == SignalDecision.ALLOW
    assert not signal.ai_used
    assert signal.blocked_reason == "rule_not_confirmed"


def test_fusion_blocks_rule_buy_when_long_rating_is_sell():
    """Bearish long-term rating should block AI-assisted new buys."""
    service = make_service(enabled=True)

    signal = service.fuse(
        rule_signal=RuleSignal(action="buy", confidence=0.9, reason="breakout"),
        rating=make_rating("Sell"),
        advice=make_advice("buy_on_pullback"),
        now=datetime(2024, 1, 3, 10, 10),
        live=False,
    )

    assert signal.action == "hold"
    assert signal.ai_decision == SignalDecision.BLOCK_BUY
    assert not signal.ai_used
    assert signal.blocked_reason == "ai_block_buy"


def test_fusion_keeps_rule_signal_when_tradingagents_disabled():
    """Disabling TradingAgents should leave non-AI strategy logic intact."""
    service = make_service(enabled=False)

    signal = service.fuse(
        rule_signal=RuleSignal(action="buy", confidence=0.9, reason="breakout"),
        rating=make_rating("Buy"),
        advice=make_advice("buy_on_pullback"),
        now=datetime(2024, 1, 3, 10, 10),
        live=False,
    )

    assert signal.action == "buy"
    assert signal.ai_decision == SignalDecision.IGNORE
    assert not signal.ai_used
    assert signal.blocked_reason == "ai_unavailable"


def make_service(enabled: bool) -> SignalFusionService:
    """Create a fusion service fixture."""
    runtime = TradingAgentsRuntimeController()
    if enabled:
        runtime.enable(mode=TradingAgentsMode.PAPER_ONLY)
    return SignalFusionService(policy=AiSignalPolicy(runtime=runtime))


def make_rating(rating: str) -> RatingSignal:
    """Create a rating fixture."""
    return RatingSignal(
        vt_symbol="600519.SSE",
        rating=rating,
        confidence=0.8,
        source_run_id="run-rating",
    )


def make_advice(action: str) -> IntradayAdvice:
    """Create an intraday advice fixture."""
    return IntradayAdvice(
        vt_symbol="600519.SSE",
        action=action,
        confidence=0.7,
        valid_until=datetime(2024, 1, 3, 10, 15),
        source_run_id="run-advice",
    )
