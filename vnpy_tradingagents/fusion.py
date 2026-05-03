from dataclasses import dataclass
from datetime import datetime

from .policy import AiSignalPolicy, SignalDecision
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


@dataclass(frozen=True)
class RuleSignal:
    """
    Deterministic strategy signal generated before AI fusion.
    """

    action: str
    confidence: float
    reason: str = ""


@dataclass(frozen=True)
class FusedSignal:
    """
    Strategy-side signal after applying AI policy and fusion rules.
    """

    action: str
    confidence: float
    ai_decision: SignalDecision
    ai_used: bool
    blocked_reason: str = ""
    source_run_ids: list[str] | None = None


class SignalFusionService:
    """
    Fuse deterministic strategy output with TradingAgents signals.
    """

    def __init__(self, policy: AiSignalPolicy) -> None:
        """"""
        self.policy: AiSignalPolicy = policy

    def fuse(
        self,
        rule_signal: RuleSignal,
        rating: RatingSignal,
        advice: IntradayAdvice,
        now: datetime,
        live: bool,
    ) -> FusedSignal:
        """
        Apply AI policy without letting AI create standalone orders.
        """
        decision: SignalDecision = self.policy.evaluate(
            rating=rating,
            advice=advice,
            now=now,
            live=live,
        )

        if decision == SignalDecision.IGNORE:
            return _base_signal(rule_signal, decision, "ai_unavailable")

        if decision == SignalDecision.BLOCK_BUY and _is_buy_action(rule_signal):
            return FusedSignal(
                action="hold",
                confidence=rule_signal.confidence,
                ai_decision=decision,
                ai_used=False,
                blocked_reason="ai_block_buy",
                source_run_ids=_source_run_ids(rating, advice),
            )

        if _is_buy_advice(advice) and not _is_buy_action(rule_signal):
            return _base_signal(rule_signal, decision, "rule_not_confirmed")

        return FusedSignal(
            action=rule_signal.action,
            confidence=rule_signal.confidence,
            ai_decision=decision,
            ai_used=True,
            source_run_ids=_source_run_ids(rating, advice),
        )


def _base_signal(
    rule_signal: RuleSignal,
    ai_decision: SignalDecision,
    blocked_reason: str,
) -> FusedSignal:
    """"""
    return FusedSignal(
        action=rule_signal.action,
        confidence=rule_signal.confidence,
        ai_decision=ai_decision,
        ai_used=False,
        blocked_reason=blocked_reason,
        source_run_ids=[],
    )


def _is_buy_action(rule_signal: RuleSignal) -> bool:
    """"""
    return rule_signal.action.strip().lower() in BUY_ACTIONS


def _is_buy_advice(advice: IntradayAdvice) -> bool:
    """"""
    return advice.action.strip().lower() in BUY_ACTIONS


def _source_run_ids(rating: RatingSignal, advice: IntradayAdvice) -> list[str]:
    """"""
    return [rating.source_run_id, advice.source_run_id]
