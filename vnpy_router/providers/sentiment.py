from datetime import datetime

from vnpy_router.event_storage import NewsEvent, SentimentSnapshot


class SentimentProvider:
    """
    Event/manual sentiment provider for phase 1.
    """

    name: str = "sentiment"

    def score_events(
        self,
        vt_symbol: str,
        events: list[NewsEvent],
        as_of: datetime,
    ) -> SentimentSnapshot:
        """
        Aggregate event sentiment scores.
        """
        scores: list[float] = [
            event.sentiment_score for event in events if event.sentiment_score is not None
        ]
        score: float = sum(scores) / len(scores) if scores else 0
        return SentimentSnapshot(
            vt_symbol=vt_symbol,
            as_of=as_of,
            provider_name=self.name,
            payload={
                "score": score,
                "event_count": len(events),
                "scored_event_count": len(scores),
            },
        )
