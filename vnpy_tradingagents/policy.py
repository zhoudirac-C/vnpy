from datetime import datetime
from enum import Enum

from .runtime import TradingAgentsRuntimeController
from .signals import IntradayAdvice, RatingSignal


BUY_ACTIONS: frozenset[str] = frozenset(
    {
        "buy",
        "buy_on_pullback",
        "add",
        "increase",
        "open_long",
    }
)
BEARISH_RATINGS: frozenset[str] = frozenset({"sell", "underweight"})


class SignalDecision(Enum):
    """
    Decision for consuming a TradingAgents signal inside vn.py strategies.
    """

    ALLOW = "allow"
    IGNORE = "ignore"
    BLOCK_BUY = "block_buy"


class AiSignalPolicy:
    """
    Policy boundary between TradingAgents output and vn.py strategies.
    """

    def __init__(self, runtime: TradingAgentsRuntimeController) -> None:
        """"""
        self.runtime: TradingAgentsRuntimeController = runtime

    def evaluate(
        self,
        rating: RatingSignal,
        advice: IntradayAdvice,
        now: datetime,
        live: bool,
    ) -> SignalDecision:
        """
        Decide whether a strategy may consume the latest AI signal pair.
        """
        if not self.runtime.can_use_signal(live):
            return SignalDecision.IGNORE

        if advice.valid_until < now:
            return SignalDecision.IGNORE

        if _is_bearish(rating) and _is_buy_advice(advice):
            return SignalDecision.BLOCK_BUY

        return SignalDecision.ALLOW


def _is_bearish(rating: RatingSignal) -> bool:
    """"""
    return rating.rating.strip().lower() in BEARISH_RATINGS


def _is_buy_advice(advice: IntradayAdvice) -> bool:
    """"""
    return advice.action.strip().lower() in BUY_ACTIONS
