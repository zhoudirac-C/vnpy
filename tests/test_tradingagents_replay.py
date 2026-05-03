from datetime import datetime

from vnpy_tradingagents.fusion import RuleSignal, SignalFusionService
from vnpy_tradingagents.policy import AiSignalPolicy
from vnpy_tradingagents.replay import IntradayReplayEngine, ReplayStep
from vnpy_tradingagents.risk import OrderIntent, PreOrderDecisionService, RiskRuleSet
from vnpy_tradingagents.runtime import TradingAgentsMode, TradingAgentsRuntimeController
from vnpy_tradingagents.signals import IntradayAdvice, RatingSignal


def test_intraday_replay_engine_counts_allowed_and_rejected_steps():
    """IntradayReplayEngine should replay fusion, risk and audit in time order."""
    audit_storage = FakeAuditStorage()
    engine = make_engine(audit_storage=audit_storage)
    steps = [
        make_step(
            at=datetime(2024, 1, 3, 10, 10),
            rating="Buy",
            rule_action="buy",
            advice_action="buy_on_pullback",
            price=100,
            volume=50,
        ),
        make_step(
            at=datetime(2024, 1, 3, 10, 15),
            rating="Sell",
            rule_action="buy",
            advice_action="buy_on_pullback",
            price=100,
            volume=50,
        ),
        make_step(
            at=datetime(2024, 1, 3, 10, 20),
            rating="Buy",
            rule_action="buy",
            advice_action="buy_on_pullback",
            price=100,
            volume=2_000,
        ),
    ]

    summary = engine.run(steps)

    assert summary.total_steps == 3
    assert summary.submit_allowed == 1
    assert summary.risk_rejected == 1
    assert summary.ai_blocked == 1
    assert summary.ai_used == 2
    assert len(summary.results) == 3
    assert audit_storage.saved == [result.decision.audit_record for result in summary.results]
    assert summary.results[0].submit_allowed
    assert not summary.results[1].submit_allowed
    assert summary.results[1].fused_signal.blocked_reason == "ai_block_buy"
    assert not summary.results[2].submit_allowed
    assert summary.results[2].decision.risk_result.failed_rule == "max_order_value"


def test_intraday_replay_engine_keeps_rule_logic_when_ai_disabled():
    """Replay should keep deterministic rule/risk flow when TradingAgents is disabled."""
    audit_storage = FakeAuditStorage()
    engine = make_engine(audit_storage=audit_storage, tradingagents_enabled=False)

    summary = engine.run(
        [
            make_step(
                at=datetime(2024, 1, 3, 10, 10),
                rating="Buy",
                rule_action="buy",
                advice_action="buy_on_pullback",
                price=100,
                volume=50,
            )
        ]
    )

    assert summary.total_steps == 1
    assert summary.submit_allowed == 1
    assert summary.ai_used == 0
    assert summary.results[0].fused_signal.blocked_reason == "ai_unavailable"
    assert audit_storage.saved == [summary.results[0].decision.audit_record]


def make_engine(
    audit_storage,
    tradingagents_enabled: bool = True,
) -> IntradayReplayEngine:
    """Create a replay engine fixture."""
    runtime = TradingAgentsRuntimeController()
    if tradingagents_enabled:
        runtime.enable(mode=TradingAgentsMode.PAPER_ONLY)

    counter = DecisionCounter()
    return IntradayReplayEngine(
        fusion_service=SignalFusionService(policy=AiSignalPolicy(runtime=runtime)),
        decision_service=PreOrderDecisionService(
            rules=RiskRuleSet(max_order_value=100_000),
            audit_storage=audit_storage,
            decision_id_factory=counter.next,
        ),
        live=False,
    )


def make_step(
    at: datetime,
    rating: str,
    rule_action: str,
    advice_action: str,
    price: float,
    volume: float,
) -> ReplayStep:
    """Create a replay step fixture."""
    return ReplayStep(
        at=at,
        rule_signal=RuleSignal(action=rule_action, confidence=0.9, reason="replay_rule"),
        rating=RatingSignal(
            vt_symbol="600519.SSE",
            rating=rating,
            confidence=0.8,
            source_run_id=f"rating-{at:%H%M}",
        ),
        advice=IntradayAdvice(
            vt_symbol="600519.SSE",
            action=advice_action,
            confidence=0.7,
            valid_until=at.replace(minute=at.minute + 5),
            source_run_id=f"advice-{at:%H%M}",
        ),
        intent=OrderIntent(
            vt_symbol="600519.SSE",
            action=rule_action,
            price=price,
            volume=volume,
        ),
    )


class DecisionCounter:
    """Stable decision id factory for replay tests."""

    def __init__(self) -> None:
        self.value = 0

    def next(self) -> str:
        self.value += 1
        return f"decision-{self.value}"


class FakeAuditStorage:
    """Fake audit storage recording replay audit records."""

    def __init__(self) -> None:
        self.saved = []

    def save_decision(self, record):
        self.saved.append(record)
