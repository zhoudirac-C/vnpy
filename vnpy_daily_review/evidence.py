"""
Evidence pack builder for daily market review.
"""

from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from decimal import Decimal
from hashlib import sha256
import re
from typing import Any

from .domain import DailyEventCatalyst
from .signals import LeaderScore, MarketBreadthSignal, SectorRotationSignal


SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{3,}"),
    re.compile(r"OPENAI_API_KEY\s*=", re.IGNORECASE),
    re.compile(r"ZHIPU_API_KEY\s*=", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]+", re.IGNORECASE),
    re.compile(r"api-key\s*:", re.IGNORECASE),
]


class EvidenceSecretError(ValueError):
    """
    Secret-like content was found in evidence.
    """


@dataclass(frozen=True)
class EvidenceItem:
    """
    Auditable evidence item.
    """

    evidence_id: str
    source: str
    source_type: str
    content: str
    trust_score: Decimal
    data_time: datetime
    content_hash: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_llm_dict(self) -> dict[str, Any]:
        """
        Convert to an LLM input dictionary.
        """
        return {
            "evidence_id": self.evidence_id,
            "source": self.source,
            "source_type": self.source_type,
            "content": self.content,
            "trust_score": str(self.trust_score),
            "data_time": self.data_time.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class EvidencePack:
    """
    Daily review evidence pack.
    """

    trade_date: date
    market_summary: dict[str, Any]
    themes: list[dict[str, Any]]
    leader_candidates: list[dict[str, Any]]
    risk_events: list[dict[str, Any]]
    news_catalysts: list[dict[str, Any]]
    data_quality: list[str]
    evidence: list[EvidenceItem]
    min_trust_score: Decimal
    max_llm_items: int

    def to_llm_input(self) -> dict[str, Any]:
        """
        Build a filtered LLM payload and scan it for secrets.
        """
        llm_evidence = [
            item
            for item in self.evidence
            if item.trust_score >= self.min_trust_score
        ][: self.max_llm_items]
        try:
            EvidenceSecretGuard().assert_no_secrets(llm_evidence)
        except EvidenceSecretError:
            if "secret_like_content_detected" not in self.data_quality:
                self.data_quality.append("secret_like_content_detected")
            raise

        return {
            "trade_date": self.trade_date.isoformat(),
            "market_summary": self.market_summary,
            "themes": self.themes,
            "leader_candidates": self.leader_candidates,
            "risk_events": self.risk_events,
            "news_catalysts": self.news_catalysts,
            "data_quality": list(self.data_quality),
            "evidence": [item.to_llm_dict() for item in llm_evidence],
        }


class EvidencePackBuilder:
    """
    Build daily review evidence packs.
    """

    def __init__(
        self,
        min_trust_score: Decimal = Decimal("0.6"),
        max_llm_items: int = 200,
    ) -> None:
        self._min_trust_score = min_trust_score
        self._max_llm_items = max_llm_items

    def build(
        self,
        trade_date: date,
        market_signal: MarketBreadthSignal,
        sector_signals: list[SectorRotationSignal],
        leader_candidates: list[LeaderScore],
        risk_events: list[DailyEventCatalyst] | None = None,
        news_catalysts: list[DailyEventCatalyst] | None = None,
        data_quality: list[str] | None = None,
        extra_evidence: list[EvidenceItem] | None = None,
    ) -> EvidencePack:
        """
        Build the pack.
        """
        evidence: list[EvidenceItem] = [_market_evidence(trade_date, market_signal)]
        evidence.extend(_sector_evidence(trade_date, signal) for signal in sector_signals)
        evidence.extend(_leader_evidence(trade_date, leader) for leader in leader_candidates)
        risk_events = risk_events or []
        news_catalysts = news_catalysts or []
        evidence.extend(_event_evidence(event) for event in risk_events)
        evidence.extend(_event_evidence(event) for event in news_catalysts)
        evidence.extend(extra_evidence or [])

        identified = _assign_evidence_ids(trade_date, evidence)
        return EvidencePack(
            trade_date=trade_date,
            market_summary=_market_summary(market_signal),
            themes=[_theme_payload(signal) for signal in sector_signals],
            leader_candidates=[
                _leader_payload(leader) for leader in leader_candidates
            ],
            risk_events=[_event_payload(event) for event in risk_events],
            news_catalysts=[_event_payload(event) for event in news_catalysts],
            data_quality=list(data_quality or []) + list(market_signal.quality_warnings),
            evidence=identified,
            min_trust_score=self._min_trust_score,
            max_llm_items=self._max_llm_items,
        )


class EvidenceSecretGuard:
    """
    Scan evidence content before it is sent to an LLM.
    """

    def assert_no_secrets(self, evidence: list[EvidenceItem]) -> None:
        """
        Raise when secret-like content exists.
        """
        for item in evidence:
            if _contains_secret(item.content):
                raise EvidenceSecretError(
                    f"secret-like content detected in {item.evidence_id}"
                )


def _assign_evidence_ids(
    trade_date: date,
    evidence: list[EvidenceItem],
) -> list[EvidenceItem]:
    prefix = f"EVT-{trade_date:%Y%m%d}"
    seen: set[str] = set()
    result: list[EvidenceItem] = []
    for item in evidence:
        content_hash = item.content_hash or _content_hash(
            trade_date=trade_date,
            source=item.source,
            source_type=item.source_type,
            content=item.content,
        )
        if content_hash in seen:
            continue
        seen.add(content_hash)
        result.append(
            replace(
                item,
                evidence_id=f"{prefix}-{len(result) + 1:04d}",
                content_hash=content_hash,
            )
        )
    return result


def _market_evidence(trade_date: date, signal: MarketBreadthSignal) -> EvidenceItem:
    content = (
        f"市场宽度：上涨{signal.advance_count}家，下跌{signal.decline_count}家，"
        f"涨停{signal.limit_up_count}家，跌停{signal.limit_down_count}家，"
        f"breadth_score={signal.breadth_score}，emotion_score={signal.emotion_score}"
    )
    return EvidenceItem(
        evidence_id="",
        source="signal_engine",
        source_type="market_summary",
        content=content,
        trust_score=Decimal("0.95"),
        data_time=_close_time(trade_date),
        content_hash="",
        metadata=signal.evidence_payload,
    )


def _sector_evidence(trade_date: date, signal: SectorRotationSignal) -> EvidenceItem:
    content = (
        f"板块{signal.theme}状态{signal.status}，score={signal.score}，"
        f"核心标的={','.join(signal.leader_symbols)}，"
        f"风险标签={','.join(signal.risk_tags)}"
    )
    return EvidenceItem(
        evidence_id="",
        source="signal_engine",
        source_type="theme_rotation",
        content=content,
        trust_score=Decimal("0.9"),
        data_time=_close_time(trade_date),
        content_hash="",
        metadata=signal.evidence_payload,
    )


def _leader_evidence(trade_date: date, leader: LeaderScore) -> EvidenceItem:
    content = (
        f"风向标{leader.symbol} {leader.name} role={leader.role}，"
        f"score={leader.score}，action={leader.watch_action}，"
        f"entry={leader.entry_condition}，avoid={leader.avoid_condition}"
    )
    return EvidenceItem(
        evidence_id="",
        source="signal_engine",
        source_type="leader_candidate",
        content=content,
        trust_score=Decimal("0.9"),
        data_time=_close_time(trade_date),
        content_hash="",
        metadata=leader.evidence_payload,
    )


def _event_evidence(event: DailyEventCatalyst) -> EvidenceItem:
    return EvidenceItem(
        evidence_id="",
        source=event.source,
        source_type=event.source_type,
        content=(
            f"{event.title}；sentiment={event.sentiment}；"
            f"symbols={','.join(event.related_symbols)}；"
            f"sectors={','.join(event.related_sectors)}"
        ),
        trust_score=event.trust_score,
        data_time=event.published_at,
        content_hash=event.content_hash,
        metadata={"sentiment": event.sentiment},
    )


def _market_summary(signal: MarketBreadthSignal) -> dict[str, Any]:
    return {
        "advance_count": signal.advance_count,
        "decline_count": signal.decline_count,
        "flat_count": signal.flat_count,
        "limit_up_count": signal.limit_up_count,
        "limit_down_count": signal.limit_down_count,
        "breadth_score": str(signal.breadth_score),
        "emotion_score": str(signal.emotion_score),
    }


def _theme_payload(signal: SectorRotationSignal) -> dict[str, Any]:
    return {
        "theme": signal.theme,
        "score": str(signal.score),
        "status": signal.status,
        "leader_symbols": signal.leader_symbols,
        "risk_tags": signal.risk_tags,
    }


def _leader_payload(leader: LeaderScore) -> dict[str, Any]:
    return {
        "symbol": leader.symbol,
        "name": leader.name,
        "role": leader.role,
        "score": str(leader.score),
        "watch_action": leader.watch_action,
        "entry_condition": leader.entry_condition,
        "avoid_condition": leader.avoid_condition,
        "position_rule": leader.position_rule,
    }


def _event_payload(event: DailyEventCatalyst) -> dict[str, Any]:
    return {
        "title": event.title,
        "source": event.source,
        "source_type": event.source_type,
        "published_at": event.published_at.isoformat(),
        "related_symbols": event.related_symbols,
        "related_sectors": event.related_sectors,
        "sentiment": event.sentiment,
        "trust_score": str(event.trust_score),
    }


def _content_hash(
    trade_date: date,
    source: str,
    source_type: str,
    content: str,
) -> str:
    raw = f"{trade_date.isoformat()}|{source}|{source_type}|{content}"
    return sha256(raw.encode("utf-8")).hexdigest()


def _contains_secret(value: str) -> bool:
    return any(pattern.search(value) for pattern in SECRET_PATTERNS)


def _close_time(trade_date: date) -> datetime:
    return datetime(
        trade_date.year,
        trade_date.month,
        trade_date.day,
        15,
        30,
        tzinfo=UTC,
    )
