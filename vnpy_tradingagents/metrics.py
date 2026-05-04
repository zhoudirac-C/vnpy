import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MetricsSnapshot:
    """
    Aggregated operational metrics.
    """

    run_count: int = 0
    failure_count: int = 0
    total_latency_seconds: float = 0
    degraded_sources: dict[str, int] = field(default_factory=dict)
    blocked_orders: int = 0
    blocked_reasons: dict[str, int] = field(default_factory=dict)

    @property
    def avg_latency_seconds(self) -> float:
        """
        Average run latency.
        """
        if not self.run_count:
            return 0
        return self.total_latency_seconds / self.run_count

    def to_dict(self) -> dict[str, Any]:
        """
        Convert metrics into a monitor-friendly dictionary.
        """
        return {
            "run_count": self.run_count,
            "failure_count": self.failure_count,
            "avg_latency_seconds": self.avg_latency_seconds,
            "degraded_sources": dict(sorted(self.degraded_sources.items())),
            "blocked_orders": self.blocked_orders,
            "blocked_reasons": dict(sorted(self.blocked_reasons.items())),
        }


class MetricsCollector:
    """
    In-process metrics collector for logs or external monitoring scrapers.
    """

    def __init__(self) -> None:
        """"""
        self.snapshot: MetricsSnapshot = MetricsSnapshot()

    def record_run(
        self,
        success: bool,
        latency_seconds: float,
        degraded_sources: list[str] | None = None,
    ) -> None:
        """
        Record one TradingAgents run.
        """
        self.snapshot.run_count += 1
        if not success:
            self.snapshot.failure_count += 1
        self.snapshot.total_latency_seconds += latency_seconds
        for source in degraded_sources or []:
            self.snapshot.degraded_sources[source] = (
                self.snapshot.degraded_sources.get(source, 0) + 1
            )

    def record_blocked_order(self, reason: str) -> None:
        """
        Record one blocked pre-order decision.
        """
        self.snapshot.blocked_orders += 1
        self.snapshot.blocked_reasons[reason] = (
            self.snapshot.blocked_reasons.get(reason, 0) + 1
        )

    def to_json_line(self) -> str:
        """
        Export one stable JSON line.
        """
        return json.dumps(self.snapshot.to_dict(), ensure_ascii=False, sort_keys=True) + "\n"
