from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SnapshotSourcePolicyResult:
    """
    Result of validating worker context source completeness.
    """

    allowed: bool
    degraded_sources: list[str]
    missing_required_sources: list[str]
    blocked_reason: str = ""


@dataclass(frozen=True)
class SnapshotSourcePolicy:
    """
    Policy defining required and degradable worker context sources.
    """

    required_sources: frozenset[str]
    degradable_sources: frozenset[str]

    @classmethod
    def default(cls) -> "SnapshotSourcePolicy":
        """
        Default policy: market required, news/sentiment may degrade.
        """
        return cls.required(
            "market",
            degradable_sources=(
                "fundamentals",
                "valuation",
                "financials",
                "news",
                "sentiment",
                "benchmark",
                "portfolio",
            ),
        )

    @classmethod
    def required(
        cls,
        *required_sources: str,
        degradable_sources: tuple[str, ...] = ("news", "sentiment", "benchmark", "portfolio"),
    ) -> "SnapshotSourcePolicy":
        """
        Build policy with explicit required sources.
        """
        return cls(
            required_sources=frozenset(required_sources),
            degradable_sources=frozenset(degradable_sources),
        )

    def evaluate(self, context: dict[str, Any]) -> SnapshotSourcePolicyResult:
        """
        Evaluate whether a context can be sent to TradingAgents.
        """
        missing_required: list[str] = [
            source for source in sorted(self.required_sources) if not _has_source(context, source)
        ]
        degraded_sources: list[str] = [
            source
            for source in context.get("degraded_sources", [])
            if source in self.degradable_sources or source in self.required_sources
        ]

        if missing_required:
            source: str = missing_required[0]
            return SnapshotSourcePolicyResult(
                allowed=False,
                degraded_sources=degraded_sources,
                missing_required_sources=missing_required,
                blocked_reason=f"missing_required_source:{source}",
            )

        return SnapshotSourcePolicyResult(
            allowed=True,
            degraded_sources=degraded_sources,
            missing_required_sources=[],
        )


def _has_source(context: dict[str, Any], source: str) -> bool:
    """
    Return whether a source has usable data.
    """
    value: Any = context.get(source)
    if source == "market":
        if not isinstance(value, dict):
            return False
        bars: Any = value.get("bars")
        return isinstance(bars, list) and bool(bars)

    if value is None:
        return False
    if isinstance(value, dict):
        return bool(value)
    if isinstance(value, list):
        return bool(value)
    return True
