from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TradingAgentsWorkerRequest:
    """
    Provider-independent request sent to a TradingAgents worker.
    """

    run_id: str
    vt_symbol: str
    trade_date: str
    mode: str
    context: dict[str, Any]


@dataclass(frozen=True)
class TradingAgentsWorkerResponse:
    """
    Structured response returned by a TradingAgents worker.
    """

    run_id: str
    vt_symbol: str
    rating: str
    confidence: float
    report: str
    raw_state: dict[str, Any]
