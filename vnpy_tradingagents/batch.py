from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from .research import AgentStorage, ResearchSnapshot, Worker
from .runtime import TradingAgentsRuntimeController
from .signals import PortfolioIntent, RatingSignal
from .worker import TradingAgentsWorkerRequest, TradingAgentsWorkerResponse


@dataclass(frozen=True)
class BatchRunSummary:
    """
    Summary for one long-horizon stock-pool run.
    """

    batch_run_id: str
    trade_date: str
    total: int
    succeeded: int
    failed: int
    ratings: list[RatingSignal]
    intents: list[PortfolioIntent]
    failures: dict[str, str]


class ResearchSnapshotReader(Protocol):
    """
    Read long-horizon snapshots for a symbol and trade date.
    """

    def load_snapshot(self, vt_symbol: str, trade_date: str) -> ResearchSnapshot:
        pass


class BatchLongHorizonAgentJob:
    """
    Run long-horizon TradingAgents jobs over a stock pool.
    """

    def __init__(
        self,
        runtime: TradingAgentsRuntimeController,
        worker: Worker,
        storage: AgentStorage,
        snapshot_reader: ResearchSnapshotReader,
        batch_id_factory=None,
    ) -> None:
        """"""
        self.runtime: TradingAgentsRuntimeController = runtime
        self.worker: Worker = worker
        self.storage: AgentStorage = storage
        self.snapshot_reader: ResearchSnapshotReader = snapshot_reader
        self.batch_id_factory = batch_id_factory or _batch_run_id

    def run(
        self,
        symbols: list[str],
        trade_date: str,
        batch_run_id: str | None = None,
    ) -> BatchRunSummary:
        """
        Run a stock pool; one symbol failure does not stop the rest.
        """
        run_id: str = batch_run_id or self.batch_id_factory()
        ratings: list[RatingSignal] = []
        intents: list[PortfolioIntent] = []
        failures: dict[str, str] = {}

        if not self.runtime.can_generate_report():
            return BatchRunSummary(
                batch_run_id=run_id,
                trade_date=trade_date,
                total=len(symbols),
                succeeded=0,
                failed=0,
                ratings=[],
                intents=[],
                failures={},
            )

        for vt_symbol in symbols:
            try:
                snapshot: ResearchSnapshot = self.snapshot_reader.load_snapshot(vt_symbol, trade_date)
                request: TradingAgentsWorkerRequest = self._build_request(
                    batch_run_id=run_id,
                    snapshot=snapshot,
                )
                response: TradingAgentsWorkerResponse = self.worker.run(request)
                self.storage.save_worker_result(request, response)
            except Exception as exc:
                failures[vt_symbol] = str(exc)
                continue

            ratings.append(_rating_from_response(response))
            intents.append(_intent_from_response(trade_date, response))
            self.runtime.mark_success(response.run_id)

        return BatchRunSummary(
            batch_run_id=run_id,
            trade_date=trade_date,
            total=len(symbols),
            succeeded=len(ratings),
            failed=len(failures),
            ratings=ratings,
            intents=intents,
            failures=failures,
        )

    def _build_request(
        self,
        batch_run_id: str,
        snapshot: ResearchSnapshot,
    ) -> TradingAgentsWorkerRequest:
        """
        Build a traceable worker request for one symbol.
        """
        context = dict(snapshot.to_context())
        context["batch"] = {
            "batch_run_id": batch_run_id,
            "symbol_count_scope": "stock_pool",
        }
        return TradingAgentsWorkerRequest(
            run_id=f"{batch_run_id}:{snapshot.trade_date}:{snapshot.vt_symbol}",
            vt_symbol=snapshot.vt_symbol,
            trade_date=snapshot.trade_date,
            mode="long_horizon_batch",
            context=context,
        )


def _rating_from_response(response: TradingAgentsWorkerResponse) -> RatingSignal:
    """"""
    return RatingSignal(
        vt_symbol=response.vt_symbol,
        rating=response.rating,
        confidence=response.confidence,
        source_run_id=response.run_id,
    )


def _intent_from_response(
    trade_date: str,
    response: TradingAgentsWorkerResponse,
) -> PortfolioIntent:
    """"""
    return PortfolioIntent(
        vt_symbol=response.vt_symbol,
        trade_date=trade_date,
        action=response.action,
        target_weight_hint=response.target_weight_hint,
        holding_period_hint=response.holding_period_hint,
        risk_notes=response.risk_notes,
        source_run_id=response.run_id,
    )


def _batch_run_id() -> str:
    """"""
    return f"batch-{uuid4().hex}"
