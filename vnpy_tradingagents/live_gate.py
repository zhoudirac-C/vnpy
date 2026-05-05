from dataclasses import dataclass

from .runtime import TradingAgentsRuntimeController


@dataclass(frozen=True)
class LiveGateConfig:
    """
    Minimum requirements before allowing live AI signal use.
    """

    min_stable_days: int
    max_drawdown: float
    min_audit_completeness: float
    max_failure_rate: float | None = None
    require_manual_takeover: bool = False


@dataclass(frozen=True)
class LiveGateMetrics:
    """
    Latest paper/small-capital health metrics.
    """

    simulation_stable_days: int
    max_drawdown: float
    audit_completeness: float
    failure_rate: float = 0
    manual_takeover_ready: bool = True


@dataclass(frozen=True)
class LiveGateResult:
    """
    Live gate decision.
    """

    allowed: bool
    reason: str


class LiveGate:
    """
    Decide whether TradingAgents may enter live_allowed mode.
    """

    def __init__(self, config: LiveGateConfig) -> None:
        """"""
        self.config: LiveGateConfig = config

    def evaluate(
        self,
        runtime: TradingAgentsRuntimeController,
        metrics: LiveGateMetrics,
    ) -> LiveGateResult:
        """
        Evaluate live-entry requirements.
        """
        if not runtime.can_use_signal(live=True):
            return LiveGateResult(False, "live_ai_not_enabled")

        if metrics.simulation_stable_days < self.config.min_stable_days:
            return LiveGateResult(False, "insufficient_simulation_stable_days")

        if metrics.max_drawdown > self.config.max_drawdown:
            return LiveGateResult(False, "max_drawdown_exceeded")

        if metrics.audit_completeness < self.config.min_audit_completeness:
            return LiveGateResult(False, "audit_incomplete")

        if (
            self.config.max_failure_rate is not None
            and metrics.failure_rate > self.config.max_failure_rate
        ):
            return LiveGateResult(False, "failure_rate_exceeded")

        if self.config.require_manual_takeover and not metrics.manual_takeover_ready:
            return LiveGateResult(False, "manual_takeover_not_ready")

        return LiveGateResult(True, "ready")
