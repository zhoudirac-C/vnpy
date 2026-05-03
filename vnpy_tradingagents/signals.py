from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class RatingSignal:
    """
    Long-horizon TradingAgents rating persisted from a worker run.
    """

    vt_symbol: str
    rating: str
    confidence: float
    source_run_id: str


@dataclass(frozen=True)
class IntradayAdvice:
    """
    Short-lived intraday advice generated from an intraday snapshot.
    """

    vt_symbol: str
    action: str
    confidence: float
    valid_until: datetime
    source_run_id: str


@dataclass(frozen=True)
class PortfolioIntent:
    """
    Long-horizon portfolio intent consumed by portfolio strategies.
    """

    vt_symbol: str
    trade_date: str
    action: str
    target_weight_hint: float | None
    holding_period_hint: str
    risk_notes: str
    source_run_id: str
