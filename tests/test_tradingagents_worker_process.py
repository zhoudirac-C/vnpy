import json
import sys

from vnpy_tradingagents.runtime import SignalStatus, TradingAgentsMode
from vnpy_tradingagents.service import TradingAgentsService
from vnpy_tradingagents.worker import TradingAgentsWorkerRequest, TradingAgentsWorkerResponse


def test_worker_process_runs_json_request_with_injected_worker():
    """Worker process helper should accept JSON input and return JSON output."""
    from vnpy_tradingagents.worker_process import run_worker_process_json

    output_text = run_worker_process_json(json.dumps(make_request_dict()), EchoWorker())
    output = json.loads(output_text)

    assert output["run_id"] == "run-1"
    assert output["vt_symbol"] == "600519.SSE"
    assert output["rating"] == "Buy"
    assert output["action"] == "buy"
    assert output["raw_state"]["status"] == "ok"


def test_subprocess_worker_returns_failed_response_on_timeout():
    """Subprocess worker should return auditable failure on timeout."""
    from vnpy_tradingagents.worker_process import SubprocessTradingAgentsWorker

    worker = SubprocessTradingAgentsWorker(
        [
            sys.executable,
            "-c",
            "import time; time.sleep(1)",
        ],
        timeout_seconds=0.01,
        max_retries=0,
    )

    response = worker.run(make_request())

    assert response.action == "hold"
    assert response.raw_state["status"] == "failed"
    assert response.raw_state["error_type"] == "timeout"


def test_service_marks_runtime_degraded_when_worker_raises():
    """Service should degrade runtime instead of leaking worker exceptions."""
    from vnpy_tradingagents.runtime import TradingAgentsRuntimeController

    runtime = TradingAgentsRuntimeController()
    runtime.enable(mode=TradingAgentsMode.REPORT_ONLY)
    storage = RecordingStorage()
    service = TradingAgentsService(
        runtime=runtime,
        worker=RaisingWorker(),
        storage=storage,
    )

    response = service.run(make_request())

    assert response is not None
    assert response.action == "hold"
    assert response.raw_state["status"] == "failed"
    assert response.raw_state["error_type"] == "worker_exception"
    assert runtime.state.signal_status == SignalStatus.DEGRADED
    assert storage.saved == [(make_request(), response)]


def make_request_dict() -> dict:
    """Create JSON request fixture."""
    return {
        "run_id": "run-1",
        "vt_symbol": "600519.SSE",
        "trade_date": "2024-01-03",
        "mode": "report_only",
        "context": {"market": {"bars": []}},
    }


def make_request() -> TradingAgentsWorkerRequest:
    """Create request fixture."""
    return TradingAgentsWorkerRequest(**make_request_dict())


class EchoWorker:
    """Worker fake used by JSON process helper."""

    def run(self, request: TradingAgentsWorkerRequest) -> TradingAgentsWorkerResponse:
        return TradingAgentsWorkerResponse(
            run_id=request.run_id,
            vt_symbol=request.vt_symbol,
            rating="Buy",
            confidence=0.8,
            report="ok",
            raw_state={"status": "ok"},
            action="buy",
        )


class RaisingWorker:
    """Worker fake that crashes."""

    def run(self, request: TradingAgentsWorkerRequest) -> TradingAgentsWorkerResponse:
        raise RuntimeError("worker crashed")


class RecordingStorage:
    """Storage fake recording saved worker responses."""

    def __init__(self) -> None:
        self.saved: list[tuple[TradingAgentsWorkerRequest, TradingAgentsWorkerResponse]] = []

    def save_worker_result(
        self,
        request: TradingAgentsWorkerRequest,
        response: TradingAgentsWorkerResponse,
    ) -> None:
        self.saved.append((request, response))
