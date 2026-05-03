from dataclasses import dataclass
from enum import Enum

from .runtime import TradingAgentsMode, TradingAgentsRuntimeController


class GatewayAccountMode(Enum):
    """
    Account mode used to gate AI signal consumption.
    """

    BACKTEST = "backtest"
    SIMULATION = "simulation"
    LIVE = "live"


@dataclass(frozen=True)
class GatewayProfile:
    """
    Minimal gateway profile used before enabling TradingAgents signals.
    """

    gateway_name: str
    account_mode: GatewayAccountMode


class GatewayAiPolicy:
    """
    Apply frontend and gateway-mode constraints to TradingAgents runtime.
    """

    def __init__(self, allow_live_ai: bool = False) -> None:
        """"""
        self.allow_live_ai: bool = allow_live_ai

    def apply(
        self,
        runtime: TradingAgentsRuntimeController,
        profile: GatewayProfile,
        ai_enabled: bool,
    ) -> None:
        """
        Configure runtime for a backtest, simulation or live gateway profile.
        """
        if not ai_enabled:
            runtime.disable("front_switch_off")
            return

        if profile.account_mode in {GatewayAccountMode.BACKTEST, GatewayAccountMode.SIMULATION}:
            runtime.enable(mode=TradingAgentsMode.PAPER_ONLY)
            return

        if profile.account_mode == GatewayAccountMode.LIVE and self.allow_live_ai:
            runtime.enable(mode=TradingAgentsMode.LIVE_ALLOWED, live_enabled=True)
            return

        runtime.disable("ai_not_allowed_for_gateway")
