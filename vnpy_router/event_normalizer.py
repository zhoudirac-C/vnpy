from typing import Any

from .event_storage import NewsEvent, SentimentSnapshot, validate_event_for_context


class EventNormalizer:
    """
    Build compact event snapshots for TradingAgents contexts.
    """

    def build_news_snapshot(
        self,
        vt_symbol: str,
        events: list[NewsEvent],
    ) -> dict[str, Any]:
        """
        Convert normalized events into a symbol-scoped news snapshot.
        """
        return {
            "vt_symbol": vt_symbol,
            "event_count": len(events),
            "events": [_event_to_context(event) for event in events],
        }

    def build_sentiment_snapshot(
        self,
        snapshot: SentimentSnapshot,
    ) -> dict[str, Any]:
        """
        Convert sentiment payload into a traceable snapshot.
        """
        payload: dict[str, Any] = dict(snapshot.payload)
        payload["_snapshot_type"] = "sentiment"
        payload["_provider_name"] = snapshot.provider_name
        payload["_provider_version"] = snapshot.provider_version
        payload["_as_of"] = snapshot.as_of.isoformat()
        payload["_vt_symbol"] = snapshot.vt_symbol
        return payload


def _event_to_context(event: NewsEvent) -> dict[str, Any]:
    """
    Convert one news event into a TradingAgents-readable context row.
    """
    validate_event_for_context(event)
    context: dict[str, Any] = {
        "event_id": event.event_id,
        "vt_symbol": event.vt_symbol,
        "title": event.title,
        "summary": event.summary,
        "event_type": event.event_type,
        "occurred_at": event.occurred_at.isoformat(),
        "source": event.source,
        "url": event.url,
        "provider_name": event.provider_name,
        "provider_version": event.provider_version,
        "raw_hash": event.raw_hash,
        "source_quality": event.source_quality,
        "trust_score": event.trust_score,
        "spam_score": event.spam_score,
        "dedup_window_seconds": event.dedup_window_seconds,
        "review_status": event.review_status,
    }
    if event.sentiment_score is not None:
        context["sentiment_score"] = event.sentiment_score
    return context
