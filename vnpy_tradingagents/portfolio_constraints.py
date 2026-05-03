from dataclasses import dataclass

from .signals import PortfolioIntent


BUY_ACTIONS: frozenset[str] = frozenset(
    {
        "buy",
        "buy_on_pullback",
        "add",
        "increase",
        "open_long",
    }
)


@dataclass(frozen=True)
class PortfolioConstraintConfig:
    """
    Deterministic portfolio constraints for long-horizon intents.
    """

    max_single_weight: float | None = None
    max_sector_weight: float | None = None
    max_turnover_rate: float | None = None
    min_cash_weight: float | None = None
    max_drawdown: float | None = None


@dataclass(frozen=True)
class PortfolioState:
    """
    Current portfolio weights and risk state.
    """

    current_weights: dict[str, float]
    sector_weights: dict[str, float]
    symbol_sectors: dict[str, str]
    cash_weight: float
    turnover_rate: float
    drawdown: float


@dataclass(frozen=True)
class PortfolioConstraintViolation:
    """
    One blocked portfolio intent and its failed rule.
    """

    vt_symbol: str
    rule: str
    reason: str


@dataclass(frozen=True)
class PortfolioConstraintResult:
    """
    Approved intents and constraint violations.
    """

    approved_intents: list[PortfolioIntent]
    violations: list[PortfolioConstraintViolation]


class PortfolioConstraintEngine:
    """
    Apply deterministic portfolio constraints before intent consumption.
    """

    def __init__(self, config: PortfolioConstraintConfig) -> None:
        """"""
        self.config: PortfolioConstraintConfig = config

    def apply(
        self,
        intents: list[PortfolioIntent],
        state: PortfolioState,
    ) -> PortfolioConstraintResult:
        """
        Return only intents whose target weights satisfy constraints.
        """
        approved: list[PortfolioIntent] = []
        violations: list[PortfolioConstraintViolation] = []

        for intent in intents:
            violation = self._evaluate_intent(intent, state)
            if violation is None:
                approved.append(intent)
            else:
                violations.append(violation)

        return PortfolioConstraintResult(approved_intents=approved, violations=violations)

    def _evaluate_intent(
        self,
        intent: PortfolioIntent,
        state: PortfolioState,
    ) -> PortfolioConstraintViolation | None:
        """
        Evaluate one intent. Constraint failures block buy-like intents.
        """
        if not _is_buy_action(intent.action):
            return None

        target_weight: float = float(intent.target_weight_hint or 0)
        current_weight: float = state.current_weights.get(intent.vt_symbol, 0)
        weight_delta: float = abs(target_weight - current_weight)
        buy_delta: float = max(target_weight - current_weight, 0)

        if self.config.max_drawdown is not None and state.drawdown > self.config.max_drawdown:
            return _violation(intent, "max_drawdown", "portfolio drawdown exceeds limit")

        if (
            self.config.max_single_weight is not None
            and target_weight > self.config.max_single_weight
        ):
            return _violation(intent, "max_single_weight", "single symbol target exceeds limit")

        sector: str = state.symbol_sectors.get(intent.vt_symbol, "")
        sector_weight: float = state.sector_weights.get(sector, 0)
        current_sector_symbol_weight: float = current_weight if sector else 0
        projected_sector_weight: float = sector_weight - current_sector_symbol_weight + target_weight
        if (
            sector
            and self.config.max_sector_weight is not None
            and projected_sector_weight > self.config.max_sector_weight
        ):
            return _violation(intent, "max_sector_weight", "sector exposure exceeds limit")

        projected_turnover: float = state.turnover_rate + weight_delta
        if (
            self.config.max_turnover_rate is not None
            and projected_turnover > self.config.max_turnover_rate
        ):
            return _violation(intent, "max_turnover_rate", "turnover exceeds limit")

        projected_cash: float = state.cash_weight - buy_delta
        if self.config.min_cash_weight is not None and projected_cash < self.config.min_cash_weight:
            return _violation(intent, "min_cash_weight", "cash reserve would fall below limit")

        return None


def _violation(
    intent: PortfolioIntent,
    rule: str,
    reason: str,
) -> PortfolioConstraintViolation:
    """"""
    return PortfolioConstraintViolation(
        vt_symbol=intent.vt_symbol,
        rule=rule,
        reason=reason,
    )


def _is_buy_action(action: str) -> bool:
    """"""
    return action.strip().lower() in BUY_ACTIONS
