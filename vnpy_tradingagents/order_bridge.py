from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from vnpy.trader.constant import Direction, Exchange, OrderType
from vnpy.trader.object import OrderRequest

from .fusion import FusedSignal
from .risk import (
    DecisionAuditRecord,
    DecisionAuditStorage,
    OrderIntent,
    PreOrderDecisionResult,
    PreOrderDecisionService,
    RiskCheckResult,
    RiskDecision,
    RiskRuleSet,
)
from .runtime import TradingAgentsRuntimeController


BUY_ACTIONS: frozenset[str] = frozenset({"buy", "add", "increase", "open_long"})
SELL_ACTIONS: frozenset[str] = frozenset({"sell", "reduce", "exit", "close_long"})


@dataclass(frozen=True)
class OrderBridgeResult:
    """
    Result of converting an audited intent to a vn.py order request.
    """

    decision: PreOrderDecisionResult
    order_request: OrderRequest | None


class OrderBridge:
    """
    Controlled boundary from TradingAgents-assisted intent to vn.py OrderRequest.
    """

    def __init__(
        self,
        rules: RiskRuleSet,
        audit_storage: DecisionAuditStorage,
        runtime: TradingAgentsRuntimeController | None = None,
        decision_id_factory: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """"""
        self.runtime: TradingAgentsRuntimeController | None = runtime
        self.decision_service: PreOrderDecisionService = PreOrderDecisionService(
            rules=rules,
            audit_storage=audit_storage,
            decision_id_factory=decision_id_factory,
            clock=clock,
        )

    def to_order_request(
        self,
        intent: OrderIntent,
        fused_signal: FusedSignal,
        live: bool = True,
    ) -> OrderBridgeResult:
        """
        Save pre-order audit, then build OrderRequest only if risk allows.
        """
        if live and not self._live_ai_order_allowed():
            return OrderBridgeResult(
                decision=self._blocked_live_decision(intent, fused_signal),
                order_request=None,
            )

        decision: PreOrderDecisionResult = self.decision_service.evaluate(
            intent,
            fused_signal,
        )
        if not decision.submit_allowed:
            return OrderBridgeResult(decision=decision, order_request=None)

        return OrderBridgeResult(
            decision=decision,
            order_request=_intent_to_order_request(intent, decision),
        )

    def _live_ai_order_allowed(self) -> bool:
        """
        Return whether this bridge may create live AI-assisted orders.
        """
        return bool(self.runtime and self.runtime.can_use_signal(live=True))

    def _blocked_live_decision(
        self,
        intent: OrderIntent,
        fused_signal: FusedSignal,
    ) -> PreOrderDecisionResult:
        """
        Save an audit record for a live-order block before returning no order.
        """
        risk_result = RiskCheckResult(
            decision=RiskDecision.REJECTED,
            failed_rule="live_ai_disabled",
            reason="live TradingAgents order bridge requires live_allowed runtime mode",
        )
        audit_record = DecisionAuditRecord.from_decision(
            decision_id=self.decision_service.decision_id_factory(),
            created_at=self.decision_service.clock(),
            intent=intent,
            fused_signal=fused_signal,
            risk_result=risk_result,
        )
        self.decision_service.audit_storage.save_decision(audit_record)
        return PreOrderDecisionResult(
            submit_allowed=False,
            risk_result=risk_result,
            audit_record=audit_record,
        )


def _intent_to_order_request(
    intent: OrderIntent,
    decision: PreOrderDecisionResult,
) -> OrderRequest:
    """
    Convert approved intent into vn.py OrderRequest.
    """
    symbol, exchange = _split_vt_symbol(intent.vt_symbol)
    return OrderRequest(
        symbol=symbol,
        exchange=exchange,
        direction=_direction_for_action(intent.action),
        type=OrderType.LIMIT,
        volume=intent.volume,
        price=intent.price,
        reference=f"TradingAgents:{decision.audit_record.decision_id}",
    )


def _split_vt_symbol(vt_symbol: str) -> tuple[str, Exchange]:
    """
    Split vn.py vt_symbol into symbol and exchange.
    """
    symbol, exchange_value = vt_symbol.rsplit(".", 1)
    return symbol, Exchange(exchange_value)


def _direction_for_action(action: str) -> Direction:
    """
    Map strategy action to vn.py order direction.
    """
    normalized: str = action.strip().lower()
    if normalized in BUY_ACTIONS:
        return Direction.LONG
    if normalized in SELL_ACTIONS:
        return Direction.SHORT
    raise ValueError(f"unsupported order intent action: {action}")
