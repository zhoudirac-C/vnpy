from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .output_validation import validate_worker_response
from .toolkit import MarketDataToolkit, SnapshotQuery, SnapshotReader
from .worker import TradingAgentsWorkerRequest, TradingAgentsWorkerResponse


@dataclass(frozen=True)
class RunnerSmokeConfig:
    """
    Smoke-run query for one symbol.
    """

    vt_symbol: str
    start: datetime
    end: datetime
    mode: str = "long_horizon_smoke"
    run_id: str = ""


@dataclass(frozen=True)
class RunnerSmokeResult:
    """
    Result of a TradingAgents runner smoke test.
    """

    success: bool
    request: TradingAgentsWorkerRequest | None = None
    response: TradingAgentsWorkerResponse | None = None
    error_type: str = ""
    error_message: str = ""


class Worker(Protocol):
    """
    Worker protocol for smoke runs.
    """

    def run(self, request: TradingAgentsWorkerRequest) -> TradingAgentsWorkerResponse:
        pass


class Storage(Protocol):
    """
    Storage protocol for smoke-run persistence.
    """

    def save_worker_result(
        self,
        request: TradingAgentsWorkerRequest,
        response: TradingAgentsWorkerResponse,
    ) -> None:
        pass


class TradingAgentsRunnerSmoke:
    """
    Build a PostgreSQL snapshot context and run one TradingAgents worker smoke test.
    """

    def __init__(
        self,
        reader: SnapshotReader,
        worker: Worker,
        storage: Storage,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """"""
        self.reader: SnapshotReader = reader
        self.worker: Worker = worker
        self.storage: Storage = storage
        self.clock: Callable[[], datetime] = clock or datetime.now

    def run(self, config: RunnerSmokeConfig) -> RunnerSmokeResult:
        """
        Execute one smoke run and persist only successful structured output.
        """
        request: TradingAgentsWorkerRequest = self._build_request(config)
        try:
            response = validate_worker_response(self.worker.run(request))
            self.storage.save_worker_result(request, response)
        except Exception as exc:
            return RunnerSmokeResult(
                success=False,
                request=request,
                error_type="worker_error",
                error_message=str(exc),
            )

        return RunnerSmokeResult(
            success=True,
            request=request,
            response=response,
        )

    def _build_request(self, config: RunnerSmokeConfig) -> TradingAgentsWorkerRequest:
        """
        Build one smoke-run worker request.
        """
        context = MarketDataToolkit(self.reader).build_context(
            SnapshotQuery(
                vt_symbol=config.vt_symbol,
                start=config.start,
                end=config.end,
            )
        )
        run_id: str = config.run_id or f"smoke-{config.end.date().isoformat()}-{config.vt_symbol}"
        return TradingAgentsWorkerRequest(
            run_id=run_id,
            vt_symbol=config.vt_symbol,
            trade_date=config.end.date().isoformat(),
            mode=config.mode,
            context=context,
        )
