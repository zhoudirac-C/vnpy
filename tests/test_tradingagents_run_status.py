from datetime import datetime

from vnpy_tradingagents.monitoring import ReplayRunStatusBuilder, ReplayRunStatusLog
from vnpy_tradingagents.replay import (
    PortfolioReplaySummary,
    PortfolioReplayStepResult,
    ReplaySummary,
    ReplayStepResult,
)
from vnpy_tradingagents.risk import (
    DecisionAuditRecord,
    PreOrderDecisionResult,
    RiskCheckResult,
    RiskDecision,
)


def test_run_status_builder_summarizes_intraday_replay():
    """ReplayRunStatusBuilder should summarize intraday replay for gray-run views."""
    builder = ReplayRunStatusBuilder(clock=lambda: datetime(2024, 1, 3, 16, 0))

    status = builder.from_intraday_summary(
        run_id="replay-intraday-1",
        summary=ReplaySummary(
            total_steps=3,
            submit_allowed=1,
            risk_rejected=1,
            ai_blocked=1,
            ai_used=2,
            results=[
                make_result("decision-1", RiskDecision.APPROVED, "", True, ["run-rating"]),
                make_result("decision-2", RiskDecision.REJECTED, "max_order_value", False, []),
            ],
        ),
    )

    assert status.run_id == "replay-intraday-1"
    assert status.mode == "intraday"
    assert status.health == "blocked"
    assert status.total_steps == 3
    assert status.submit_allowed == 1
    assert status.risk_rejected == 1
    assert status.ai_blocked == 1
    assert status.ai_used == 2
    assert status.latest_decision_id == "decision-2"
    assert status.latest_action == "buy"
    assert status.latest_ai_decision == "allow"
    assert not status.latest_ai_used
    assert status.latest_risk_failed_rule == "max_order_value"


def test_run_status_builder_summarizes_portfolio_replay():
    """ReplayRunStatusBuilder should summarize long-horizon portfolio replay."""
    builder = ReplayRunStatusBuilder(clock=lambda: datetime(2024, 1, 5, 16, 0))

    status = builder.from_portfolio_summary(
        run_id="replay-portfolio-1",
        summary=PortfolioReplaySummary(
            total_steps=2,
            submit_allowed=0,
            risk_rejected=0,
            rating_blocked=2,
            ai_used=0,
            results=[
                make_portfolio_result("decision-1", RiskDecision.APPROVED, "", False, ["rating-1"])
            ],
        ),
    )

    assert status.run_id == "replay-portfolio-1"
    assert status.mode == "portfolio"
    assert status.health == "blocked"
    assert status.rating_blocked == 2
    assert status.ai_blocked == 0
    assert status.latest_ai_source_run_ids == ["rating-1"]


def test_run_status_log_writes_stable_json_line():
    """ReplayRunStatusLog should produce stable JSON for logs and future UI panels."""
    builder = ReplayRunStatusBuilder(clock=lambda: datetime(2024, 1, 3, 16, 0))
    status = builder.from_intraday_summary(
        run_id="replay-intraday-1",
        summary=ReplaySummary(
            total_steps=0,
            submit_allowed=0,
            risk_rejected=0,
            ai_blocked=0,
            ai_used=0,
            results=[],
        ),
    )

    line = ReplayRunStatusLog().to_json_line(status)

    assert line.endswith("\n")
    assert '"health": "no_data"' in line
    assert '"run_id": "replay-intraday-1"' in line
    assert '"mode": "intraday"' in line


def make_result(
    decision_id: str,
    risk_decision: RiskDecision,
    failed_rule: str,
    submit_allowed: bool,
    source_run_ids: list[str],
) -> ReplayStepResult:
    """Create a ReplayStepResult fixture with only status-relevant fields."""
    return ReplayStepResult(
        step=None,  # type: ignore[arg-type]
        fused_signal=None,  # type: ignore[arg-type]
        decision=PreOrderDecisionResult(
            submit_allowed=submit_allowed,
            risk_result=RiskCheckResult(decision=risk_decision, failed_rule=failed_rule),
            audit_record=make_audit_record(decision_id, risk_decision, failed_rule, source_run_ids),
        ),
        submit_allowed=submit_allowed,
    )


def make_portfolio_result(
    decision_id: str,
    risk_decision: RiskDecision,
    failed_rule: str,
    submit_allowed: bool,
    source_run_ids: list[str],
) -> PortfolioReplayStepResult:
    """Create a PortfolioReplayStepResult fixture with only status-relevant fields."""
    return PortfolioReplayStepResult(
        step=None,  # type: ignore[arg-type]
        fused_signal=None,  # type: ignore[arg-type]
        decision=PreOrderDecisionResult(
            submit_allowed=submit_allowed,
            risk_result=RiskCheckResult(decision=risk_decision, failed_rule=failed_rule),
            audit_record=make_audit_record(decision_id, risk_decision, failed_rule, source_run_ids),
        ),
        submit_allowed=submit_allowed,
    )


def make_audit_record(
    decision_id: str,
    risk_decision: RiskDecision,
    failed_rule: str,
    source_run_ids: list[str],
) -> DecisionAuditRecord:
    """Create an audit record fixture."""
    return DecisionAuditRecord(
        decision_id=decision_id,
        created_at=datetime(2024, 1, 3, 10, 10),
        vt_symbol="600519.SSE",
        action="buy",
        price=100,
        volume=50,
        rule_confidence=0.9,
        ai_decision="allow",
        ai_used=bool(source_run_ids),
        ai_source_run_ids=source_run_ids,
        risk_decision=risk_decision,
        risk_failed_rule=failed_rule,
        risk_reason="",
    )
