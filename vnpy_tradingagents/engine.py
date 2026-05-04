from vnpy.event import EventEngine
from vnpy.trader.engine import BaseEngine, MainEngine

from .runtime import (
    TradingAgentsMode,
    TradingAgentsRuntimeController,
    TradingAgentsRuntimeState,
)


class RuntimeStateStorage:
    """
    Storage protocol for persisted TradingAgents runtime state.
    """

    def save_state(self, state: TradingAgentsRuntimeState) -> None:
        pass

    def load_state(self) -> TradingAgentsRuntimeState | None:
        pass


class TradingAgentsEngine(BaseEngine):
    """
    Runtime control engine for TradingAgents integration.
    """

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine) -> None:
        """"""
        super().__init__(main_engine, event_engine, "TradingAgents")
        self.runtime: TradingAgentsRuntimeController = TradingAgentsRuntimeController()
        self.state_storage: RuntimeStateStorage | None = None

    def set_state_storage(self, storage: RuntimeStateStorage) -> None:
        """
        Attach persistent runtime storage and restore prior state when available.
        """
        self.state_storage = storage
        restored = storage.load_state()
        if restored is not None:
            self.runtime.state = restored

    def enable(
        self,
        mode: TradingAgentsMode = TradingAgentsMode.REPORT_ONLY,
        live_enabled: bool = False,
    ) -> None:
        """
        Enable TradingAgents runtime.
        """
        self.runtime.enable(mode, live_enabled)
        self._persist_state()

    def disable(self, reason: str = "") -> None:
        """
        Disable TradingAgents runtime.
        """
        self.runtime.disable(reason)
        self._persist_state()

    def pause_manual_takeover(self, reason: str = "manual_takeover") -> None:
        """
        Pause AI usage for operator takeover.
        """
        self.runtime.pause_manual_takeover(reason)
        self._persist_state()

    def get_state(self) -> TradingAgentsRuntimeState:
        """
        Return current runtime state.
        """
        return self.runtime.state

    def _persist_state(self) -> None:
        """
        Persist runtime state when storage is configured.
        """
        if self.state_storage:
            self.state_storage.save_state(self.runtime.state)
