import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .replay import (
    PortfolioReplayStepResult,
    PortfolioReplaySummary,
    ReplayStepResult,
    ReplaySummary,
)
from .risk import DecisionAuditRecord


@dataclass(frozen=True)
class ReplayRunStatus:
    """
    Gray-run status DTO for replay logs and future UI panels.
    """

    run_id: str
    mode: str
    generated_at: datetime
    health: str
    total_steps: int
    submit_allowed: int
    risk_rejected: int
    ai_blocked: int
    rating_blocked: int
    ai_used: int
    latest_decision_id: str = ""
    latest_vt_symbol: str = ""
    latest_action: str = ""
    latest_ai_decision: str = ""
    latest_ai_used: bool = False
    latest_risk_decision: str = ""
    latest_risk_failed_rule: str = ""
    latest_ai_source_run_ids: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        """
        Convert status into a JSON-serializable dictionary.
        """
        return {
            "run_id": self.run_id,
            "mode": self.mode,
            "generated_at": self.generated_at.isoformat(),
            "health": self.health,
            "total_steps": self.total_steps,
            "submit_allowed": self.submit_allowed,
            "risk_rejected": self.risk_rejected,
            "ai_blocked": self.ai_blocked,
            "rating_blocked": self.rating_blocked,
            "ai_used": self.ai_used,
            "latest_decision_id": self.latest_decision_id,
            "latest_vt_symbol": self.latest_vt_symbol,
            "latest_action": self.latest_action,
            "latest_ai_decision": self.latest_ai_decision,
            "latest_ai_used": self.latest_ai_used,
            "latest_risk_decision": self.latest_risk_decision,
            "latest_risk_failed_rule": self.latest_risk_failed_rule,
            "latest_ai_source_run_ids": self.latest_ai_source_run_ids or [],
        }


class ReplayRunStatusBuilder:
    """
    Build status snapshots from intraday and portfolio replay summaries.
    """

    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        """"""
        self.clock: Callable[[], datetime] = clock or datetime.now

    def from_intraday_summary(
        self,
        run_id: str,
        summary: ReplaySummary,
    ) -> ReplayRunStatus:
        """
        Build a status snapshot from intraday replay summary.
        """
        latest: DecisionAuditRecord | None = _latest_audit(summary.results)
        return ReplayRunStatus(
            run_id=run_id,
            mode="intraday",
            generated_at=self.clock(),
            health=_health(summary.total_steps, summary.submit_allowed, summary.risk_rejected, summary.ai_blocked),
            total_steps=summary.total_steps,
            submit_allowed=summary.submit_allowed,
            risk_rejected=summary.risk_rejected,
            ai_blocked=summary.ai_blocked,
            rating_blocked=0,
            ai_used=summary.ai_used,
            **_latest_fields(latest),
        )

    def from_portfolio_summary(
        self,
        run_id: str,
        summary: PortfolioReplaySummary,
    ) -> ReplayRunStatus:
        """
        Build a status snapshot from long-horizon portfolio replay summary.
        """
        latest: DecisionAuditRecord | None = _latest_audit(summary.results)
        return ReplayRunStatus(
            run_id=run_id,
            mode="portfolio",
            generated_at=self.clock(),
            health=_health(
                summary.total_steps,
                summary.submit_allowed,
                summary.risk_rejected,
                summary.rating_blocked,
            ),
            total_steps=summary.total_steps,
            submit_allowed=summary.submit_allowed,
            risk_rejected=summary.risk_rejected,
            ai_blocked=0,
            rating_blocked=summary.rating_blocked,
            ai_used=summary.ai_used,
            **_latest_fields(latest),
        )


class ReplayRunStatusLog:
    """
    Serialize replay status snapshots for append-only logs.
    """

    def to_json_line(self, status: ReplayRunStatus) -> str:
        """
        Return one stable JSON line.
        """
        return json.dumps(status.to_dict(), ensure_ascii=False, sort_keys=True) + "\n"


def _latest_audit(
    results: Sequence[ReplayStepResult | PortfolioReplayStepResult],
) -> DecisionAuditRecord | None:
    """"""
    if not results:
        return None
    return results[-1].decision.audit_record


def _latest_fields(record: DecisionAuditRecord | None) -> dict[str, Any]:
    """"""
    if record is None:
        return {}

    return {
        "latest_decision_id": record.decision_id,
        "latest_vt_symbol": record.vt_symbol,
        "latest_action": record.action,
        "latest_ai_decision": record.ai_decision,
        "latest_ai_used": record.ai_used,
        "latest_risk_decision": record.risk_decision.value,
        "latest_risk_failed_rule": record.risk_failed_rule,
        "latest_ai_source_run_ids": record.ai_source_run_ids,
    }


def _health(
    total_steps: int,
    submit_allowed: int,
    risk_rejected: int,
    ai_blocked: int,
) -> str:
    """"""
    if not total_steps:
        return "no_data"

    if risk_rejected or ai_blocked:
        return "blocked"

    if submit_allowed:
        return "ready"

    return "watch"
