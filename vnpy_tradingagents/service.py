from typing import Protocol

from .runtime import TradingAgentsRuntimeController
from .worker import TradingAgentsWorkerRequest, TradingAgentsWorkerResponse


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

        response: TradingAgentsWorkerResponse = self.worker.run(request)
        self.storage.save_worker_result(request, response)
        self.runtime.mark_success(response.run_id)
        return response
