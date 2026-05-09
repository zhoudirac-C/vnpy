from vnpy_tradingagents.runtime import TradingAgentsMode, TradingAgentsRuntimeController
from vnpy_tradingagents.storage import PostgresAgentStorage, TRADINGAGENTS_SCHEMA
from vnpy_tradingagents.service import TradingAgentsService
from vnpy_tradingagents.worker import TradingAgentsWorkerRequest, TradingAgentsWorkerResponse


def test_tradingagents_schema_contains_core_signal_tables():
    """TradingAgents schema should persist runs, reports, ratings and intents."""
    assert "CREATE TABLE IF NOT EXISTS agent_run" in TRADINGAGENTS_SCHEMA
    assert "CREATE TABLE IF NOT EXISTS agent_report" in TRADINGAGENTS_SCHEMA
    assert "CREATE TABLE IF NOT EXISTS rating_signal" in TRADINGAGENTS_SCHEMA
    assert "CREATE TABLE IF NOT EXISTS trade_intent" in TRADINGAGENTS_SCHEMA
    assert "model_provider TEXT" in TRADINGAGENTS_SCHEMA
    assert "model_name TEXT" in TRADINGAGENTS_SCHEMA
    assert "prompt_version TEXT" in TRADINGAGENTS_SCHEMA
    assert "snapshot_ids JSONB" in TRADINGAGENTS_SCHEMA
    assert "error_message TEXT" in TRADINGAGENTS_SCHEMA


def test_agent_storage_saves_worker_response_to_signal_tables():
    """PostgresAgentStorage should persist worker outputs into auditable tables."""
    connection = FakeConnection()
    storage = PostgresAgentStorage(connection)
    request = make_request()
    response = make_response()

    storage.save_worker_result(request, response)

    executed_sql = [sql for sql, _ in connection.cursor_obj.executed]
    executed_params = [params for _, params in connection.cursor_obj.executed]
    assert connection.committed
    assert any("INSERT INTO agent_run" in sql for sql in executed_sql)
    assert any("INSERT INTO agent_report" in sql for sql in executed_sql)
    assert any("INSERT INTO rating_signal" in sql for sql in executed_sql)
    assert any("INSERT INTO trade_intent" in sql for sql in executed_sql)
    assert executed_params[0]["run_id"] == "run-1"
    assert executed_params[2]["rating"] == "Buy"
    assert executed_params[3]["action"] == "buy"
    assert '"decision": "buy"' in executed_params[1]["raw_state"]


def test_agent_storage_saves_model_metadata_and_snapshot_ids():
    """PostgresAgentStorage should persist replay/audit metadata for worker runs."""
    connection = FakeConnection()
    storage = PostgresAgentStorage(connection)
    request = TradingAgentsWorkerRequest(
        run_id="run-1",
        vt_symbol="600519.SSE",
        trade_date="2024-01-03",
        mode="report_only",
        context={
            "market": {"bars": []},
            "snapshot_ids": ["bar:600519.SSE:20240103"],
        },
    )
    response = TradingAgentsWorkerResponse(
        run_id="run-1",
        vt_symbol="600519.SSE",
        rating="Unavailable",
        confidence=0,
        report="failed",
        raw_state={
            "status": "failed",
            "model_provider": "openai",
            "model_name": "gpt-test",
            "prompt_version": "ashare-context-v1",
            "snapshot_ids": ["bar:600519.SSE:20240103", "fundamental:600519.SSE"],
            "error_message": "timeout",
        },
    )

    storage.save_worker_result(request, response)

    agent_run_params = connection.cursor_obj.executed[0][1]
    agent_report_params = connection.cursor_obj.executed[1][1]
    assert agent_run_params["model_provider"] == "openai"
    assert agent_run_params["model_name"] == "gpt-test"
    assert agent_run_params["prompt_version"] == "ashare-context-v1"
    assert "fundamental:600519.SSE" in agent_run_params["snapshot_ids"]
    assert agent_report_params["error_message"] == "timeout"


def test_agent_storage_loads_analysis_history_with_params_and_report():
    """Analysis history should join run metadata, report and signal outputs."""
    connection = FakeConnection()
    connection.cursor_obj.fetchall_rows = [
        {
            "run_id": "manual-1",
            "vt_symbol": "600519.SSE",
            "trade_date": "2026-05-08",
            "mode": "manual_analysis",
            "model_provider": "zhipu",
            "model_name": "glm-4.7",
            "prompt_version": "ashare-context-v1",
            "snapshot_ids": '["bar:600519.SSE:20260508"]',
            "context": '{"manual_analysis": {"window_days": 7}}',
            "created_at": "2026-05-08 11:00:00",
            "report": "## 多智能体报告\n结论",
            "raw_state": '{"status": "completed"}',
            "error_message": None,
            "rating": "Buy",
            "confidence": 0.82,
            "action": "buy",
            "target_weight_hint": 0.15,
            "holding_period_hint": "20d",
            "risk_notes": "回撤风险",
        }
    ]
    storage = PostgresAgentStorage(connection)

    records = storage.load_analysis_history("600519.SSE", limit=20)

    assert len(records) == 1
    record = records[0]
    assert record.run_id == "manual-1"
    assert record.vt_symbol == "600519.SSE"
    assert record.model_provider == "zhipu"
    assert record.snapshot_ids == ["bar:600519.SSE:20260508"]
    assert record.context["manual_analysis"]["window_days"] == 7
    assert record.report.startswith("## 多智能体报告")
    assert record.rating == "Buy"
    assert record.action == "buy"
    assert connection.cursor_obj.executed[-1][1] == {
        "vt_symbol": "600519.SSE",
        "limit": 20,
    }
    assert "LEFT JOIN agent_report" in connection.cursor_obj.executed[-1][0]


def test_service_runs_worker_and_persists_when_runtime_enabled():
    """TradingAgentsService should call worker and persist output when enabled."""
    runtime = TradingAgentsRuntimeController()
    runtime.enable(mode=TradingAgentsMode.REPORT_ONLY)
    worker = FakeWorker()
    storage = FakeAgentStorage()
    service = TradingAgentsService(runtime=runtime, worker=worker, storage=storage)
    request = make_request()

    response = service.run(request)

    assert response.rating == "Buy"
    assert worker.requests == [request]
    assert storage.saved == [(request, response)]
    assert runtime.state.last_successful_run_id == "run-1"


def test_service_blocks_worker_when_runtime_disabled():
    """TradingAgentsService should not call worker when global switch is disabled."""
    runtime = TradingAgentsRuntimeController()
    worker = FakeWorker()
    storage = FakeAgentStorage()
    service = TradingAgentsService(runtime=runtime, worker=worker, storage=storage)

    response = service.run(make_request())

    assert response is None
    assert worker.requests == []
    assert storage.saved == []


def make_request() -> TradingAgentsWorkerRequest:
    """Create a worker request fixture."""
    return TradingAgentsWorkerRequest(
        run_id="run-1",
        vt_symbol="600519.SSE",
        trade_date="2024-01-03",
        mode="report_only",
        context={"market": {"bars": []}},
    )


def make_response() -> TradingAgentsWorkerResponse:
    """Create a worker response fixture."""
    return TradingAgentsWorkerResponse(
        run_id="run-1",
        vt_symbol="600519.SSE",
        rating="Buy",
        confidence=0.82,
        report="多智能体报告",
        raw_state={"decision": "buy"},
        action="buy",
        target_weight_hint=0.15,
        holding_period_hint="20d",
        risk_notes="回撤风险",
    )


class FakeCursor:
    """Tiny DB-API cursor fake for storage unit tests."""

    def __init__(self) -> None:
        self.executed: list[tuple[str, dict]] = []
        self.fetchall_rows: list[dict] = []

    def execute(self, sql: str, params: dict | None = None) -> None:
        self.executed.append((sql, params or {}))

    def fetchall(self) -> list[dict]:
        return self.fetchall_rows

    def close(self) -> None:
        return


class FakeConnection:
    """Tiny DB-API connection fake for storage unit tests."""

    def __init__(self) -> None:
        self.cursor_obj = FakeCursor()
        self.committed = False

    def cursor(self) -> FakeCursor:
        return self.cursor_obj

    def commit(self) -> None:
        self.committed = True


class FakeWorker:
    """Fake worker returning a fixed response."""

    def __init__(self) -> None:
        self.requests: list[TradingAgentsWorkerRequest] = []

    def run(self, request: TradingAgentsWorkerRequest) -> TradingAgentsWorkerResponse:
        self.requests.append(request)
        return make_response()


class FakeAgentStorage:
    """Fake agent storage that records saved pairs."""

    def __init__(self) -> None:
        self.saved: list[tuple[TradingAgentsWorkerRequest, TradingAgentsWorkerResponse]] = []

    def save_worker_result(
        self,
        request: TradingAgentsWorkerRequest,
        response: TradingAgentsWorkerResponse,
    ) -> None:
        self.saved.append((request, response))
