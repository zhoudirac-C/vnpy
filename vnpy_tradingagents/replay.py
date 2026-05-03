from dataclasses import dataclass, replace
from datetime import datetime

from .fusion import FusedSignal, RuleSignal, SignalFusionService
from .policy import SignalDecision
from .risk import OrderIntent, PreOrderDecisionResult, PreOrderDecisionService, RiskDecision
from .signals import IntradayAdvice, PortfolioIntent, RatingSignal


BEARISH_RATINGS: frozenset[str] = frozenset({"sell", "underweight"})
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
class ReplayStep:
    """
    One historical decision point used for intraday replay.
    """

    at: datetime
    rule_signal: RuleSignal
    rating: RatingSignal
    advice: IntradayAdvice
    intent: OrderIntent


@dataclass(frozen=True)
class ReplayStepResult:
    """
    Replay result for one historical decision point.
    """

    step: ReplayStep
    fused_signal: FusedSignal
    decision: PreOrderDecisionResult
    submit_allowed: bool


@dataclass(frozen=True)
class ReplaySummary:
    """
    Aggregated replay result.
    """

    total_steps: int
    submit_allowed: int
    risk_rejected: int
    ai_blocked: int
    ai_used: int
    results: list[ReplayStepResult]


@dataclass(frozen=True)
class PortfolioReplayStep:
    """
    One historical long-horizon portfolio decision point.
    """

    at: datetime
    rating: RatingSignal
    intent: PortfolioIntent
    order_intent: OrderIntent


@dataclass(frozen=True)
class PortfolioReplayStepResult:
    """
    Portfolio replay result for one historical decision point.
    """

    step: PortfolioReplayStep
    fused_signal: FusedSignal
    decision: PreOrderDecisionResult
    submit_allowed: bool


@dataclass(frozen=True)
class PortfolioReplaySummary:
    """
    Aggregated long-horizon portfolio replay result.
    """

    total_steps: int
    submit_allowed: int
    risk_rejected: int
    rating_blocked: int
    ai_used: int
    results: list[PortfolioReplayStepResult]


class IntradayReplayEngine:
    """
    Replay intraday AI-assisted decisions without touching Gateway or MainEngine.
    """

    def __init__(
        self,
        fusion_service: SignalFusionService,
        decision_service: PreOrderDecisionService,
        live: bool = False,
    ) -> None:
        """"""
        self.fusion_service: SignalFusionService = fusion_service
        self.decision_service: PreOrderDecisionService = decision_service
        self.live: bool = live

    def run(self, steps: list[ReplayStep]) -> ReplaySummary:
        """
        Replay steps in historical time order.
        """
        results: list[ReplayStepResult] = []

        for step in sorted(steps, key=lambda item: item.at):
            fused_signal: FusedSignal = self.fusion_service.fuse(
                rule_signal=step.rule_signal,
                rating=step.rating,
                advice=step.advice,
                now=step.at,
                live=self.live,
            )
            intent: OrderIntent = replace(step.intent, action=fused_signal.action)
            decision: PreOrderDecisionResult = self.decision_service.evaluate(
                intent=intent,
                fused_signal=fused_signal,
            )
            submit_allowed: bool = decision.submit_allowed and fused_signal.action != "hold"
            results.append(
                ReplayStepResult(
                    step=step,
                    fused_signal=fused_signal,
                    decision=decision,
                    submit_allowed=submit_allowed,
                )
            )

        return ReplaySummary(
            total_steps=len(results),
            submit_allowed=sum(1 for result in results if result.submit_allowed),
            risk_rejected=sum(
                1 for result in results if result.decision.risk_result.decision == RiskDecision.REJECTED
            ),
            ai_blocked=sum(
                1 for result in results if result.fused_signal.ai_decision == SignalDecision.BLOCK_BUY
            ),
            ai_used=sum(1 for result in results if result.fused_signal.ai_used),
            results=results,
        )


class PortfolioReplayEngine:
    """
    Replay long-horizon AI-assisted portfolio decisions without submitting orders.
    """

    def __init__(self, decision_service: PreOrderDecisionService) -> None:
        """"""
        self.decision_service: PreOrderDecisionService = decision_service

    def run(self, steps: list[PortfolioReplayStep]) -> PortfolioReplaySummary:
        """
        Replay portfolio steps in historical time order.
        """
        results: list[PortfolioReplayStepResult] = []

        for step in sorted(steps, key=lambda item: item.at):
            fused_signal: FusedSignal = _portfolio_fused_signal(step)
            order_intent: OrderIntent = replace(step.order_intent, action=fused_signal.action)
            decision: PreOrderDecisionResult = self.decision_service.evaluate(
                intent=order_intent,
                fused_signal=fused_signal,
            )
            submit_allowed: bool = decision.submit_allowed and fused_signal.action != "hold"
            results.append(
                PortfolioReplayStepResult(
                    step=step,
                    fused_signal=fused_signal,
                    decision=decision,
                    submit_allowed=submit_allowed,
                )
            )

        return PortfolioReplaySummary(
            total_steps=len(results),
            submit_allowed=sum(1 for result in results if result.submit_allowed),
            risk_rejected=sum(
                1 for result in results if result.decision.risk_result.decision == RiskDecision.REJECTED
            ),
            rating_blocked=sum(
                1 for result in results if result.fused_signal.blocked_reason == "rating_block_buy"
            ),
            ai_used=sum(1 for result in results if result.fused_signal.ai_used),
            results=results,
        )


def _portfolio_fused_signal(step: PortfolioReplayStep) -> FusedSignal:
    """"""
    source_run_ids: list[str] = [step.rating.source_run_id, step.intent.source_run_id]
    if _is_bearish(step.rating) and _is_buy_action(step.intent.action):
        return FusedSignal(
            action="hold",
            confidence=step.rating.confidence,
            ai_decision=SignalDecision.BLOCK_BUY,
            ai_used=False,
            blocked_reason="rating_block_buy",
            source_run_ids=source_run_ids,
        )

    return FusedSignal(
        action=step.intent.action,
        confidence=step.rating.confidence,
        ai_decision=SignalDecision.ALLOW,
        ai_used=True,
        source_run_ids=source_run_ids,
    )


def _is_bearish(rating: RatingSignal) -> bool:
    """"""
    return rating.rating.strip().lower() in BEARISH_RATINGS


def _is_buy_action(action: str) -> bool:
    """"""
    return action.strip().lower() in BUY_ACTIONS
