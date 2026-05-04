from datetime import datetime

import pytest

from vnpy_tradingagents.fusion import RuleSignal, SignalFusionService
from vnpy_tradingagents.gateway_policy import GatewayAccountMode, GatewayAiPolicy, GatewayProfile
from vnpy_tradingagents.policy import AiSignalPolicy
from vnpy_tradingagents.risk import (
    OrderIntent,
    PreOrderDecisionService,
    RiskRuleSet,
)
from vnpy_tradingagents.runtime import TradingAgentsMode, TradingAgentsRuntimeController
from vnpy_tradingagents.signals import IntradayAdvice, PortfolioIntent, RatingSignal
from vnpy_tradingagents.worker import TradingAgentsWorkerResponse


def test_backtesting_app_bridge_evaluates_decision_without_gateway_and_writes_audit():
    """BacktestingAppBridge should attach AI signal evaluation to a vn.py backtest point."""
    from vnpy_tradingagents.backtesting_app_bridge import (
        BacktestingAppBridge,
        BacktestingDecisionPoint,
    )

    runtime = TradingAgentsRuntimeController()
    runtime.enable(mode=TradingAgentsMode.PAPER_ONLY)
    audit_storage = FakeAuditStorage()
    app_bridge = BacktestingAppBridge(
        signal_reader=FakeSignalReader(),
        fusion_service=SignalFusionService(policy=AiSignalPolicy(runtime)),
        decision_service=PreOrderDecisionService(
            rules=RiskRuleSet(max_order_value=100_000),
            audit_storage=audit_storage,
            decision_id_factory=lambda: "decision-backtest-app",
        ),
    )

    result = app_bridge.evaluate_decision(
        BacktestingDecisionPoint(
            vt_symbol="600519.SSE",
            trade_date="2024-01-03",
            at=datetime(2024, 1, 3, 10, 15),
            rule_signal=RuleSignal(action="buy", confidence=0.8, reason="rule"),
            order_intent=OrderIntent("600519.SSE", "buy", 100, 10),
        )
    )

    assert not hasattr(app_bridge, "gateway")
    assert not hasattr(app_bridge, "main_engine")
    assert result.decision.submit_allowed
    assert audit_storage.saved[0].decision_id == "decision-backtest-app"
    assert audit_storage.saved[0].ai_source_run_ids == ["rating-1", "advice-1"]


def test_paper_bridge_records_account_snapshot_only_for_simulation():
    """PaperAccountBridge should convert simulation account returns into feedback."""
    from vnpy_tradingagents.paper_bridge import PaperAccountBridge, PaperAccountSnapshot, SimulatedTrade

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
    bridge.record_account_snapshot(
        PaperAccountSnapshot(
            vt_symbol="600519.SSE",
            as_of=datetime(2024, 1, 3, 15),
            portfolio_value=1_020_000,
            previous_value=1_000_000,
            benchmark_return=0.01,
            turnover_rate=0.03,
            max_drawdown=0.02,
        )
    )

    assert runtime.can_use_signal(live=False)
    assert feedback_storage.performance_feedback[0].portfolio_return == 0.02
    assert feedback_storage.performance_feedback[0].alpha == 0.01

    live_bridge = PaperAccountBridge(
        runtime=TradingAgentsRuntimeController(),
        gateway_policy=GatewayAiPolicy(allow_live_ai=True),
        feedback_storage=FakeFeedbackStorage(),
    )
    live_bridge.configure(
        GatewayProfile(gateway_name="LIVE", account_mode=GatewayAccountMode.LIVE),
        ai_enabled=True,
    )
    with pytest.raises(RuntimeError, match="simulation"):
        live_bridge.record_account_snapshot(
            PaperAccountSnapshot(
                vt_symbol="600519.SSE",
                as_of=datetime(2024, 1, 3, 15),
                portfolio_value=1,
                previous_value=1,
                benchmark_return=0,
                turnover_rate=0,
                max_drawdown=0,
            )
        )

    with pytest.raises(ValueError, match="non-executable"):
        bridge.record_fill(
            SimulatedTrade(
                source_run_id="run-hold",
                vt_symbol="600519.SSE",
                trade_date="2024-01-03",
                action="hold",
                volume=100,
                price=1688,
                slippage=0,
                pnl=0,
            )
        )


def test_ui_manual_takeover_and_replay_status_storage_helpers():
    """UI helpers should pause AI and load replay status from storage."""
    from vnpy_tradingagents.monitoring import ReplayRunStatus
    from vnpy_tradingagents.ui.widget import (
        apply_manual_takeover,
        load_replay_status_panel_text,
    )

    engine = FakeEngine()
    engine.enable(mode=TradingAgentsMode.LIVE_ALLOWED, live_enabled=True)

    state = apply_manual_takeover(engine, "operator_pause")

    assert not state.enabled
    assert not engine.runtime.can_use_signal(live=False)
    assert not engine.runtime.can_use_signal(live=True)

    status = ReplayRunStatus(
        run_id="gray-1",
        mode="paper",
        generated_at=datetime(2024, 1, 3, 15),
        health="ready",
        total_steps=1,
        submit_allowed=1,
        risk_rejected=0,
        ai_blocked=0,
        rating_blocked=0,
        ai_used=1,
        latest_decision_id="decision-1",
    )
    text = load_replay_status_panel_text(FakeStatusStorage(status), "gray-1")

    assert "gray-1" in text
    assert "decision-1" in text


def test_paper_smoke_runs_snapshot_worker_signal_fill_feedback_without_live_gateway():
    """Paper smoke should exercise snapshot -> worker -> paper fill -> feedback only."""
    from vnpy_tradingagents.paper_bridge import PaperAccountBridge
    from vnpy_tradingagents.paper_smoke import PaperSmokeConfig, TradingAgentsPaperSmoke

    runtime = TradingAgentsRuntimeController()
    feedback_storage = FakeFeedbackStorage()
    paper_bridge = PaperAccountBridge(
        runtime=runtime,
        gateway_policy=GatewayAiPolicy(),
        feedback_storage=feedback_storage,
    )
    smoke = TradingAgentsPaperSmoke(
        reader=SnapshotReaderFake(),
        worker=SmokeWorker(),
        agent_storage=RecordingAgentStorage(),
        paper_bridge=paper_bridge,
    )

    result = smoke.run(
        PaperSmokeConfig(
            vt_symbol="600519.SSE",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 3),
            fill_price=1688,
            fill_volume=100,
        )
    )

    assert result.success
    assert result.live_gateway_touched is False
    assert runtime.state.mode == TradingAgentsMode.PAPER_ONLY
    assert feedback_storage.trade_feedback[0].run_id == result.response.run_id


def test_paper_smoke_does_not_record_fill_for_hold_advice():
    """Paper smoke should not convert non-executable hold advice into a simulated fill."""
    from vnpy_tradingagents.paper_bridge import PaperAccountBridge
    from vnpy_tradingagents.paper_smoke import PaperSmokeConfig, TradingAgentsPaperSmoke

    runtime = TradingAgentsRuntimeController()
    feedback_storage = FakeFeedbackStorage()
    paper_bridge = PaperAccountBridge(
        runtime=runtime,
        gateway_policy=GatewayAiPolicy(),
        feedback_storage=feedback_storage,
    )
    smoke = TradingAgentsPaperSmoke(
        reader=SnapshotReaderFake(),
        worker=HoldWorker(),
        agent_storage=RecordingAgentStorage(),
        paper_bridge=paper_bridge,
    )

    result = smoke.run(
        PaperSmokeConfig(
            vt_symbol="600519.SSE",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 3),
            fill_price=1688,
            fill_volume=100,
        )
    )

    assert result.success
    assert paper_bridge.positions == {}
    assert feedback_storage.trade_feedback == []


def test_ops_storage_records_heartbeat_and_metrics_export_json_line():
    """Ops storage and metrics should expose machine-readable production health."""
    from vnpy_tradingagents.metrics import MetricsCollector
    from vnpy_tradingagents.ops_storage import OpsHeartbeat, PostgresOpsStorage

    storage = PostgresOpsStorage(FakeConnection())
    heartbeat = OpsHeartbeat(
        component="tradingagents-worker",
        heartbeat_at=datetime(2024, 1, 3, 15),
        status="degraded",
        last_error="timeout",
        data_latency_seconds=12.5,
        queue_backlog=3,
        degraded_sources=["news", "sentiment"],
    )

    storage.save_heartbeat(heartbeat)
    collector = MetricsCollector()
    collector.record_run(success=True, latency_seconds=1.2, degraded_sources=["news"])
    collector.record_run(success=False, latency_seconds=2.5, degraded_sources=["sentiment"])
    collector.record_blocked_order("max_order_value")
    line = collector.to_json_line()

    assert "INSERT INTO ops_heartbeat" in storage.connection.cursor_obj.executed[0][0]
    assert '"run_count": 2' in line
    assert '"failure_count": 1' in line
    assert '"blocked_orders": 1' in line
    assert "max_order_value" in line


def test_secrets_policy_masks_and_blocks_secret_context():
    """Secrets policy should keep API keys out of logs, DB payloads and worker context."""
    from vnpy_tradingagents.secrets_policy import (
        SecretLeakError,
        assert_context_has_no_secrets,
        mask_secret,
        sanitize_mapping,
    )

    masked = mask_secret("sk-1234567890")
    assert masked.startswith("sk-1")
    assert masked.endswith("90")
    assert "2345678" not in masked
    sanitized = sanitize_mapping({"api_key": "sk-1234567890", "model": "gpt"})
    sanitized_text = sanitize_mapping(
        {"news": [{"headline": "leaked OPENAI_API_KEY=sk-1234567890 in text"}]}
    )

    assert sanitized["api_key"] == masked
    assert "sk-1234567890" not in sanitized_text["news"][0]["headline"]
    with pytest.raises(SecretLeakError):
        assert_context_has_no_secrets({"market": {}, "OPENAI_API_KEY": "sk-123"})
    with pytest.raises(SecretLeakError):
        assert_context_has_no_secrets(
            {
                "market": {},
                "news": [{"headline": "leaked OPENAI_API_KEY=sk-1234567890 in text"}],
            }
        )
    assert_context_has_no_secrets({"news": [{"headline": "OpenAI earnings report without credentials"}]})


def test_worker_adapter_blocks_secret_context_before_runner():
    """Worker adapter should reject API keys before context reaches any runner."""
    from vnpy_tradingagents.config import TradingAgentsWorkerConfig
    from vnpy_tradingagents.worker import TradingAgentsWorkerRequest
    from vnpy_tradingagents.worker_adapter import TradingAgentsWorkerAdapter

    adapter = TradingAgentsWorkerAdapter(
        config=TradingAgentsWorkerConfig(api_key_env_var="TEST_KEY"),
        runner=FailIfCalledRunner(),
        environ={"TEST_KEY": "llm-key"},
    )

    response = adapter.run(
        TradingAgentsWorkerRequest(
            run_id="run-1",
            vt_symbol="600519.SSE",
            trade_date="2024-01-03",
            mode="paper",
            context={
                "market": {"bars": [{"close": 10}]},
                "api_key": "sk-should-not-enter-runner",
            },
        )
    )

    assert response.action == "hold"
    assert response.raw_state["error_type"] == "secret_context"


def test_schema_initializer_includes_ops_heartbeat_schema():
    """Default schema migrations should include P11 operational heartbeat storage."""
    from vnpy_tradingagents.schema_init import DEFAULT_MIGRATIONS

    migrations = {migration.version: migration.sql for migration in DEFAULT_MIGRATIONS}
    sql = "\n".join(migrations.values())

    assert "CREATE TABLE IF NOT EXISTS ops_heartbeat" in sql
    assert "0003_ops_heartbeat" in migrations


class FakeSignalReader:
    """Signal reader fake for backtesting."""

    def load_latest_rating_signal(self, vt_symbol, trade_date):
        return RatingSignal(vt_symbol, "Buy", 0.8, "rating-1")

    def load_latest_intraday_advice(self, vt_symbol, at):
        return IntradayAdvice(vt_symbol, "buy", 0.7, at.replace(minute=at.minute + 5), "advice-1")

    def load_portfolio_intents(self, trade_date):
        return [PortfolioIntent("600519.SSE", trade_date, "buy", 0.1, "20d", "risk", "intent-1")]


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
        self.performance_feedback = []

    def save_trade_feedback(self, feedback):
        self.trade_feedback.append(feedback)

    def save_performance_feedback(self, feedback):
        self.performance_feedback.append(feedback)


class FakeEngine:
    """Tiny engine fake with runtime controller methods."""

    def __init__(self) -> None:
        self.runtime = TradingAgentsRuntimeController()

    def enable(self, mode=TradingAgentsMode.REPORT_ONLY, live_enabled=False):
        self.runtime.enable(mode=mode, live_enabled=live_enabled)

    def disable(self, reason=""):
        self.runtime.disable(reason)

    def pause_manual_takeover(self, reason="manual_takeover"):
        self.runtime.pause_manual_takeover(reason)

    def get_state(self):
        return self.runtime.state


class FakeStatusStorage:
    """Fake replay status storage."""

    def __init__(self, status) -> None:
        self.status = status

    def load_latest_status(self, run_id):
        return self.status if run_id == self.status.run_id else None


class SnapshotReaderFake:
    """Snapshot reader fake for paper smoke."""

    def load_bar_snapshots(self, vt_symbol, start, end):
        return [{"datetime": "2024-01-03", "close": 1688}]

    def load_latest_snapshot(self, snapshot_type, vt_symbol, as_of):
        return {}


class SmokeWorker:
    """Worker fake for paper smoke."""

    def run(self, request):
        return TradingAgentsWorkerResponse(
            run_id=request.run_id,
            vt_symbol=request.vt_symbol,
            rating="Buy",
            confidence=0.8,
            report="paper smoke",
            raw_state={"status": "ok"},
            action="buy",
            risk_notes="risk checked",
        )


class HoldWorker:
    """Worker fake returning hold advice for paper smoke."""

    def run(self, request):
        return TradingAgentsWorkerResponse(
            run_id=request.run_id,
            vt_symbol=request.vt_symbol,
            rating="Neutral",
            confidence=0.6,
            report="paper smoke hold",
            raw_state={"status": "ok"},
            action="hold",
            risk_notes="wait",
        )


class FailIfCalledRunner:
    """Runner fake that should never receive secret context."""

    def run(self, payload):
        raise AssertionError("runner should not be called")


class RecordingAgentStorage:
    """Agent storage fake."""

    def __init__(self) -> None:
        self.saved = []

    def save_worker_result(self, request, response):
        self.saved.append((request, response))


class FakeCursor:
    """Tiny DB-API cursor fake."""

    def __init__(self) -> None:
        self.executed = []

    def execute(self, sql, params=None) -> None:
        self.executed.append((sql, params or {}))

    def close(self) -> None:
        return


class FakeConnection:
    """Tiny DB-API connection fake."""

    def __init__(self) -> None:
        self.cursor_obj = FakeCursor()
        self.commits = 0

    def cursor(self):
        return self.cursor_obj

    def commit(self) -> None:
        self.commits += 1
