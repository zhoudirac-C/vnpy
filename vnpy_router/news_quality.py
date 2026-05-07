"""
Production scoring and filtering rules for news events.
"""

from dataclasses import dataclass

from vnpy_router.event_storage import NewsRaw


SOURCE_BASE_TRUST: dict[str, float] = {
    "official_disclosure": 0.95,
    "global_public_news": 0.65,
    "public_web": 0.50,
    "manual": 0.80,
    "reviewed": 0.85,
}


@dataclass(frozen=True)
class NewsQualityAssessment:
    """
    Quality outcome for one candidate event.
    """

    trust_score: float
    relevance_score: float
    spam_score: float
    review_status: str
    reason: str = ""


class NewsQualityScorer:
    """
    Score trust, relevance and spam risk before events enter context.
    """

    def score(
        self,
        news: NewsRaw,
        link_confidence: float,
        event_type: str,
        duplicate: bool = False,
    ) -> NewsQualityAssessment:
        """
        Score one news/link candidate.
        """
        if duplicate:
            return NewsQualityAssessment(
                trust_score=max(news.trust_score, _base_trust(news)) * 0.8,
                relevance_score=link_confidence,
                spam_score=max(news.spam_score, 0.1),
                review_status="duplicate",
                reason="duplicate_cluster",
            )

        base = max(float(news.trust_score or 0), _base_trust(news))
        spam = float(news.spam_score or 0)
        reason = "accepted"

        if not news.title.strip() or not news.source.strip() or not news.provider_name.strip():
            return NewsQualityAssessment(0, 0, 1, "blocked", "missing_trace")
        if not news.url and news.source_quality != "manual":
            base -= 0.08
            reason = "missing_url"
        if not news.content.strip() or news.content.strip() == news.title.strip():
            spam = max(spam, 0.35)
            base -= 0.05
            reason = "thin_content"
        if event_type == "news" and news.source_quality == "public_web":
            base -= 0.05

        trust = _clamp(base)
        relevance = _clamp(link_confidence)
        if spam >= 0.7:
            status = "blocked"
        elif trust >= 0.7 and relevance >= 0.75:
            status = "accepted"
        else:
            status = "pending"

        return NewsQualityAssessment(
            trust_score=trust,
            relevance_score=relevance,
            spam_score=_clamp(spam),
            review_status=status,
            reason=reason,
        )


def _base_trust(news: NewsRaw) -> float:
    """
    Return source-quality baseline trust.
    """
    return SOURCE_BASE_TRUST.get(news.source_quality, 0.35)


def _clamp(value: float) -> float:
    """
    Clamp score into 0..1.
    """
    return max(0.0, min(1.0, value))
