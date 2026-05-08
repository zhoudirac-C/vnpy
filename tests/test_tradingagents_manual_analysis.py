from datetime import datetime

from vnpy_tradingagents.runtime import TradingAgentsMode, TradingAgentsRuntimeController
from vnpy_tradingagents.worker import TradingAgentsWorkerRequest, TradingAgentsWorkerResponse


def test_manual_analysis_service_builds_context_runs_worker_and_persists():
    """Manual analysis should be a report-only AI entrypoint, not an order path."""
    from vnpy_tradingagents.manual_analysis import (
        ManualAnalysisRequest,
        TradingAgentsManualAnalysisService,
    )

    runtime = TradingAgentsRuntimeController()
    runtime.enable(mode=TradingAgentsMode.REPORT_ONLY)
    toolkit = FakeToolkit()
    worker = FakeWorker()
    storage = FakeAgentStorage()
    service = TradingAgentsManualAnalysisService(
        runtime=runtime,
        toolkit=toolkit,
        worker=worker,
        storage=storage,
        run_id_factory=lambda _: "manual-1",
    )

    result = service.run(
        ManualAnalysisRequest(
            vt_symbol="600519.SSE",
            start=datetime(2024, 1, 1, 9, 30),
            end=datetime(2024, 1, 3, 15),
        )
    )

    assert result.status == "completed"
    assert result.response is not None
    assert result.response.action == "buy"
    assert result.request.run_id == "manual-1"
    assert result.request.mode == "manual_analysis"
    assert result.request.context["manual_analysis"]["entrypoint"] == "TradingAgentsApp"
    assert toolkit.queries[0].vt_symbol == "600519.SSE"
    assert worker.requests == [result.request]
    assert storage.saved == [(result.request, result.response)]
    assert runtime.state.last_successful_run_id == "manual-1"


def test_manual_analysis_service_returns_disabled_without_calling_worker():
    """Manual analysis should be explicit about disabled AI instead of silently doing work."""
    from vnpy_tradingagents.manual_analysis import (
        ManualAnalysisRequest,
        TradingAgentsManualAnalysisService,
    )

    service = TradingAgentsManualAnalysisService(
        runtime=TradingAgentsRuntimeController(),
        toolkit=FakeToolkit(),
        worker=FakeWorker(),
        storage=FakeAgentStorage(),
        run_id_factory=lambda _: "manual-1",
    )

    result = service.run(
        ManualAnalysisRequest(
            vt_symbol="600519.SSE",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 3),
        )
    )

    assert result.status == "disabled"
    assert result.response is None
    assert result.request is None


def test_manual_analysis_service_persists_worker_failure_without_crashing():
    """Worker exceptions should become failed analysis results and still be auditable."""
    from vnpy_tradingagents.manual_analysis import (
        ManualAnalysisRequest,
        TradingAgentsManualAnalysisService,
    )

    runtime = TradingAgentsRuntimeController()
    runtime.enable(mode=TradingAgentsMode.REPORT_ONLY)
    storage = FakeAgentStorage()
    service = TradingAgentsManualAnalysisService(
        runtime=runtime,
        toolkit=FakeToolkit(),
        worker=FailingWorker(),
        storage=storage,
        run_id_factory=lambda _: "manual-failed",
    )

    result = service.run(
        ManualAnalysisRequest(
            vt_symbol="600519.SSE",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 3),
        )
    )

    assert result.status == "failed"
    assert result.response is not None
    assert result.response.raw_state["status"] == "failed"
    assert storage.saved == [(result.request, result.response)]
    assert runtime.state.disabled_reason == "boom"


def test_engine_delegates_manual_analysis_service():
    """TradingAgentsEngine should expose a small service hook for the UI."""
    from vnpy.event import EventEngine

    from vnpy_tradingagents.engine import TradingAgentsEngine
    from vnpy_tradingagents.manual_analysis import ManualAnalysisRequest

    engine = TradingAgentsEngine(None, EventEngine())  # type: ignore[arg-type]
    service = FakeManualAnalysisService()
    engine.set_manual_analysis_service(service)

    request = ManualAnalysisRequest(
        vt_symbol="600519.SSE",
        start=datetime(2024, 1, 1),
        end=datetime(2024, 1, 3),
    )

    result = engine.run_manual_analysis(request)

    assert result == "manual-result"
    assert service.requests == [request]


def test_manual_analysis_summary_text_hides_order_language():
    """UI summary should present AI output as analysis, not as an executed order."""
    from vnpy_tradingagents.manual_analysis import ManualAnalysisResult
    from vnpy_tradingagents.ui.widget import build_manual_analysis_summary_text

    result = ManualAnalysisResult(
        status="completed",
        request=TradingAgentsWorkerRequest(
            run_id="manual-1",
            vt_symbol="600519.SSE",
            trade_date="2024-01-03",
            mode="manual_analysis",
            context={},
        ),
        response=make_response(),
    )

    text = build_manual_analysis_summary_text(result)

    assert "600519.SSE" in text
    assert "rating=Buy" in text
    assert "action=buy" in text
    assert "risk=回撤风险" in text
    assert "send_order" not in text


class FakeToolkit:
    """Tiny toolkit fake that records snapshot queries."""

    def __init__(self) -> None:
        self.queries = []

    def build_context(self, query):
        self.queries.append(query)
        return {"market": {"bars": [{"close": 100}]}}


class FakeWorker:
    """Fake worker returning a fixed manual analysis response."""

    def __init__(self) -> None:
        self.requests = []

    def run(self, request: TradingAgentsWorkerRequest) -> TradingAgentsWorkerResponse:
        self.requests.append(request)
        return make_response(run_id=request.run_id)


class FailingWorker:
    """Worker fake that raises for failure-path coverage."""

    def run(self, request: TradingAgentsWorkerRequest) -> TradingAgentsWorkerResponse:
        raise RuntimeError("boom")


class FakeAgentStorage:
    """Fake agent storage that records persisted worker results."""

    def __init__(self) -> None:
        self.saved = []

    def save_worker_result(self, request, response) -> None:
        self.saved.append((request, response))


class FakeManualAnalysisService:
    """Fake manual service for engine delegation tests."""

    def __init__(self) -> None:
        self.requests = []

    def run(self, request):
        self.requests.append(request)
        return "manual-result"


def make_response(run_id: str = "manual-1") -> TradingAgentsWorkerResponse:
    """Create a manual analysis worker response fixture."""
    return TradingAgentsWorkerResponse(
        run_id=run_id,
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
