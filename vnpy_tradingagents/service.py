from typing import Protocol

from .runtime import TradingAgentsRuntimeController
from .worker import TradingAgentsWorkerRequest, TradingAgentsWorkerResponse
from .worker_adapter import failed_worker_response


class Worker(Protocol):
    """
    Worker client protocol.
    """

    def run(self, request: TradingAgentsWorkerRequest) -> TradingAgentsWorkerResponse:
        pass


class AgentStorage(Protocol):
    """
    Storage protocol for TradingAgents outputs.
    """

    def save_worker_result(
        self,
        request: TradingAgentsWorkerRequest,
        response: TradingAgentsWorkerResponse,
    ) -> None:
        pass


class TradingAgentsService:
    """
    Runtime-guarded service for invoking TradingAgents workers.
    """

    def __init__(
        self,
        runtime: TradingAgentsRuntimeController,
        worker: Worker,
        storage: AgentStorage,
    ) -> None:
        """"""
        self.runtime: TradingAgentsRuntimeController = runtime
        self.worker: Worker = worker
        self.storage: AgentStorage = storage

    def run(self, request: TradingAgentsWorkerRequest) -> TradingAgentsWorkerResponse | None:
        """
        Run TradingAgents only when the global switch allows it.
        """
        if not self.runtime.can_generate_report():
            return None

        try:
            response: TradingAgentsWorkerResponse = self.worker.run(request)
        except Exception as exc:
            response = failed_worker_response(request, "worker_exception", str(exc))

        self.storage.save_worker_result(request, response)
        if response.raw_state.get("status") == "failed":
            self.runtime.mark_degraded(response.raw_state.get("error_message", ""))
        else:
            self.runtime.mark_success(response.run_id)
        return response
