from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from vnpy.trader.constant import Direction, Exchange, OrderType
from vnpy.trader.object import OrderRequest

from .fusion import FusedSignal
from .risk import (
    DecisionAuditStorage,
    OrderIntent,
    PreOrderDecisionResult,
    PreOrderDecisionService,
    RiskRuleSet,
)


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
        decision_id_factory: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """"""
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
    ) -> OrderBridgeResult:
        """
        Save pre-order audit, then build OrderRequest only if risk allows.
        """
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
