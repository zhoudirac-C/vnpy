from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from vnpy.trader.constant import Interval
from vnpy.trader.object import HistoryRequest


class ProviderCostLevel(Enum):
    """
    Operational cost level for a market/event data provider.
    """

    FREE = "free"
    LOW = "low"
    PAID = "paid"
    BROKER = "broker"
    MANUAL = "manual"


@dataclass(frozen=True)
class ProviderCapability:
    """
    Production capability matrix for one provider.
    """

    name: str
    intervals: frozenset[Interval] = frozenset()
    fields: frozenset[str] = frozenset()
    adjustments: frozenset[str] = frozenset({"none"})
    supports_tick: bool = False
    realtime: bool = False
    history: bool = True
    cost_level: ProviderCostLevel = ProviderCostLevel.FREE
    realtime_notes: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def supports_history_request(self, req: HistoryRequest) -> bool:
        """
        Return whether this provider can satisfy a vn.py history request.
        """
        if not self.history:
            return False

        if req.interval and self.intervals and req.interval not in self.intervals:
            return False

        return True

    def to_metadata(self) -> dict[str, Any]:
        """
        Convert capability into provider metadata safe for logs and snapshots.
        """
        return {
            "provider_name": self.name,
            "intervals": sorted(interval.value for interval in self.intervals),
            "fields": sorted(self.fields),
            "adjustments": sorted(self.adjustments),
            "supports_tick": self.supports_tick,
            "realtime": self.realtime,
            "history": self.history,
            "cost_level": self.cost_level.value,
            "realtime_notes": self.realtime_notes,
            "metadata": dict(self.metadata),
        }


def unsupported_reason(
    capability: ProviderCapability,
    req: HistoryRequest,
) -> str:
    """
    Explain why a provider cannot satisfy a request.
    """
    if not capability.history:
        return f"{capability.name} capability does not support historical data"
    if req.interval and capability.intervals and req.interval not in capability.intervals:
        return (
            f"{capability.name} capability does not support interval "
            f"{req.interval.value}"
        )
    return f"{capability.name} capability does not support request"
