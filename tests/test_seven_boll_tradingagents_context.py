from __future__ import annotations

from datetime import datetime

from vnpy_tradingagents.runtime import TradingAgentsMode, TradingAgentsRuntimeController
from vnpy_tradingagents.worker import TradingAgentsWorkerResponse


def test_manual_analysis_injects_seven_boll_scan_guidance() -> None:
    from vnpy_tradingagents.manual_analysis import ManualAnalysisRequest, TradingAgentsManualAnalysisService

    runtime = TradingAgentsRuntimeController()
    runtime.enable(mode=TradingAgentsMode.REPORT_ONLY)
    worker = FakeWorker()
    service = TradingAgentsManualAnalysisService(
        runtime=runtime,
        toolkit=FakeToolkit(),
        worker=worker,
        storage=FakeStorage(),
        run_id_factory=lambda _: "seven-boll-analysis-1",
    )

    service.run(
        ManualAnalysisRequest(
            vt_symbol="600519.SSE",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 3),
            mode="seven_boll_scan_analysis",
            context_overrides={
                "seven_boll_scan": {
                    "vt_symbol": "600519.SSE",
                    "interval": "d",
                    "signals": ["trend_pullback_long"],
                    "action": "buy_watch",
                }
            },
        )
    )

    context = worker.requests[0].context
    assert context["seven_boll_scan"]["interval"] == "d"
    guidance = context["seven_boll_analysis_guidance"]
    assert "日线技术面证据" in guidance
    assert "不能当作唯一买卖依据" in guidance
    assert "不输出日内分时交易建议" in guidance


class FakeToolkit:
    def build_context(self, query):
        return {"market": {"bars": []}}


class FakeWorker:
    def __init__(self) -> None:
        self.requests = []

    def run(self, request):
        self.requests.append(request)
        return TradingAgentsWorkerResponse(
            run_id=request.run_id,
            vt_symbol=request.vt_symbol,
            rating="Neutral",
            confidence=0.5,
            report="report",
            raw_state={"status": "completed"},
            action="hold",
            target_weight_hint=None,
            holding_period_hint="20d",
            risk_notes="risk",
        )


class FakeStorage:
    def save_worker_result(self, request, response) -> None:
        pass
