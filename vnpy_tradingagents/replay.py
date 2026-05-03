from dataclasses import dataclass, replace
from datetime import datetime

from .fusion import FusedSignal, RuleSignal, SignalFusionService
from .policy import SignalDecision
from .risk import OrderIntent, PreOrderDecisionResult, PreOrderDecisionService, RiskDecision
from .signals import IntradayAdvice, RatingSignal


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
