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


@dataclass(frozen=True)
class LiveGateMetrics:
    """
    Latest paper/small-capital health metrics.
    """

    simulation_stable_days: int
    max_drawdown: float
    audit_completeness: float


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

        return LiveGateResult(True, "ready")
