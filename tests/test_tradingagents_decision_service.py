from datetime import datetime

from vnpy_tradingagents.fusion import FusedSignal
from vnpy_tradingagents.policy import SignalDecision
from vnpy_tradingagents.risk import (
    OrderIntent,
    PreOrderDecisionService,
    RiskDecision,
    RiskRuleSet,
)


def test_pre_order_decision_service_allows_approved_intent_and_audits():
    """PreOrderDecisionService should audit and allow intents that pass risk."""
    audit_storage = FakeAuditStorage()
    service = PreOrderDecisionService(
        rules=RiskRuleSet(max_order_value=100_000),
        audit_storage=audit_storage,
        decision_id_factory=lambda: "decision-1",
        clock=lambda: datetime(2024, 1, 3, 10, 10),
    )

    result = service.evaluate(intent=make_intent(), fused_signal=make_fused_signal())

    assert result.submit_allowed
    assert result.risk_result.decision == RiskDecision.APPROVED
    assert result.audit_record.decision_id == "decision-1"
    assert audit_storage.saved == [result.audit_record]


def test_pre_order_decision_service_blocks_rejected_intent_and_audits():
    """PreOrderDecisionService should audit rejected intents and block submit."""
    audit_storage = FakeAuditStorage()
    service = PreOrderDecisionService(
        rules=RiskRuleSet(max_order_value=1_000),
        audit_storage=audit_storage,
        decision_id_factory=lambda: "decision-2",
        clock=lambda: datetime(2024, 1, 3, 10, 10),
    )

    result = service.evaluate(intent=make_intent(price=100, volume=50), fused_signal=make_fused_signal())

    assert not result.submit_allowed
    assert result.risk_result.decision == RiskDecision.REJECTED
    assert result.risk_result.failed_rule == "max_order_value"
    assert result.audit_record.risk_failed_rule == "max_order_value"
    assert audit_storage.saved == [result.audit_record]


def make_intent(price: float = 100, volume: float = 50) -> OrderIntent:
    """Create an order intent fixture."""
    return OrderIntent(
        vt_symbol="600519.SSE",
        action="buy",
        price=price,
        volume=volume,
    )


def make_fused_signal() -> FusedSignal:
    """Create a fused signal fixture."""
    return FusedSignal(
        action="buy",
        confidence=0.9,
        ai_decision=SignalDecision.ALLOW,
        ai_used=True,
        source_run_ids=["run-rating", "run-advice"],
    )


class FakeAuditStorage:
    """Fake audit storage recording saved records."""

    def __init__(self) -> None:
        self.saved = []

    def save_decision(self, record):
        self.saved.append(record)
