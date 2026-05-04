from datetime import datetime
from pathlib import Path

from vnpy_tradingagents.config import TradingAgentsWorkerConfig
from vnpy_tradingagents.worker import TradingAgentsWorkerRequest, TradingAgentsWorkerResponse
from vnpy_tradingagents.worker_adapter import TradingAgentsContextPayload


def test_real_runner_returns_dependency_error_when_tradingagents_missing():
    """Real runner adapter should fail clearly when TradingAgents is unavailable."""
    from vnpy_tradingagents.real_runner import TradingAgentsRunnerAdapter

    runner = TradingAgentsRunnerAdapter(dependency_loader=missing_dependency_loader)

    result = runner.run(make_payload())

    assert result["action"] == "hold"
    assert result["rating"] == "Unavailable"
    assert result["raw_state"]["status"] == "failed"
    assert result["raw_state"]["error_type"] == "dependency_error"
    assert "TradingAgents dependency is not available" in result["risk_notes"]


def test_real_runner_maps_payload_to_context_only_native_input():
    """Real runner adapter should pass context-only input and isolated checkpoint path."""
    from vnpy_tradingagents.real_runner import TradingAgentsRunnerAdapter

    native_runner = RecordingNativeRunner()
    runner = TradingAgentsRunnerAdapter(native_runner=native_runner)
    payload = make_payload(
        run_id="run-1",
        vt_symbol="600519.SSE",
        trade_date="2024-01-03",
    )

    result = runner.run(payload)

    assert native_runner.input is not None
    assert native_runner.input["symbol"] == "600519.SSE"
    assert native_runner.input["trade_date"] == "2024-01-03"
    assert native_runner.input["context"] is payload.context
    assert "gateway" not in native_runner.input
    assert "main_engine" not in native_runner.input
    assert "send_order" not in native_runner.input
    assert native_runner.input["checkpoint_dir"].endswith("2024-01-03/600519_SSE/run-1")
    assert result["rating"] == "Buy"
    assert result["action"] == "buy"
    assert result["raw_state"]["native"] == "ok"


def test_real_runner_supports_tradingagents_graph_propagate_shape():
    """Legacy propagate support should be explicit because it bypasses context input."""
    from vnpy_tradingagents.real_runner import TradingAgentsRunnerAdapter

    native_runner = PropagateNativeRunner()
    runner = TradingAgentsRunnerAdapter(
        native_runner=native_runner,
        allow_legacy_propagate=True,
    )

    result = runner.run(make_payload())

    assert native_runner.args == ("600519.SSE", "2024-01-03")
    assert result["rating"] == "Buy"
    assert result["action"] == "buy"
    assert result["report"] == "BUY: portfolio manager approved a long entry"
    assert result["raw_state"]["native_state_type"] == "dict"


def test_real_runner_rejects_propagate_shape_by_default():
    """Production runner should not call propagate(symbol, date) without context."""
    from vnpy_tradingagents.real_runner import TradingAgentsRunnerAdapter

    native_runner = PropagateNativeRunner()
    runner = TradingAgentsRunnerAdapter(native_runner=native_runner)

    result = runner.run(make_payload())

    assert native_runner.args is None
    assert result["rating"] == "Unavailable"
    assert result["action"] == "hold"
    assert result["raw_state"]["error_type"] == "unsupported_runner_shape"


def test_real_runner_supports_structured_model_dump_output():
    """Real runner adapter should normalize Pydantic-like structured outputs."""
    from vnpy_tradingagents.real_runner import TradingAgentsRunnerAdapter

    runner = TradingAgentsRunnerAdapter(native_runner=StructuredOutputRunner())

    result = runner.run(make_payload())

    assert result["rating"] == "Overweight"
    assert result["action"] == "buy"
    assert result["confidence"] == 0.66
    assert result["risk_notes"] == "position size capped"


def test_output_validation_downgrades_invalid_action_and_clamps_confidence():
    """Output validation should keep invalid actions out of downstream intent tables."""
    from vnpy_tradingagents.output_validation import validate_worker_response

    response = TradingAgentsWorkerResponse(
        run_id="run-1",
        vt_symbol="600519.SSE",
        rating="StrongBuy",
        confidence=1.7,
        report="bad native output",
        raw_state={},
        action="send_order",
        risk_notes="",
    )

    validated = validate_worker_response(response)

    assert validated.rating == "Unavailable"
    assert validated.action == "hold"
    assert validated.confidence == 1
    assert validated.risk_notes == "invalid output downgraded"
    assert "invalid_action" in validated.raw_state["validation_errors"]
    assert "invalid_rating" in validated.raw_state["validation_errors"]


def test_output_validation_handles_non_numeric_confidence():
    """Output validation should downgrade invalid confidence without crashing."""
    from vnpy_tradingagents.output_validation import validate_worker_response

    response = TradingAgentsWorkerResponse(
        run_id="run-1",
        vt_symbol="600519.SSE",
        rating="Buy",
        confidence="high",
        report="bad native output",
        raw_state={},
        action="buy",
        risk_notes="",
    )

    validated = validate_worker_response(response)

    assert validated.confidence == 0
    assert "invalid_confidence" in validated.raw_state["validation_errors"]


def test_storage_validates_action_before_trade_intent_insert():
    """PostgresAgentStorage should not persist forbidden actions into trade_intent."""
    from vnpy_tradingagents.storage import PostgresAgentStorage

    connection = FakeConnection()
    storage = PostgresAgentStorage(connection)
    request = TradingAgentsWorkerRequest(
        run_id="run-1",
        vt_symbol="600519.SSE",
        trade_date="2024-01-03",
        mode="long_horizon",
        context={"market": {"bars": [{"close": 10}]}},
    )
    response = TradingAgentsWorkerResponse(
        run_id="run-1",
        vt_symbol="600519.SSE",
        rating="Buy",
        confidence=0.7,
        report="bad action",
        raw_state={},
        action="send_order",
        risk_notes="",
    )

    storage.save_worker_result(request, response)

    _, trade_params = connection.cursor_obj.executed[3]
    assert trade_params["action"] == "hold"
    assert trade_params["risk_notes"] == "invalid output downgraded"


def test_storage_does_not_create_signals_for_failed_worker_response():
    """Failed worker responses should be diagnostic only."""
    from vnpy_tradingagents.storage import PostgresAgentStorage

    connection = FakeConnection()
    storage = PostgresAgentStorage(connection)
    request = TradingAgentsWorkerRequest(
        run_id="run-failed",
        vt_symbol="600519.SSE",
        trade_date="2024-01-03",
        mode="long_horizon",
        context={"market": {"bars": [{"close": 10}]}},
    )
    response = TradingAgentsWorkerResponse(
        run_id="run-failed",
        vt_symbol="600519.SSE",
        rating="Unavailable",
        confidence=0,
        report="dependency missing",
        raw_state={"status": "failed", "error_type": "dependency_error"},
        action="hold",
        risk_notes="dependency missing",
    )

    storage.save_worker_result(request, response)

    executed_sql = "\n".join(sql for sql, _ in connection.cursor_obj.executed)
    assert "INSERT INTO agent_run" in executed_sql
    assert "INSERT INTO agent_report" in executed_sql
    assert "INSERT INTO rating_signal" not in executed_sql
    assert "INSERT INTO trade_intent" not in executed_sql


def test_worker_adapter_validates_native_mapping_output():
    """Worker adapter should validate mapping output before returning a response."""
    from vnpy_tradingagents.worker_adapter import TradingAgentsWorkerAdapter

    adapter = TradingAgentsWorkerAdapter(
        config=TradingAgentsWorkerConfig(api_key_env_var="TEST_KEY"),
        runner=InvalidActionRunner(),
        environ={"TEST_KEY": "secret"},
    )

    response = adapter.run(
        TradingAgentsWorkerRequest(
            run_id="run-1",
            vt_symbol="600519.SSE",
            trade_date="2024-01-03",
            mode="long_horizon",
            context={"market": {"bars": [{"close": 10}]}},
        )
    )

    assert response.action == "hold"
    assert response.rating == "Unavailable"
    assert "invalid_action" in response.raw_state["validation_errors"]


def test_checkpoint_path_is_isolated_by_date_symbol_and_run_id(tmp_path):
    """Worker config should isolate checkpoint/memory directories per run."""
    config = TradingAgentsWorkerConfig(checkpoint_dir=tmp_path / "checkpoints")

    first = config.checkpoint_path_for("run-1", "600519.SSE", "2024-01-03")
    second = config.checkpoint_path_for("run-2", "000001.SZSE", "2024-01-03")

    assert first != second
    assert first == tmp_path / "checkpoints" / "2024-01-03" / "600519_SSE" / "run-1"
    assert second == tmp_path / "checkpoints" / "2024-01-03" / "000001_SZSE" / "run-2"


def test_runner_smoke_success_persists_worker_result():
    """Runner smoke should build context, call worker, and persist structured output."""
    from vnpy_tradingagents.runner_smoke import RunnerSmokeConfig, TradingAgentsRunnerSmoke

    storage = RecordingStorage()
    smoke = TradingAgentsRunnerSmoke(
        reader=SnapshotReaderFake(),
        worker=SmokeWorker(),
        storage=storage,
        clock=lambda: datetime(2024, 1, 3, 16, 0),
    )

    result = smoke.run(
        RunnerSmokeConfig(
            vt_symbol="600519.SSE",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 3),
        )
    )

    assert result.success
    assert result.response is not None
    assert result.response.action == "buy"
    assert storage.saved[0][0].run_id == "smoke-2024-01-03-600519.SSE"
    assert storage.saved[0][0].context["market"]["bars"][0]["close"] == 10


def test_runner_smoke_returns_diagnostic_failure_without_persisting():
    """Runner smoke should return diagnosable failure when worker raises."""
    from vnpy_tradingagents.runner_smoke import RunnerSmokeConfig, TradingAgentsRunnerSmoke

    storage = RecordingStorage()
    smoke = TradingAgentsRunnerSmoke(
        reader=SnapshotReaderFake(),
        worker=CrashingWorker(),
        storage=storage,
        clock=lambda: datetime(2024, 1, 3, 16, 0),
    )

    result = smoke.run(
        RunnerSmokeConfig(
            vt_symbol="600519.SSE",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 3),
        )
    )

    assert not result.success
    assert result.error_type == "worker_error"
    assert "runner exploded" in result.error_message
    assert storage.saved == []


def make_payload(
    run_id: str = "run-1",
    vt_symbol: str = "600519.SSE",
    trade_date: str = "2024-01-03",
) -> TradingAgentsContextPayload:
    """Create a reusable context-only payload."""
    return TradingAgentsContextPayload(
        run_id=run_id,
        vt_symbol=vt_symbol,
        trade_date=trade_date,
        mode="long_horizon",
        context={"market": {"bars": [{"close": 10}]}},
        config=TradingAgentsWorkerConfig(
            api_key_env_var="TEST_KEY",
            checkpoint_dir=Path(".checkpoints"),
        ),
    )


def missing_dependency_loader():
    """Dependency loader fake that simulates missing TradingAgents."""
    raise ModuleNotFoundError("tradingagents")


class RecordingNativeRunner:
    """Fake native TradingAgents runner."""

    def __init__(self) -> None:
        self.input = None

    def run(self, native_input):
        self.input = native_input
        return {
            "rating": "Buy",
            "confidence": 0.8,
            "report": "native report",
            "action": "buy",
            "risk_notes": "native risk checked",
            "raw_state": {"native": "ok"},
        }


class PropagateNativeRunner:
    """Fake upstream TradingAgentsGraph runner."""

    def __init__(self) -> None:
        self.args = None

    def propagate(self, symbol, trade_date):
        self.args = (symbol, trade_date)
        return (
            {"final_trade_decision": "BUY: portfolio manager approved a long entry"},
            "BUY",
        )


class StructuredDecision:
    """Pydantic-like structured decision fake."""

    def model_dump(self):
        return {
            "rating": "Overweight",
            "confidence": 0.66,
            "action": "buy",
            "report": "structured decision",
            "risk_notes": "position size capped",
        }


class StructuredOutputRunner:
    """Runner fake that returns structured output."""

    def run(self, native_input):
        return StructuredDecision()


class InvalidActionRunner:
    """Runner fake that returns a forbidden action."""

    def run(self, payload):
        return {
            "rating": "StrongBuy",
            "confidence": 0.8,
            "report": "bad native report",
            "action": "send_order",
            "risk_notes": "",
        }


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

    def cursor(self):
        return self.cursor_obj

    def commit(self) -> None:
        return


class SnapshotReaderFake:
    """Snapshot reader fake for runner smoke."""

    def load_bar_snapshots(self, vt_symbol, start, end):
        return [{"datetime": "2024-01-03", "close": 10}]

    def load_latest_snapshot(self, snapshot_type, vt_symbol, as_of):
        return {"snapshot_type": snapshot_type}


class SmokeWorker:
    """Worker fake for successful smoke runs."""

    def run(self, request):
        return TradingAgentsWorkerResponse(
            run_id=request.run_id,
            vt_symbol=request.vt_symbol,
            rating="Buy",
            confidence=0.8,
            report="smoke report",
            raw_state={"status": "ok"},
            action="buy",
            risk_notes="risk checked",
        )


class CrashingWorker:
    """Worker fake that crashes during smoke run."""

    def run(self, request):
        raise RuntimeError("runner exploded")


class RecordingStorage:
    """Storage fake for smoke runs."""

    def __init__(self) -> None:
        self.saved = []

    def save_worker_result(self, request, response):
        self.saved.append((request, response))
