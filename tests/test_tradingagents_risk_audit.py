from datetime import datetime

from vnpy_tradingagents.fusion import FusedSignal
from vnpy_tradingagents.policy import SignalDecision
from vnpy_tradingagents.risk import (
    DecisionAuditRecord,
    OrderIntent,
    PostgresDecisionAuditStorage,
    RiskDecision,
    RiskRuleSet,
)


def test_risk_rule_set_rejects_blacklisted_symbol():
    """RiskRuleSet should reject intents for blacklisted symbols."""
    rules = RiskRuleSet(blacklist=frozenset({"600519.SSE"}))

    result = rules.evaluate(make_intent())

    assert result.decision == RiskDecision.REJECTED
    assert result.failed_rule == "blacklist"


def test_risk_rule_set_rejects_order_value_above_limit():
    """RiskRuleSet should cap single-order notional value."""
    rules = RiskRuleSet(max_order_value=10_000)

    result = rules.evaluate(make_intent(price=100, volume=200))

    assert result.decision == RiskDecision.REJECTED
    assert result.failed_rule == "max_order_value"


def test_risk_rule_set_rejects_buy_above_position_limit():
    """RiskRuleSet should prevent buy intents from exceeding position limit."""
    rules = RiskRuleSet(max_position_volume=120)

    result = rules.evaluate(make_intent(action="buy", volume=50, current_position=100))

    assert result.decision == RiskDecision.REJECTED
    assert result.failed_rule == "max_position_volume"


def test_risk_rule_set_rejects_daily_traded_value_above_limit():
    """RiskRuleSet should cap total traded value for the day."""
    rules = RiskRuleSet(max_daily_traded_value=20_000)

    result = rules.evaluate(make_intent(price=100, volume=50, daily_traded_value=16_000))

    assert result.decision == RiskDecision.REJECTED
    assert result.failed_rule == "max_daily_traded_value"


def test_risk_rule_set_rejects_drawdown_above_limit():
    """RiskRuleSet should block trading after max drawdown is breached."""
    rules = RiskRuleSet(max_drawdown=0.08)

    result = rules.evaluate(make_intent(drawdown=0.1))

    assert result.decision == RiskDecision.REJECTED
    assert result.failed_rule == "max_drawdown"


def test_risk_rule_set_rejects_cancel_count_above_limit():
    """RiskRuleSet should block trading after excessive cancels."""
    rules = RiskRuleSet(max_cancel_count=10)

    result = rules.evaluate(make_intent(cancel_count=11))

    assert result.decision == RiskDecision.REJECTED
    assert result.failed_rule == "max_cancel_count"


def test_risk_rule_set_rejects_buy_at_limit_up():
    """RiskRuleSet should reject buy intents at limit-up."""
    rules = RiskRuleSet()

    result = rules.evaluate(make_intent(action="buy", price=110, limit_up=110))

    assert result.decision == RiskDecision.REJECTED
    assert result.failed_rule == "limit_up_buy"


def test_risk_rule_set_rejects_sell_at_limit_down():
    """RiskRuleSet should reject sell intents at limit-down."""
    rules = RiskRuleSet()

    result = rules.evaluate(make_intent(action="sell", price=90, limit_down=90))

    assert result.decision == RiskDecision.REJECTED
    assert result.failed_rule == "limit_down_sell"


def test_risk_rule_set_approves_valid_intent():
    """RiskRuleSet should approve intents that pass all configured rules."""
    rules = RiskRuleSet(
        max_order_value=100_000,
        max_position_volume=200,
        max_daily_traded_value=200_000,
        max_drawdown=0.08,
    )

    result = rules.evaluate(
        make_intent(
            action="buy",
            price=100,
            volume=50,
            current_position=100,
            daily_traded_value=20_000,
            drawdown=0.03,
        )
    )

    assert result.decision == RiskDecision.APPROVED
    assert result.failed_rule == ""


def test_decision_audit_record_captures_fusion_and_risk_context():
    """DecisionAuditRecord should keep AI source ids together with risk result."""
    fused = FusedSignal(
        action="buy",
        confidence=0.9,
        ai_decision=SignalDecision.ALLOW,
        ai_used=True,
        source_run_ids=["run-rating", "run-advice"],
    )
    risk_result = RiskRuleSet(max_order_value=100_000).evaluate(make_intent())

    record = DecisionAuditRecord.from_decision(
        decision_id="decision-1",
        created_at=datetime(2024, 1, 3, 10, 10),
        intent=make_intent(),
        fused_signal=fused,
        risk_result=risk_result,
    )

    assert record.decision_id == "decision-1"
    assert record.vt_symbol == "600519.SSE"
    assert record.ai_source_run_ids == ["run-rating", "run-advice"]
    assert record.risk_decision == RiskDecision.APPROVED
    assert record.risk_failed_rule == ""


def test_postgres_decision_audit_storage_persists_record():
    """PostgresDecisionAuditStorage should persist auditable pre-order decisions."""
    connection = FakeConnection()
    storage = PostgresDecisionAuditStorage(connection)
    record = DecisionAuditRecord.from_decision(
        decision_id="decision-1",
        created_at=datetime(2024, 1, 3, 10, 10),
        intent=make_intent(),
        fused_signal=FusedSignal(
            action="buy",
            confidence=0.9,
            ai_decision=SignalDecision.ALLOW,
            ai_used=True,
            source_run_ids=["run-rating"],
        ),
        risk_result=RiskRuleSet(max_order_value=100_000).evaluate(make_intent()),
    )

    storage.save_decision(record)

    sql, params = connection.cursor_obj.executed[0]
    assert connection.committed
    assert "INSERT INTO decision_audit" in sql
    assert params["decision_id"] == "decision-1"
    assert params["risk_decision"] == "approved"
    assert '"run-rating"' in params["ai_source_run_ids"]


def make_intent(
    action: str = "buy",
    price: float = 100,
    volume: float = 50,
    current_position: float = 0,
    daily_traded_value: float = 0,
    drawdown: float = 0,
    cancel_count: int = 0,
    limit_up: float | None = None,
    limit_down: float | None = None,
) -> OrderIntent:
    """Create an order intent fixture."""
    return OrderIntent(
        vt_symbol="600519.SSE",
        action=action,
        price=price,
        volume=volume,
        current_position=current_position,
        daily_traded_value=daily_traded_value,
        drawdown=drawdown,
        cancel_count=cancel_count,
        limit_up=limit_up,
        limit_down=limit_down,
    )


class FakeCursor:
    """Tiny DB-API cursor fake for audit storage unit tests."""

    def __init__(self) -> None:
        self.executed: list[tuple[str, dict]] = []

    def execute(self, sql: str, params: dict | None = None) -> None:
        self.executed.append((sql, params or {}))

    def close(self) -> None:
        return


class FakeConnection:
    """Tiny DB-API connection fake for audit storage unit tests."""

    def __init__(self) -> None:
        self.cursor_obj = FakeCursor()
        self.committed = False

    def cursor(self) -> FakeCursor:
        return self.cursor_obj

    def commit(self) -> None:
        self.committed = True
