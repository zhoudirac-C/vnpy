from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from uuid import uuid4

from .risk import DecisionAuditStorage, PreOrderDecisionService, RiskRuleSet
from .runtime import TradingAgentsRuntimeController
from .service import AgentStorage, Worker
from .strategies import (
    AiStrategyDecisionContext,
    TradeIntentReader,
    TradingAgentsStrategyDecision,
    evaluate_ai_trade_intent,
)
from .toolkit import SnapshotQuery
from .worker import TradingAgentsWorkerRequest
from .worker_adapter import failed_worker_response


class ContextToolkit(Protocol):
    """
    Read-only toolkit for historical point-in-time context generation.
    """

    def build_context(self, query: SnapshotQuery) -> dict[str, Any]:
        pass


@dataclass(frozen=True)
class HistoricalAiSignalRequest:
    """
    One point-in-time AI signal generation request for future backtests.
    """

    vt_symbol: str
    trade_time: datetime
    start: datetime
    end: datetime
    mode: str = "backtest_signal"
    context_overrides: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HistoricalAiSignalSummary:
    """
    Batch summary for historical AI signal generation.
    """

    total: int
    succeeded: int
    failed: int
    skipped: int
    run_ids: list[str]
    errors: list[str]


@dataclass(frozen=True)
class AiBacktestDecisionContext:
    """
    Backtest decision point for reading one stored historical AI signal.
    """

    vt_symbol: str
    trade_time: datetime
    price: float
    volume: float
    current_position: float = 0
    daily_traded_value: float = 0
    drawdown: float = 0
    cancel_count: int = 0
    limit_up: float | None = None
    limit_down: float | None = None


class HistoricalAiSignalJob:
    """
    Generate and persist AI signals before a backtest consumes them.
    """

    def __init__(
        self,
        runtime: TradingAgentsRuntimeController,
        toolkit: ContextToolkit,
        worker: Worker,
        storage: AgentStorage,
        run_id_factory: Callable[[HistoricalAiSignalRequest], str] | None = None,
    ) -> None:
        self.runtime: TradingAgentsRuntimeController = runtime
        self.toolkit: ContextToolkit = toolkit
        self.worker: Worker = worker
        self.storage: AgentStorage = storage
        self.run_id_factory: Callable[[HistoricalAiSignalRequest], str] = (
            run_id_factory or _historical_run_id
        )

    def run(
        self,
        requests: Iterable[HistoricalAiSignalRequest],
    ) -> HistoricalAiSignalSummary:
        """
        Generate signals for all requests, isolating per-symbol failures.
        """
        request_list = list(requests)
        if not self.runtime.can_generate_report():
            return HistoricalAiSignalSummary(
                total=len(request_list),
                succeeded=0,
                failed=0,
                skipped=len(request_list),
                run_ids=[],
                errors=[],
            )

        succeeded = 0
        failed = 0
        run_ids: list[str] = []
        errors: list[str] = []
        for request in request_list:
            worker_request = self._build_worker_request(request)
            try:
                response = self.worker.run(worker_request)
            except Exception as exc:
                response = failed_worker_response(worker_request, "worker_exception", str(exc))

            self.storage.save_worker_result(worker_request, response)
            run_ids.append(response.run_id)
            if str(response.raw_state.get("status", "")).lower() == "failed":
                failed += 1
                errors.append(str(response.raw_state.get("error_message", "")))
            else:
                succeeded += 1
                self.runtime.mark_success(response.run_id)

        return HistoricalAiSignalSummary(
            total=len(request_list),
            succeeded=succeeded,
            failed=failed,
            skipped=0,
            run_ids=run_ids,
            errors=errors,
        )

    def _build_worker_request(
        self,
        request: HistoricalAiSignalRequest,
    ) -> TradingAgentsWorkerRequest:
        """
        Build a point-in-time context for one historical signal generation run.
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
        context["point_in_time"] = {
            "vt_symbol": request.vt_symbol,
            "trade_time": request.trade_time.isoformat(),
            "start": request.start.isoformat(),
            "end": request.end.isoformat(),
        }
        return TradingAgentsWorkerRequest(
            run_id=self.run_id_factory(request),
            vt_symbol=request.vt_symbol,
            trade_date=request.trade_time.date().isoformat(),
            mode=request.mode,
            context=context,
        )


class TradingAgentsBacktestStrategy:
    """
    Deterministic backtest strategy that reads pre-generated AI signals only.
    """

    def __init__(
        self,
        signal_reader: TradeIntentReader,
        rules: RiskRuleSet,
        audit_storage: DecisionAuditStorage,
        decision_id_factory: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.signal_reader: TradeIntentReader = signal_reader
        self.decision_service: PreOrderDecisionService = PreOrderDecisionService(
            rules=rules,
            audit_storage=audit_storage,
            decision_id_factory=decision_id_factory,
            clock=clock,
        )

    def evaluate(
        self,
        context: AiBacktestDecisionContext,
    ) -> TradingAgentsStrategyDecision:
        """
        Read the latest historical AI signal at the backtest time and audit it.
        """
        trade_intent = self.signal_reader.load_latest_trade_intent(
            context.vt_symbol,
            context.trade_time.date().isoformat(),
        )
        return evaluate_ai_trade_intent(
            trade_intent=trade_intent,
            context=AiStrategyDecisionContext(
                vt_symbol=context.vt_symbol,
                trade_time=context.trade_time,
                price=context.price,
                volume=context.volume,
                live=False,
                current_position=context.current_position,
                daily_traded_value=context.daily_traded_value,
                drawdown=context.drawdown,
                cancel_count=context.cancel_count,
                limit_up=context.limit_up,
                limit_down=context.limit_down,
            ),
            decision_service=self.decision_service,
        )


def _historical_run_id(request: HistoricalAiSignalRequest) -> str:
    """
    Generate a stable-prefix historical AI signal run id.
    """
    return f"hist-{request.trade_time.date().isoformat()}-{uuid4().hex}"
