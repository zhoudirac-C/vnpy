from __future__ import annotations

from datetime import datetime, timedelta

from vnpy.event import EventEngine

from vnpy_seven_boll.scanner import SevenBollScanRequest, SevenBollScanResult, SevenBollScanSummary


def test_engine_runs_seven_boll_scan_without_tradingagents_service() -> None:
    from vnpy_tradingagents.engine import TradingAgentsEngine

    engine = TradingAgentsEngine(None, EventEngine())  # type: ignore[arg-type]
    service = FakeScanService(_summary())
    repository = FakeScanRepository()
    engine.set_seven_boll_scan_service(service)
    engine.set_seven_boll_scan_repository(repository)

    summary = engine.run_seven_boll_scan(SevenBollScanRequest(symbols=("600519.SSE",)))

    assert summary.run_id == "scan-1"
    assert service.requests[0].interval.value == "d"
    assert repository.saved == [summary]


def test_engine_forwards_seven_boll_scan_progress_and_cancel_callbacks() -> None:
    from vnpy_tradingagents.engine import TradingAgentsEngine

    engine = TradingAgentsEngine(None, EventEngine())  # type: ignore[arg-type]
    service = FakeScanService(_summary())
    engine.set_seven_boll_scan_service(service)

    progress_callback = object()
    cancel_requested = object()
    summary = engine.run_seven_boll_scan(
        SevenBollScanRequest(symbols=("600519.SSE",)),
        progress_callback=progress_callback,
        cancel_requested=cancel_requested,
    )

    assert summary.run_id == "scan-1"
    assert service.progress_callback is progress_callback
    assert service.cancel_requested is cancel_requested


def test_engine_loads_latest_and_history_from_seven_boll_repository() -> None:
    from vnpy_tradingagents.engine import TradingAgentsEngine

    engine = TradingAgentsEngine(None, EventEngine())  # type: ignore[arg-type]
    repository = FakeScanRepository()
    repository.saved = [_summary("scan-1"), _summary("scan-2")]
    engine.set_seven_boll_scan_repository(repository)

    assert engine.load_latest_seven_boll_scan().run_id == "scan-2"
    assert [summary.run_id for summary in engine.list_seven_boll_scan_history()] == ["scan-2", "scan-1"]


def test_engine_runs_single_scan_analysis_with_seven_boll_context() -> None:
    from vnpy_tradingagents.engine import TradingAgentsEngine

    engine = TradingAgentsEngine(None, EventEngine())  # type: ignore[arg-type]
    engine.set_seven_boll_scan_repository(FakeScanRepository([_summary()]))
    service = FakeManualAnalysisService()
    engine.set_manual_analysis_service(service)

    run_id = engine.run_scan_analysis("600519.SSE")

    assert run_id == "analysis-600519.SSE"
    request = service.requests[0]
    assert request.mode == "seven_boll_scan_analysis"
    assert request.context_overrides["seven_boll_scan"]["vt_symbol"] == "600519.SSE"
    assert request.context_overrides["seven_boll_scan"]["interval"] == "d"


def test_engine_runs_batch_scan_analysis() -> None:
    from vnpy_tradingagents.engine import TradingAgentsEngine

    engine = TradingAgentsEngine(None, EventEngine())  # type: ignore[arg-type]
    engine.set_seven_boll_scan_repository(FakeScanRepository([_summary()]))
    service = FakeManualAnalysisService()
    engine.set_manual_analysis_service(service)

    run_ids = engine.run_batch_scan_analysis(["600519.SSE", "000001.SZSE"])

    assert run_ids == ["analysis-600519.SSE"]


def _summary(run_id: str = "scan-1") -> SevenBollScanSummary:
    started_at = datetime(2024, 1, 2, 15, 5)
    result = SevenBollScanResult(
        vt_symbol="600519.SSE",
        name="贵州茅台",
        action="buy_watch",
        score=80,
        buy_score=80,
        sell_score=0,
        signal_types=("trend_pullback_long",),
        reasons=("test_reason",),
        risks=("test_risk",),
        close=100,
        zscore=1,
        bandwidth_percentile=20,
        mid_slope=1,
        rail_zone="upper2_to_upper1",
        regime="trend_up",
        bar_datetime=started_at,
        interval="d",
    )
    return SevenBollScanSummary(
        run_id=run_id,
        started_at=started_at,
        finished_at=started_at + timedelta(seconds=2),
        status="completed",
        total_symbols=1,
        scanned_symbols=1,
        skipped_symbols=0,
        buy_candidates=[result],
        sell_candidates=[],
        errors=[],
    )


class FakeScanService:
    def __init__(self, summary: SevenBollScanSummary) -> None:
        self.summary = summary
        self.requests = []
        self.latest_summary = None
        self.progress_callback = None
        self.cancel_requested = None

    def scan(self, request, progress_callback=None, cancel_requested=None):
        self.requests.append(request)
        self.progress_callback = progress_callback
        self.cancel_requested = cancel_requested
        self.latest_summary = self.summary
        return self.summary


class FakeScanRepository:
    def __init__(self, saved: list[SevenBollScanSummary] | None = None) -> None:
        self.saved = saved or []

    def save_scan_summary(self, summary, scan_type="manual") -> None:
        self.saved.append(summary)

    def load_latest_summary(self):
        return self.saved[-1] if self.saved else None

    def list_scan_runs(self, limit=50):
        return list(reversed(self.saved[-limit:]))


class FakeManualAnalysisService:
    def __init__(self) -> None:
        self.requests = []

    def run(self, request):
        self.requests.append(request)
        return FakeManualAnalysisResult(f"analysis-{request.vt_symbol}", request)


class FakeManualAnalysisResult:
    def __init__(self, run_id: str, request) -> None:
        self.status = "completed"
        self.request = request
        self.response = FakeResponse(run_id)


class FakeResponse:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
