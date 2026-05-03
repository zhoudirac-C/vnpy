from vnpy.event import EventEngine
from vnpy.trader.engine import BaseEngine, MainEngine

from .runtime import (
    TradingAgentsMode,
    TradingAgentsRuntimeController,
    TradingAgentsRuntimeState,
)


class TradingAgentsEngine(BaseEngine):
    """
    Runtime control engine for TradingAgents integration.
    """

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine) -> None:
        """"""
        super().__init__(main_engine, event_engine, "TradingAgents")
        self.runtime: TradingAgentsRuntimeController = TradingAgentsRuntimeController()

    def enable(
        self,
        mode: TradingAgentsMode = TradingAgentsMode.REPORT_ONLY,
        live_enabled: bool = False,
    ) -> None:
        """
        Enable TradingAgents runtime.
        """
        self.runtime.enable(mode, live_enabled)

    def disable(self, reason: str = "") -> None:
        """
        Disable TradingAgents runtime.
        """
        self.runtime.disable(reason)

    def get_state(self) -> TradingAgentsRuntimeState:
        """
        Return current runtime state.
        """
        return self.runtime.state
