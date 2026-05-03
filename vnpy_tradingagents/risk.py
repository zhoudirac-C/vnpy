import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Protocol
from uuid import uuid4

from .fusion import FusedSignal


BUY_ACTIONS: frozenset[str] = frozenset(
    {
        "buy",
        "buy_on_pullback",
        "add",
        "increase",
        "open_long",
    }
)


class RiskDecision(Enum):
    """
    Deterministic risk decision before an intent can become an order request.
    """

    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True)
class OrderIntent:
    """
    Strategy intent checked before converting to vn.py OrderRequest.
    """

    vt_symbol: str
    action: str
    price: float
    volume: float
    current_position: float = 0
    daily_traded_value: float = 0
    drawdown: float = 0
    cancel_count: int = 0
    limit_up: float | None = None
    limit_down: float | None = None

    @property
    def order_value(self) -> float:
        """
        Return notional order value.
        """
        return self.price * self.volume


@dataclass(frozen=True)
class RiskCheckResult:
    """
    Result returned by the deterministic risk layer.
    """

    decision: RiskDecision
    failed_rule: str = ""
    reason: str = ""


@dataclass(frozen=True)
class RiskRuleSet:
    """
    Deterministic risk rules for AI-assisted strategy intents.
    """

    max_position_volume: float | None = None
    max_order_value: float | None = None
    max_daily_traded_value: float | None = None
    max_drawdown: float | None = None
    max_cancel_count: int | None = None
    blacklist: frozenset[str] = field(default_factory=frozenset)
    reject_limit_up_buy: bool = True
    reject_limit_down_sell: bool = True

    def evaluate(self, intent: OrderIntent) -> RiskCheckResult:
        """
        Evaluate an order intent against deterministic rules.
        """
        if intent.action.strip().lower() == "hold":
            return _approved()

        if intent.vt_symbol in self.blacklist:
            return _rejected("blacklist", "symbol is blacklisted")

        if self.max_order_value is not None and intent.order_value > self.max_order_value:
            return _rejected("max_order_value", "single order value exceeds limit")

        if (
            self.max_position_volume is not None
            and _is_buy_action(intent)
            and intent.current_position + intent.volume > self.max_position_volume
        ):
            return _rejected("max_position_volume", "position volume exceeds limit")

        if (
            self.max_daily_traded_value is not None
            and intent.daily_traded_value + intent.order_value > self.max_daily_traded_value
        ):
            return _rejected("max_daily_traded_value", "daily traded value exceeds limit")

        if self.max_drawdown is not None and intent.drawdown > self.max_drawdown:
            return _rejected("max_drawdown", "drawdown exceeds limit")

        if self.max_cancel_count is not None and intent.cancel_count > self.max_cancel_count:
            return _rejected("max_cancel_count", "cancel count exceeds limit")

        if (
            self.reject_limit_up_buy
            and _is_buy_action(intent)
            and intent.limit_up is not None
            and intent.price >= intent.limit_up
        ):
            return _rejected("limit_up_buy", "buy at limit-up is blocked")

        if (
            self.reject_limit_down_sell
            and _is_sell_action(intent)
            and intent.limit_down is not None
            and intent.price <= intent.limit_down
        ):
            return _rejected("limit_down_sell", "sell at limit-down is blocked")

        return _approved()


@dataclass(frozen=True)
class DecisionAuditRecord:
    """
    Auditable pre-order decision record.
    """

    decision_id: str
    created_at: datetime
    vt_symbol: str
    action: str
    price: float
    volume: float
    rule_confidence: float
    ai_decision: str
    ai_used: bool
    ai_source_run_ids: list[str]
    risk_decision: RiskDecision
    risk_failed_rule: str
    risk_reason: str

    @classmethod
    def from_decision(
        cls,
        decision_id: str,
        created_at: datetime,
        intent: OrderIntent,
        fused_signal: FusedSignal,
        risk_result: RiskCheckResult,
    ) -> "DecisionAuditRecord":
        """
        Build an audit record from strategy, AI and risk outputs.
        """
        return cls(
            decision_id=decision_id,
            created_at=created_at,
            vt_symbol=intent.vt_symbol,
            action=intent.action,
            price=intent.price,
            volume=intent.volume,
            rule_confidence=fused_signal.confidence,
            ai_decision=fused_signal.ai_decision.value,
            ai_used=fused_signal.ai_used,
            ai_source_run_ids=fused_signal.source_run_ids or [],
            risk_decision=risk_result.decision,
            risk_failed_rule=risk_result.failed_rule,
            risk_reason=risk_result.reason,
        )


@dataclass(frozen=True)
class PreOrderDecisionResult:
    """
    Result of the pre-order risk and audit boundary.
    """

    submit_allowed: bool
    risk_result: RiskCheckResult
    audit_record: DecisionAuditRecord


DECISION_AUDIT_SCHEMA: str = """
CREATE TABLE IF NOT EXISTS decision_audit (
    decision_id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    vt_symbol TEXT NOT NULL,
    action TEXT NOT NULL,
    price DOUBLE PRECISION NOT NULL,
    volume DOUBLE PRECISION NOT NULL,
    rule_confidence DOUBLE PRECISION NOT NULL,
    ai_decision TEXT NOT NULL,
    ai_used BOOLEAN NOT NULL,
    ai_source_run_ids JSONB NOT NULL,
    risk_decision TEXT NOT NULL,
    risk_failed_rule TEXT,
    risk_reason TEXT
);
"""


INSERT_DECISION_AUDIT_SQL: str = """
INSERT INTO decision_audit (
    decision_id,
    created_at,
    vt_symbol,
    action,
    price,
    volume,
    rule_confidence,
    ai_decision,
    ai_used,
    ai_source_run_ids,
    risk_decision,
    risk_failed_rule,
    risk_reason
) VALUES (
    %(decision_id)s,
    %(created_at)s,
    %(vt_symbol)s,
    %(action)s,
    %(price)s,
    %(volume)s,
    %(rule_confidence)s,
    %(ai_decision)s,
    %(ai_used)s,
    %(ai_source_run_ids)s,
    %(risk_decision)s,
    %(risk_failed_rule)s,
    %(risk_reason)s
)
ON CONFLICT (decision_id)
DO UPDATE SET
    created_at = EXCLUDED.created_at,
    vt_symbol = EXCLUDED.vt_symbol,
    action = EXCLUDED.action,
    price = EXCLUDED.price,
    volume = EXCLUDED.volume,
    rule_confidence = EXCLUDED.rule_confidence,
    ai_decision = EXCLUDED.ai_decision,
    ai_used = EXCLUDED.ai_used,
    ai_source_run_ids = EXCLUDED.ai_source_run_ids,
    risk_decision = EXCLUDED.risk_decision,
    risk_failed_rule = EXCLUDED.risk_failed_rule,
    risk_reason = EXCLUDED.risk_reason;
"""


class Cursor(Protocol):
    """
    Minimal DB-API cursor protocol.
    """

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> None:
        pass

    def close(self) -> None:
        pass


class Connection(Protocol):
    """
    Minimal DB-API connection protocol.
    """

    def cursor(self) -> Cursor:
        pass

    def commit(self) -> None:
        pass


class PostgresDecisionAuditStorage:
    """
    PostgreSQL storage for auditable pre-order decisions.
    """

    def __init__(self, connection: Connection) -> None:
        """"""
        self.connection: Connection = connection

    def create_schema(self) -> None:
        """
        Create the decision audit table.
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(DECISION_AUDIT_SCHEMA)
            self.connection.commit()
        finally:
            cursor.close()

    def save_decision(self, record: DecisionAuditRecord) -> None:
        """
        Persist an auditable decision record.
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(INSERT_DECISION_AUDIT_SQL, _audit_params(record))
            self.connection.commit()
        finally:
            cursor.close()


class DecisionAuditStorage(Protocol):
    """
    Storage protocol for pre-order audit records.
    """

    def save_decision(self, record: DecisionAuditRecord) -> None:
        pass


class PreOrderDecisionService:
    """
    Evaluate risk and persist audit before any OrderRequest conversion.
    """

    def __init__(
        self,
        rules: RiskRuleSet,
        audit_storage: DecisionAuditStorage,
        decision_id_factory: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """"""
        self.rules: RiskRuleSet = rules
        self.audit_storage: DecisionAuditStorage = audit_storage
        self.decision_id_factory: Callable[[], str] = decision_id_factory or _decision_id
        self.clock: Callable[[], datetime] = clock or datetime.now

    def evaluate(
        self,
        intent: OrderIntent,
        fused_signal: FusedSignal,
    ) -> PreOrderDecisionResult:
        """
        Run deterministic risk, save audit and return whether submit may continue.
        """
        risk_result: RiskCheckResult = self.rules.evaluate(intent)
        audit_record: DecisionAuditRecord = DecisionAuditRecord.from_decision(
            decision_id=self.decision_id_factory(),
            created_at=self.clock(),
            intent=intent,
            fused_signal=fused_signal,
            risk_result=risk_result,
        )
        self.audit_storage.save_decision(audit_record)

        return PreOrderDecisionResult(
            submit_allowed=risk_result.decision == RiskDecision.APPROVED,
            risk_result=risk_result,
            audit_record=audit_record,
        )


def _approved() -> RiskCheckResult:
    """"""
    return RiskCheckResult(decision=RiskDecision.APPROVED)


def _rejected(failed_rule: str, reason: str) -> RiskCheckResult:
    """"""
    return RiskCheckResult(
        decision=RiskDecision.REJECTED,
        failed_rule=failed_rule,
        reason=reason,
    )


def _is_buy_action(intent: OrderIntent) -> bool:
    """"""
    return intent.action.strip().lower() in BUY_ACTIONS


def _is_sell_action(intent: OrderIntent) -> bool:
    """"""
    return intent.action.strip().lower() in {"sell", "reduce", "exit", "close_long"}


def _audit_params(record: DecisionAuditRecord) -> dict[str, Any]:
    """"""
    return {
        "decision_id": record.decision_id,
        "created_at": record.created_at,
        "vt_symbol": record.vt_symbol,
        "action": record.action,
        "price": record.price,
        "volume": record.volume,
        "rule_confidence": record.rule_confidence,
        "ai_decision": record.ai_decision,
        "ai_used": record.ai_used,
        "ai_source_run_ids": json.dumps(record.ai_source_run_ids, ensure_ascii=False),
        "risk_decision": record.risk_decision.value,
        "risk_failed_rule": record.risk_failed_rule,
        "risk_reason": record.risk_reason,
    }


def _decision_id() -> str:
    """"""
    return f"decision-{uuid4().hex}"
