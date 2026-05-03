from datetime import datetime

from vnpy_tradingagents.fusion import RuleSignal, SignalFusionService
from vnpy_tradingagents.gateway_policy import GatewayAccountMode, GatewayAiPolicy, GatewayProfile
from vnpy_tradingagents.policy import AiSignalPolicy
from vnpy_tradingagents.risk import (
    DecisionAuditRecord,
    OrderIntent,
    PreOrderDecisionService,
    RiskDecision,
    RiskRuleSet,
)
from vnpy_tradingagents.runtime import SignalStatus, TradingAgentsMode, TradingAgentsRuntimeController
from vnpy_tradingagents.signals import IntradayAdvice, PortfolioIntent, RatingSignal


def test_backtesting_bridge_reads_ai_signals_and_writes_audit_without_gateway():
    """Backtesting bridge should use signal/risk services without real Gateway handles."""
    from vnpy_tradingagents.backtesting_bridge import BacktestingBridge

    runtime = TradingAgentsRuntimeController()
    runtime.enable(mode=TradingAgentsMode.PAPER_ONLY)
    audit_storage = FakeAuditStorage()
    bridge = BacktestingBridge(
        signal_reader=FakeSignalReader(),
        fusion_service=SignalFusionService(policy=AiSignalPolicy(runtime)),
        decision_service=PreOrderDecisionService(
            rules=RiskRuleSet(max_order_value=100_000),
            audit_storage=audit_storage,
            decision_id_factory=lambda: "decision-backtest-1",
        ),
    )

    result = bridge.evaluate_intraday(
        vt_symbol="600519.SSE",
        trade_date="2024-01-03",
        at=datetime(2024, 1, 3, 10, 10),
        rule_signal=RuleSignal(action="buy", confidence=0.9, reason="rule"),
        order_intent=OrderIntent("600519.SSE", "buy", 100, 10),
    )

    assert not hasattr(bridge, "gateway")
    assert not hasattr(bridge, "main_engine")
    assert result.signal_bundle.rating.source_run_id == "rating-1"
    assert result.signal_bundle.advice.source_run_id == "advice-1"
    assert result.signal_bundle.portfolio_intents[0].source_run_id == "intent-1"
    assert result.decision.submit_allowed
    assert audit_storage.saved[0].decision_id == "decision-backtest-1"
    assert audit_storage.saved[0].ai_source_run_ids == ["rating-1", "advice-1"]


def test_paper_bridge_enables_only_simulation_and_writes_trade_feedback():
    """Paper bridge should gate AI by simulation mode and write simulated fill feedback."""
    from vnpy_tradingagents.paper_bridge import PaperAccountBridge, SimulatedTrade

    runtime = TradingAgentsRuntimeController()
    feedback_storage = FakeFeedbackStorage()
    bridge = PaperAccountBridge(
        runtime=runtime,
        gateway_policy=GatewayAiPolicy(),
        feedback_storage=feedback_storage,
    )

    bridge.configure(
        GatewayProfile(gateway_name="PAPER", account_mode=GatewayAccountMode.SIMULATION),
        ai_enabled=True,
    )
    bridge.record_fill(
        SimulatedTrade(
            source_run_id="run-1",
            vt_symbol="600519.SSE",
            trade_date="2024-01-03",
            action="buy",
            volume=100,
            price=1650,
            slippage=0.001,
            pnl=230,
        )
    )

    assert runtime.state.mode == TradingAgentsMode.PAPER_ONLY
    assert runtime.can_use_signal(live=False)
    assert bridge.positions["600519.SSE"] == 100
    assert feedback_storage.trade_feedback[0].run_id == "run-1"
    assert feedback_storage.trade_feedback[0].payload["account_mode"] == "simulation"


def test_replay_run_status_storage_persists_and_loads_latest_status():
    """Replay run status should be queryable by run_id for UI and logs."""
    from vnpy_tradingagents.monitoring import (
        REPLAY_RUN_STATUS_SCHEMA,
        PostgresReplayRunStatusStorage,
        ReplayRunStatus,
    )

    assert "CREATE TABLE IF NOT EXISTS replay_run_status" in REPLAY_RUN_STATUS_SCHEMA

    status = ReplayRunStatus(
        run_id="gray-1",
        mode="portfolio",
        generated_at=datetime(2024, 1, 3, 16, 0),
        health="ready",
        total_steps=2,
        submit_allowed=1,
        risk_rejected=0,
        ai_blocked=0,
        rating_blocked=0,
        ai_used=2,
        latest_decision_id="decision-1",
        latest_vt_symbol="600519.SSE",
        latest_action="buy",
        latest_ai_decision="allow",
        latest_ai_used=True,
        latest_risk_decision="approved",
        latest_ai_source_run_ids=["rating-1"],
    )
    connection = FakeConnection(fetchone_row=status.to_dict())
    storage = PostgresReplayRunStatusStorage(connection)

    storage.save_status(status)
    loaded = storage.load_latest_status("gray-1")

    assert "INSERT INTO replay_run_status" in connection.cursor_obj.executed[0][0]
    assert loaded is not None
    assert loaded.run_id == "gray-1"
    assert loaded.latest_ai_source_run_ids == ["rating-1"]


def test_audit_export_supports_jsonl_and_csv():
    """Gray runs should export complete audit rows for review."""
    from vnpy_tradingagents.audit_export import AuditExportRecord, export_audit_csv, export_audit_jsonl

    record = AuditExportRecord(
        audit=make_audit_record(),
        rule_signal={"action": "buy", "confidence": 0.9},
        order_intent={"vt_symbol": "600519.SSE", "action": "buy", "price": 100, "volume": 10},
        simulated_trade_id="sim-1",
        live_trade_id="",
    )

    jsonl = export_audit_jsonl([record])
    csv_text = export_audit_csv([record])

    assert jsonl.endswith("\n")
    assert '"ai_source_run_ids": ["rating-1", "advice-1"]' in jsonl
    assert "simulated_trade_id" in csv_text.splitlines()[0]
    assert "decision-1" in csv_text


def test_manual_takeover_pauses_all_ai_signal_use():
    """Manual takeover should disable paper and live AI signal consumption immediately."""
    runtime = TradingAgentsRuntimeController()
    runtime.enable(mode=TradingAgentsMode.LIVE_ALLOWED, live_enabled=True)
    runtime.mark_success("run-1")

    runtime.pause_manual_takeover("operator_pause")

    assert runtime.state.signal_status == SignalStatus.DISABLED
    assert runtime.state.disabled_reason == "operator_pause"
    assert not runtime.can_use_signal(live=False)
    assert not runtime.can_use_signal(live=True)


def test_schema_initializer_creates_all_postgres_tables_idempotently():
    """A fresh environment should initialize TradingAgents and router schemas in one call."""
    from vnpy_tradingagents.schema_init import initialize_postgres_schema

    connection = FakeConnection()

    initialize_postgres_schema(connection)
    initialize_postgres_schema(connection)

    executed_sql = "\n".join(sql for sql, _ in connection.cursor_obj.executed)
    assert "CREATE TABLE IF NOT EXISTS schema_version" in executed_sql
    assert "CREATE TABLE IF NOT EXISTS agent_run" in executed_sql
    assert "CREATE TABLE IF NOT EXISTS news_raw" in executed_sql
    assert "CREATE TABLE IF NOT EXISTS replay_run_status" in executed_sql
    assert connection.commits == 2


def test_live_gate_requires_simulation_health_audit_and_explicit_live_enable():
    """Live gate should refuse live_allowed until all small-capital checks pass."""
    from vnpy_tradingagents.live_gate import LiveGate, LiveGateConfig, LiveGateMetrics

    gate = LiveGate(LiveGateConfig(min_stable_days=5, max_drawdown=0.08, min_audit_completeness=1.0))
    runtime = TradingAgentsRuntimeController()
    runtime.enable(mode=TradingAgentsMode.PAPER_ONLY)
    metrics = LiveGateMetrics(
        simulation_stable_days=5,
        max_drawdown=0.03,
        audit_completeness=1.0,
    )

    refused = gate.evaluate(runtime, metrics)
    runtime.enable(mode=TradingAgentsMode.LIVE_ALLOWED, live_enabled=True)
    allowed = gate.evaluate(runtime, metrics)

    assert not refused.allowed
    assert refused.reason == "live_ai_not_enabled"
    assert allowed.allowed
    assert allowed.reason == "ready"


class FakeSignalReader:
    """Signal reader fake for backtesting bridge."""

    def load_latest_rating_signal(self, vt_symbol, trade_date):
        return RatingSignal(vt_symbol, "Buy", 0.8, "rating-1")

    def load_latest_intraday_advice(self, vt_symbol, at):
        return IntradayAdvice(vt_symbol, "buy", 0.7, at.replace(minute=at.minute + 5), "advice-1")

    def load_portfolio_intents(self, trade_date):
        return [PortfolioIntent("600519.SSE", trade_date, "buy", 0.10, "20d", "risk", "intent-1")]


class FakeAuditStorage:
    """Fake audit storage."""

    def __init__(self) -> None:
        self.saved = []

    def save_decision(self, record):
        self.saved.append(record)


class FakeFeedbackStorage:
    """Fake feedback storage."""

    def __init__(self) -> None:
        self.trade_feedback = []

    def save_trade_feedback(self, feedback):
        self.trade_feedback.append(feedback)


class FakeCursor:
    """Tiny DB-API cursor fake."""

    def __init__(self, fetchone_row=None) -> None:
        self.executed = []
        self.fetchone_row = fetchone_row

    def execute(self, sql, params=None) -> None:
        self.executed.append((sql, params or {}))

    def fetchone(self):
        return self.fetchone_row

    def close(self) -> None:
        return


class FakeConnection:
    """Tiny DB-API connection fake."""

    def __init__(self, fetchone_row=None) -> None:
        self.cursor_obj = FakeCursor(fetchone_row=fetchone_row)
        self.commits = 0

    def cursor(self):
        return self.cursor_obj

    def commit(self) -> None:
        self.commits += 1


def make_audit_record() -> DecisionAuditRecord:
    """Create one audit record fixture."""
    return DecisionAuditRecord(
        decision_id="decision-1",
        created_at=datetime(2024, 1, 3, 10, 10),
        vt_symbol="600519.SSE",
        action="buy",
        price=100,
        volume=10,
        rule_confidence=0.9,
        ai_decision="allow",
        ai_used=True,
        ai_source_run_ids=["rating-1", "advice-1"],
        risk_decision=RiskDecision.APPROVED,
        risk_failed_rule="",
        risk_reason="",
    )
