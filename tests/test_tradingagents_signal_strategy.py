from datetime import datetime

from vnpy_tradingagents.risk import RiskDecision, RiskRuleSet
from vnpy_tradingagents.runtime import TradingAgentsMode, TradingAgentsRuntimeController
from vnpy_tradingagents.signals import PortfolioIntent


def test_signal_strategy_turns_ai_trade_intent_into_audited_order_intent():
    """Independent AI strategy should consume AI intent only through risk/audit."""
    from vnpy_tradingagents.strategies import (
        AiStrategyDecisionContext,
        TradingAgentsSignalStrategy,
    )

    runtime = TradingAgentsRuntimeController()
    runtime.enable(mode=TradingAgentsMode.PAPER_ONLY)
    audit_storage = FakeAuditStorage()
    strategy = TradingAgentsSignalStrategy(
        runtime=runtime,
        signal_reader=FakeSignalReader(make_intent(action="buy")),
        rules=RiskRuleSet(max_order_value=100_000),
        audit_storage=audit_storage,
        decision_id_factory=lambda: "decision-1",
        clock=lambda: datetime(2024, 1, 3, 10),
    )

    result = strategy.evaluate(
        AiStrategyDecisionContext(
            vt_symbol="600519.SSE",
            trade_time=datetime(2024, 1, 3, 10),
            price=100,
            volume=10,
            live=False,
        )
    )

    assert result.ignored_reason == ""
    assert result.trade_intent is not None
    assert result.order_intent is not None
    assert result.order_intent.action == "buy"
    assert result.decision is not None
    assert result.decision.submit_allowed
    assert result.decision.risk_result.decision == RiskDecision.APPROVED
    assert result.fused_signal.ai_used
    assert result.fused_signal.source_run_ids == ["run-buy"]
    assert audit_storage.saved == [result.decision.audit_record]


def test_signal_strategy_does_not_read_ai_when_runtime_disabled():
    """Independent AI strategy should be inert when the TradingAgents switch is off."""
    from vnpy_tradingagents.strategies import (
        AiStrategyDecisionContext,
        TradingAgentsSignalStrategy,
    )

    reader = FakeSignalReader(make_intent(action="buy"))
    strategy = TradingAgentsSignalStrategy(
        runtime=TradingAgentsRuntimeController(),
        signal_reader=reader,
        rules=RiskRuleSet(),
        audit_storage=FakeAuditStorage(),
    )

    result = strategy.evaluate(
        AiStrategyDecisionContext(
            vt_symbol="600519.SSE",
            trade_time=datetime(2024, 1, 3, 10),
            price=100,
            volume=10,
            live=False,
        )
    )

    assert result.ignored_reason == "ai_signal_disabled"
    assert result.trade_intent is None
    assert reader.trade_intent_calls == []


def test_signal_strategy_ignores_hold_and_watch_without_audit_or_order():
    """hold/watch are analysis outputs, not executable order intents."""
    from vnpy_tradingagents.strategies import (
        AiStrategyDecisionContext,
        TradingAgentsSignalStrategy,
    )

    runtime = TradingAgentsRuntimeController()
    runtime.enable(mode=TradingAgentsMode.PAPER_ONLY)
    audit_storage = FakeAuditStorage()
    strategy = TradingAgentsSignalStrategy(
        runtime=runtime,
        signal_reader=FakeSignalReader(make_intent(action="watch")),
        rules=RiskRuleSet(),
        audit_storage=audit_storage,
    )

    result = strategy.evaluate(
        AiStrategyDecisionContext(
            vt_symbol="600519.SSE",
            trade_time=datetime(2024, 1, 3, 10),
            price=100,
            volume=10,
            live=False,
        )
    )

    assert result.ignored_reason == "non_executable_action"
    assert result.order_intent is None
    assert result.decision is None
    assert audit_storage.saved == []


def test_signal_strategy_defaults_to_live_scope_and_blocks_paper_ai():
    """Production use should not accidentally consume paper-only AI signals."""
    from vnpy_tradingagents.strategies import (
        AiStrategyDecisionContext,
        TradingAgentsSignalStrategy,
    )

    runtime = TradingAgentsRuntimeController()
    runtime.enable(mode=TradingAgentsMode.PAPER_ONLY)
    reader = FakeSignalReader(make_intent(action="buy"))
    strategy = TradingAgentsSignalStrategy(
        runtime=runtime,
        signal_reader=reader,
        rules=RiskRuleSet(),
        audit_storage=FakeAuditStorage(),
    )

    result = strategy.evaluate(
        AiStrategyDecisionContext(
            vt_symbol="600519.SSE",
            trade_time=datetime(2024, 1, 3, 10),
            price=100,
            volume=10,
        )
    )

    assert result.ignored_reason == "ai_signal_disabled"
    assert reader.trade_intent_calls == []


def test_postgres_signal_reader_loads_latest_trade_intent():
    """DB signal reader should expose latest stored intent for independent AI strategy."""
    from vnpy_tradingagents.storage import PostgresSignalReader

    connection = FakeConnection(
        row={
            "vt_symbol": "600519.SSE",
            "trade_date": "2024-01-03",
            "action": "buy",
            "target_weight_hint": 0.15,
            "holding_period_hint": "20d",
            "risk_notes": "回撤风险",
            "run_id": "run-buy",
        }
    )
    reader = PostgresSignalReader(connection)

    intent = reader.load_latest_trade_intent("600519.SSE", "2024-01-04")

    assert intent == make_intent()
    assert "FROM trade_intent" in connection.cursor_obj.executed[0][0]


def make_intent(action: str = "buy") -> PortfolioIntent:
    """Create a stored AI trade intent fixture."""
    return PortfolioIntent(
        vt_symbol="600519.SSE",
        trade_date="2024-01-03",
        action=action,
        target_weight_hint=0.15,
        holding_period_hint="20d",
        risk_notes="回撤风险",
        source_run_id=f"run-{action}",
    )


class FakeSignalReader:
    """Signal reader fake for independent AI strategy tests."""

    def __init__(self, intent: PortfolioIntent | None) -> None:
        self.intent = intent
        self.trade_intent_calls = []

    def load_latest_trade_intent(self, vt_symbol: str, trade_date: str):
        self.trade_intent_calls.append((vt_symbol, trade_date))
        return self.intent


class FakeAuditStorage:
    """Audit storage fake recording saved decisions."""

    def __init__(self) -> None:
        self.saved = []

    def save_decision(self, record) -> None:
        self.saved.append(record)


class FakeCursor:
    """Tiny cursor fake returning one row."""

    def __init__(self, row) -> None:
        self.row = row
        self.executed = []

    def execute(self, sql: str, params: dict | None = None) -> None:
        self.executed.append((sql, params or {}))

    def fetchone(self):
        return self.row

    def fetchall(self):
        return []

    def close(self) -> None:
        return


class FakeConnection:
    """Tiny DB fake for PostgresSignalReader tests."""

    def __init__(self, row) -> None:
        self.cursor_obj = FakeCursor(row)

    def cursor(self) -> FakeCursor:
        return self.cursor_obj

    def commit(self) -> None:
        return
