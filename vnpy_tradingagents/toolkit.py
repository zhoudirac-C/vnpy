from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, Any

from vnpy.trader.setting import SETTINGS

from .f10_financial import F10FinancialAnalyzer


@dataclass(frozen=True)
class SnapshotQuery:
    """
    Query window for building TradingAgents context.
    """

    vt_symbol: str
    start: datetime
    end: datetime


@dataclass(frozen=True)
class NewsContextFilter:
    """
    Filtering rules for TradingAgents news context.
    """

    min_trust_score: float = 0.70
    min_link_confidence: float = 0.75
    max_items: int = 20
    allowed_event_types: frozenset[str] = frozenset(
        {
            "announcement",
            "earnings",
            "regulatory",
            "buyback",
            "holding_change",
            "industry",
            "macro",
        }
    )


def build_news_context_filter(settings: dict[str, Any] | None = None) -> NewsContextFilter:
    """
    Build TradingAgents news-context filter from vn.py settings.
    """
    source = settings or SETTINGS
    return NewsContextFilter(
        min_trust_score=_to_float(source.get("news.filter.min_trust_score", 0.70), 0.70),
        min_link_confidence=_to_float(
            source.get("news.filter.min_link_confidence", 0.75),
            0.75,
        ),
        max_items=max(1, _to_int(source.get("news.filter.max_items_per_symbol", 20), 20)),
        allowed_event_types=frozenset(
            _split_names(
                source.get(
                    "news.filter.allowed_event_types",
                    "announcement,earnings,regulatory,buyback,holding_change,industry,macro",
                )
            )
        ),
    )


class SnapshotReader(Protocol):
    """
    Read-only snapshot source for MarketDataToolkit.
    """

    def load_bar_snapshots(
        self,
        vt_symbol: str,
        start: datetime,
        end: datetime,
    ) -> Sequence[dict[str, Any]]:
        pass

    def load_latest_snapshot(
        self,
        snapshot_type: str,
        vt_symbol: str,
        as_of: datetime,
    ) -> dict[str, Any] | None:
        pass

    def load_news_events(
        self,
        vt_symbol: str,
        start: datetime,
        end: datetime,
    ) -> Sequence[Any]:
        pass

    def load_sentiment_snapshot(
        self,
        vt_symbol: str,
        as_of: datetime,
    ) -> Any | None:
        pass

    def load_financial_context(
        self,
        vt_symbol: str,
        as_of: datetime,
        max_periods: int = 4,
    ) -> dict[str, Any]:
        pass


class CompositeSnapshotReader:
    """
    Compose vn.py snapshot storage with normalized event storage.
    """

    def __init__(
        self,
        snapshot_reader: Any,
        event_reader: Any,
        financial_reader: Any | None = None,
    ) -> None:
        """"""
        self.snapshot_reader = snapshot_reader
        self.event_reader = event_reader
        self.financial_reader = financial_reader

    def load_bar_snapshots(
        self,
        vt_symbol: str,
        start: datetime,
        end: datetime,
    ) -> Sequence[dict[str, Any]]:
        """
        Delegate market bars to the existing snapshot reader.
        """
        return self.snapshot_reader.load_bar_snapshots(vt_symbol, start, end)

    def load_latest_snapshot(
        self,
        snapshot_type: str,
        vt_symbol: str,
        as_of: datetime,
    ) -> dict[str, Any] | None:
        """
        Delegate non-event snapshots to the existing snapshot reader.
        """
        return self.snapshot_reader.load_latest_snapshot(snapshot_type, vt_symbol, as_of)

    def load_news_events(
        self,
        vt_symbol: str,
        start: datetime,
        end: datetime,
    ) -> Sequence[Any]:
        """
        Delegate normalized news events to the event reader.
        """
        load_news_events = getattr(self.event_reader, "load_news_events", None)
        if callable(load_news_events):
            return load_news_events(vt_symbol, start, end)
        return []

    def load_sentiment_snapshot(
        self,
        vt_symbol: str,
        as_of: datetime,
    ) -> Any | None:
        """
        Delegate sentiment snapshots to the event reader.
        """
        load_sentiment_snapshot = getattr(self.event_reader, "load_sentiment_snapshot", None)
        if callable(load_sentiment_snapshot):
            return load_sentiment_snapshot(vt_symbol, as_of)
        return None

    def load_financial_context(
        self,
        vt_symbol: str,
        as_of: datetime,
        max_periods: int = 4,
    ) -> dict[str, Any]:
        """
        Delegate structured financial report context when configured.
        """
        reader = self.financial_reader or self.snapshot_reader
        load_financial_context = getattr(reader, "load_financial_context", None)
        if callable(load_financial_context):
            return load_financial_context(vt_symbol, as_of, max_periods)
        return {}


class MarketDataToolkit:
    """
    Read PostgreSQL snapshots and build TradingAgents input context.
    """

    snapshot_types: tuple[str, ...] = (
        "fundamentals",
        "valuation",
        "industry",
        "benchmark",
        "portfolio",
        "alpha_factor",
    )

    snapshot_context_keys: dict[str, str] = {
        "alpha_factor": "alpha_factors",
    }

    def __init__(
        self,
        reader: SnapshotReader,
        news_filter: NewsContextFilter | None = None,
        f10_analyzer: F10FinancialAnalyzer | None = None,
    ) -> None:
        """"""
        self.reader: SnapshotReader = reader
        self.news_filter: NewsContextFilter = news_filter or NewsContextFilter()
        self.f10_analyzer: F10FinancialAnalyzer = f10_analyzer or F10FinancialAnalyzer()

    def build_context(self, query: SnapshotQuery) -> dict[str, Any]:
        """
        Build a provider-independent context dictionary.
        """
        degraded_sources: list[str] = []
        bars: Sequence[dict[str, Any]] = self.reader.load_bar_snapshots(
            query.vt_symbol,
            query.start,
            query.end,
        )
        bar_list: list[dict[str, Any]] = list(bars)
        context: dict[str, Any] = {
            "vt_symbol": query.vt_symbol,
            "window": {
                "start": query.start.isoformat(),
                "end": query.end.isoformat(),
            },
            "market": {
                "bars": bar_list,
                "indicators": _market_indicators(bar_list),
            },
        }

        if not bars:
            degraded_sources.append("market")

        for snapshot_type in self.snapshot_types:
            snapshot: dict[str, Any] | None = self.reader.load_latest_snapshot(
                snapshot_type,
                query.vt_symbol,
                query.end,
            )
            context_key = self.snapshot_context_keys.get(snapshot_type, snapshot_type)
            context[context_key] = snapshot or {}
            if snapshot is None:
                degraded_sources.append(snapshot_type)

        news = _load_news(self.reader, query, self.news_filter)
        context["news"] = news
        if not news.get("events"):
            degraded_sources.append("news")

        sentiment = _load_sentiment(self.reader, query)
        context["sentiment"] = sentiment
        if not sentiment:
            degraded_sources.append("sentiment")

        financials = _load_financials(self.reader, query)
        context["financials"] = financials
        if not financials:
            degraded_sources.append("financials")
        else:
            context["f10_financial_analysis"] = self.f10_analyzer.analyze(
                vt_symbol=query.vt_symbol,
                financials=financials,
                fundamentals=context.get("fundamentals"),
                valuation=context.get("valuation"),
                industry=context.get("industry"),
            )

        context["data_quality"] = _data_quality_summary(context, degraded_sources)
        context["degraded_sources"] = degraded_sources
        return context


def _load_news(
    reader: SnapshotReader,
    query: SnapshotQuery,
    news_filter: NewsContextFilter,
) -> dict[str, Any]:
    """
    Load normalized event window when the reader supports it.
    """
    load_news_events = getattr(reader, "load_news_events", None)
    if callable(load_news_events):
        events = list(load_news_events(query.vt_symbol, query.start, query.end))
        filtered, stats = _filter_news_events(events, news_filter)
        return {
            "events": [_event_to_context(event) for event in filtered],
            "filter": stats,
        }

    snapshot = reader.load_latest_snapshot("news", query.vt_symbol, query.end)
    return dict(snapshot or {})


def _filter_news_events(
    events: Sequence[Any],
    news_filter: NewsContextFilter,
) -> tuple[list[Any], dict[str, int]]:
    """
    Filter events before they enter LLM context.
    """
    accepted: list[Any] = []
    stats = {
        "input_count": len(events),
        "output_count": 0,
        "dropped_low_trust": 0,
        "dropped_low_link_confidence": 0,
        "dropped_event_type": 0,
        "dropped_review_status": 0,
        "dropped_spam": 0,
        "dropped_limit": 0,
    }

    for event in events:
        event_type = str(_event_value(event, "event_type", ""))
        if str(_event_value(event, "review_status", "")).lower() == "blocked":
            stats["dropped_review_status"] += 1
            continue
        if float(_event_value(event, "spam_score", 0) or 0) >= 0.70:
            stats["dropped_spam"] += 1
            continue
        source_quality = str(_event_value(event, "source_quality", ""))
        trust_score = float(_event_value(event, "trust_score", 0) or 0)
        if trust_score < news_filter.min_trust_score and source_quality != "official_disclosure":
            stats["dropped_low_trust"] += 1
            continue
        if event_type not in news_filter.allowed_event_types:
            stats["dropped_event_type"] += 1
            continue
        link_confidence = float(_event_value(event, "link_confidence", 0) or 0)
        if link_confidence and link_confidence < news_filter.min_link_confidence:
            stats["dropped_low_link_confidence"] += 1
            continue
        accepted.append(event)

    accepted.sort(
        key=lambda event: (
            str(_event_value(event, "source_quality", "")) == "official_disclosure",
            float(_event_value(event, "trust_score", 0) or 0),
            _event_value(event, "occurred_at", ""),
        ),
        reverse=True,
    )
    if len(accepted) > news_filter.max_items:
        stats["dropped_limit"] = len(accepted) - news_filter.max_items
        accepted = accepted[: news_filter.max_items]
    stats["output_count"] = len(accepted)
    return accepted, stats


def _load_sentiment(reader: SnapshotReader, query: SnapshotQuery) -> dict[str, Any]:
    """
    Load sentiment snapshot when the reader supports it.
    """
    load_sentiment_snapshot = getattr(reader, "load_sentiment_snapshot", None)
    if callable(load_sentiment_snapshot):
        snapshot = load_sentiment_snapshot(query.vt_symbol, query.end)
        if snapshot is None:
            return {}
        payload = getattr(snapshot, "payload", None)
        if isinstance(payload, dict):
            result = dict(payload)
        else:
            result = {"payload": payload}
        result["_provider_name"] = getattr(snapshot, "provider_name", "")
        result["_provider_version"] = getattr(snapshot, "provider_version", "")
        result["_as_of"] = _iso(getattr(snapshot, "as_of", ""))
        return result

    snapshot = reader.load_latest_snapshot("sentiment", query.vt_symbol, query.end)
    return dict(snapshot or {})


def _load_financials(reader: SnapshotReader, query: SnapshotQuery) -> dict[str, Any]:
    """
    Load complete financial statement context when the reader supports it.
    """
    load_financial_context = getattr(reader, "load_financial_context", None)
    if callable(load_financial_context):
        context = load_financial_context(query.vt_symbol, query.end, 4)
        if isinstance(context, dict):
            return context
    return {}


def _market_indicators(bars: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """
    Build compact market indicators for TradingAgents context.
    """
    if not bars:
        return {}

    closes: list[float] = [
        float(bar["close"] if "close" in bar else bar.get("close_price", 0))
        for bar in bars
        if ("close" in bar or "close_price" in bar)
    ]
    if not closes:
        return {}

    latest_close = closes[-1]
    indicators: dict[str, Any] = {
        "latest_close": latest_close,
        "bar_count": len(bars),
    }
    if len(closes) >= 2 and closes[0]:
        indicators["window_return"] = latest_close / closes[0] - 1
    if len(closes) >= 5:
        indicators["ma5"] = sum(closes[-5:]) / 5
    if len(closes) >= 20:
        indicators["ma20"] = sum(closes[-20:]) / 20
    return indicators


def _event_to_context(event: Any) -> dict[str, Any]:
    """
    Convert dataclass-like events into context rows.
    """
    if isinstance(event, dict):
        return dict(event)
    return {
        "event_id": getattr(event, "event_id", ""),
        "vt_symbol": getattr(event, "vt_symbol", ""),
        "title": getattr(event, "title", ""),
        "summary": getattr(event, "summary", ""),
        "event_type": getattr(event, "event_type", ""),
        "occurred_at": _iso(getattr(event, "occurred_at", "")),
        "source": getattr(event, "source", ""),
        "provider_name": getattr(event, "provider_name", ""),
        "source_quality": getattr(event, "source_quality", ""),
        "trust_score": getattr(event, "trust_score", 0),
        "relevance_score": getattr(event, "relevance_score", 0),
        "link_confidence": getattr(event, "link_confidence", 0),
        "link_reason": getattr(event, "link_reason", ""),
        "sector": getattr(event, "sector", ""),
        "topic": getattr(event, "topic", ""),
        "cluster_id": getattr(event, "cluster_id", ""),
        "review_status": getattr(event, "review_status", ""),
    }


def _event_value(event: Any, key: str, default: Any = None) -> Any:
    """
    Read an event field from dict or dataclass-like objects.
    """
    if isinstance(event, dict):
        return event.get(key, default)
    return getattr(event, key, default)


def _data_quality_summary(
    context: dict[str, Any],
    degraded_sources: Sequence[str],
) -> dict[str, Any]:
    """
    Summarize data availability for worker prompts and audits.
    """
    return {
        "degraded_sources": list(degraded_sources),
        "market_bar_count": len(context.get("market", {}).get("bars", [])),
        "news_event_count": len(context.get("news", {}).get("events", [])),
        "has_sentiment": bool(context.get("sentiment")),
        "has_alpha_factors": bool(context.get("alpha_factors")),
    }


def _iso(value: Any) -> Any:
    """
    Return ISO text for datetime-like values.
    """
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return isoformat()
    return value


def _split_names(value: Any) -> list[str]:
    """
    Split comma/semicolon separated config text.
    """
    if isinstance(value, Sequence) and not isinstance(value, str):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    if not text:
        return []
    for sep in (";", "，", "\n"):
        text = text.replace(sep, ",")
    return [item.strip() for item in text.split(",") if item.strip()]


def _to_float(value: Any, default: float) -> float:
    """
    Convert a float setting with fallback.
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int) -> int:
    """
    Convert an integer setting with fallback.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
