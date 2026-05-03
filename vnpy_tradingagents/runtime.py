from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class TradingAgentsMode(Enum):
    """
    Runtime mode for TradingAgents integration.
    """

    REPORT_ONLY = "report_only"
    PAPER_ONLY = "paper_only"
    LIVE_ALLOWED = "live_allowed"


class SignalStatus(Enum):
    """
    Runtime availability of AI signals.
    """

    ACTIVE = "active"
    DISABLED = "disabled"
    EXPIRED = "expired"
    DEGRADED = "degraded"


@dataclass
class TradingAgentsRuntimeState:
    """
    Current switch state for TradingAgents.
    """

    enabled: bool = False
    live_enabled: bool = False
    mode: TradingAgentsMode = TradingAgentsMode.REPORT_ONLY
    disabled_reason: str = ""
    last_heartbeat_at: datetime | None = None
    last_successful_run_id: str = ""
    signal_status: SignalStatus = SignalStatus.DISABLED


class TradingAgentsRuntimeController:
    """
    State controller used by UI, strategies and workers.
    """

    def __init__(self, state: TradingAgentsRuntimeState | None = None) -> None:
        """"""
        self.state: TradingAgentsRuntimeState = state or TradingAgentsRuntimeState()

    def enable(
        self,
        mode: TradingAgentsMode = TradingAgentsMode.REPORT_ONLY,
        live_enabled: bool = False,
    ) -> None:
        """
        Enable TradingAgents in the requested mode.
        """
        self.state.enabled = True
        self.state.mode = mode
        self.state.live_enabled = bool(live_enabled and mode == TradingAgentsMode.LIVE_ALLOWED)
        self.state.disabled_reason = ""
        self.state.signal_status = SignalStatus.ACTIVE

    def disable(self, reason: str = "") -> None:
        """
        Disable TradingAgents and block all AI signals.
        """
        self.state.enabled = False
        self.state.live_enabled = False
        self.state.disabled_reason = reason
        self.state.signal_status = SignalStatus.DISABLED

    def heartbeat(self, at: datetime | None = None) -> None:
        """
        Record worker heartbeat.
        """
        self.state.last_heartbeat_at = at or datetime.now()

    def mark_success(self, run_id: str) -> None:
        """
        Record the last successful TradingAgents run id.
        """
        self.state.last_successful_run_id = run_id

    def can_generate_report(self) -> bool:
        """
        Return whether the worker can generate reports.
        """
        return self.state.enabled

    def can_use_signal(self, live: bool) -> bool:
        """
        Return whether strategies may consume AI signals.
        """
        if not self.state.enabled:
            return False

        if self.state.signal_status != SignalStatus.ACTIVE:
            return False

        if live:
            return self.state.mode == TradingAgentsMode.LIVE_ALLOWED and self.state.live_enabled

        return self.state.mode in {
            TradingAgentsMode.REPORT_ONLY,
            TradingAgentsMode.PAPER_ONLY,
            TradingAgentsMode.LIVE_ALLOWED,
        }
