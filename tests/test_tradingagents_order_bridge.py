from datetime import datetime

from vnpy.trader.constant import Direction, Exchange, OrderType
from vnpy_tradingagents.fusion import FusedSignal
from vnpy_tradingagents.policy import SignalDecision
from vnpy_tradingagents.risk import OrderIntent, RiskRuleSet


def test_order_bridge_creates_order_request_after_audit_and_approval():
    """OrderBridge should save audit before returning an OrderRequest."""
    from vnpy_tradingagents.order_bridge import OrderBridge

    audit_storage = RecordingAuditStorage()
    bridge = OrderBridge(
        rules=RiskRuleSet(max_order_value=20_000),
        audit_storage=audit_storage,
        decision_id_factory=lambda: "decision-1",
        clock=lambda: datetime(2024, 1, 3, 10),
    )

    result = bridge.to_order_request(
        intent=OrderIntent("600519.SSE", "buy", price=100, volume=10),
        fused_signal=make_fused_signal(),
    )

    assert result.order_request is not None
    assert result.order_request.symbol == "600519"
    assert result.order_request.exchange == Exchange.SSE
    assert result.order_request.direction == Direction.LONG
    assert result.order_request.type == OrderType.LIMIT
    assert result.order_request.reference == "TradingAgents:decision-1"
    assert result.decision.audit_record.decision_id == "decision-1"
    assert audit_storage.saved[0].ai_source_run_ids == ["rating-1", "advice-1"]


def test_order_bridge_rejects_without_order_request_but_keeps_audit():
    """OrderBridge should not create OrderRequest when risk rejects the intent."""
    from vnpy_tradingagents.order_bridge import OrderBridge

    audit_storage = RecordingAuditStorage()
    bridge = OrderBridge(
        rules=RiskRuleSet(max_order_value=1_000),
        audit_storage=audit_storage,
        decision_id_factory=lambda: "decision-2",
        clock=lambda: datetime(2024, 1, 3, 10),
    )

    result = bridge.to_order_request(
        intent=OrderIntent("600519.SSE", "buy", price=100, volume=20),
        fused_signal=make_fused_signal(),
    )

    assert result.order_request is None
    assert not result.decision.submit_allowed
    assert audit_storage.saved[0].decision_id == "decision-2"
    assert audit_storage.saved[0].risk_failed_rule == "max_order_value"


def make_fused_signal() -> FusedSignal:
    """Create fused signal fixture."""
    return FusedSignal(
        action="buy",
        confidence=0.8,
        ai_decision=SignalDecision.ALLOW,
        ai_used=True,
        source_run_ids=["rating-1", "advice-1"],
    )


class RecordingAuditStorage:
    """Audit storage fake."""

    def __init__(self) -> None:
        self.saved = []

    def save_decision(self, record) -> None:
        self.saved.append(record)
