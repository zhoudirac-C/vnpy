from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from uuid import uuid4

from .runtime import TradingAgentsRuntimeController
from .service import AgentStorage, Worker
from .toolkit import SnapshotQuery
from .worker import TradingAgentsWorkerRequest, TradingAgentsWorkerResponse
from .worker_adapter import failed_worker_response


class ContextToolkit(Protocol):
    """
    Read-only context builder used by manual analysis.
    """

    def build_context(self, query: SnapshotQuery) -> dict[str, Any]:
        pass


@dataclass(frozen=True)
class ManualAnalysisRequest:
    """
    User-triggered TradingAgents analysis request.
    """

    vt_symbol: str
    start: datetime
    end: datetime
    mode: str = "manual_analysis"
    context_overrides: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ManualAnalysisResult:
    """
    Result rendered by the TradingAgents UI manual-analysis panel.
    """

    status: str
    request: TradingAgentsWorkerRequest | None
    response: TradingAgentsWorkerResponse | None
    error_message: str = ""


class TradingAgentsManualAnalysisService:
    """
    Build a context-only request for an operator-triggered TradingAgents analysis.
    """

    def __init__(
        self,
        runtime: TradingAgentsRuntimeController,
        toolkit: ContextToolkit,
        worker: Worker,
        storage: AgentStorage,
        run_id_factory: Callable[[ManualAnalysisRequest], str] | None = None,
    ) -> None:
        self.runtime: TradingAgentsRuntimeController = runtime
        self.toolkit: ContextToolkit = toolkit
        self.worker: Worker = worker
        self.storage: AgentStorage = storage
        self.run_id_factory: Callable[[ManualAnalysisRequest], str] = (
            run_id_factory or _manual_run_id
        )

    def run(self, request: ManualAnalysisRequest) -> ManualAnalysisResult:
        """
        Run a report-only TradingAgents analysis when the global AI switch allows it.
        """
        if not self.runtime.can_generate_report():
            return ManualAnalysisResult(
                status="disabled",
                request=None,
                response=None,
                error_message=self.runtime.state.disabled_reason or "tradingagents_disabled",
            )

        worker_request = self._build_worker_request(request)
        try:
            response = self.worker.run(worker_request)
        except Exception as exc:
            response = failed_worker_response(worker_request, "worker_exception", str(exc))

        self.storage.save_worker_result(worker_request, response)
        if str(response.raw_state.get("status", "")).lower() == "failed":
            self.runtime.mark_degraded(response.raw_state.get("error_message", ""))
            status = "failed"
        else:
            self.runtime.mark_success(response.run_id)
            status = "completed"

        return ManualAnalysisResult(
            status=status,
            request=worker_request,
            response=response,
            error_message=str(response.raw_state.get("error_message", "")),
        )

    def _build_worker_request(
        self,
        request: ManualAnalysisRequest,
    ) -> TradingAgentsWorkerRequest:
        """
        Build the context-only worker request from MarketDataToolkit output.
        """
        context = dict(
            self.toolkit.build_context(
                SnapshotQuery(
                    vt_symbol=request.vt_symbol,
                    start=request.start,
                    end=request.end,
                )
            )
        )
        context.update(request.context_overrides)
        if "seven_boll_scan" in context:
            context["seven_boll_analysis_guidance"] = (
                "七轨布林线扫描结果只能作为日线技术面证据，不能当作唯一买卖依据。"
                "如果基本面、新闻、财报与七轨技术信号冲突，必须明确写出冲突。"
                "报告定位为波段/明日观察计划，不输出日内分时交易建议。"
            )
        context["manual_analysis"] = {
            "entrypoint": "TradingAgentsApp",
            "vt_symbol": request.vt_symbol,
            "start": request.start.isoformat(),
            "end": request.end.isoformat(),
        }
        return TradingAgentsWorkerRequest(
            run_id=self.run_id_factory(request),
            vt_symbol=request.vt_symbol,
            trade_date=request.end.date().isoformat(),
            mode=request.mode,
            context=context,
        )


def _manual_run_id(_: ManualAnalysisRequest) -> str:
    """
    Generate a stable-prefix run id for manual analysis.
    """
    return f"manual-{uuid4().hex}"
