"""
News duplicate clustering helpers.
"""

import re
from dataclasses import dataclass

from vnpy_router.event_storage import NewsRaw


@dataclass(frozen=True)
class DedupResult:
    """
    Dedup registration result.
    """

    cluster_id: str
    is_duplicate: bool
    duplicate_count: int = 0


class NewsDeduper:
    """
    In-memory deduper for one ingestion run.
    """

    def __init__(self) -> None:
        """"""
        self.counts: dict[str, int] = {}

    def register(self, news: NewsRaw, vt_symbol: str = "") -> DedupResult:
        """
        Register one raw/link pair and return its cluster.
        """
        cluster_id = self.cluster_key(news, vt_symbol)
        count = self.counts.get(cluster_id, 0) + 1
        self.counts[cluster_id] = count
        return DedupResult(
            cluster_id=cluster_id,
            is_duplicate=count > 1,
            duplicate_count=count - 1,
        )

    def cluster_key(self, news: NewsRaw, vt_symbol: str = "") -> str:
        """
        Build a stable cluster key across providers.
        """
        code = _payload_code(news) or vt_symbol
        date = news.published_at.date().isoformat() if news.published_at else ""
        title = _normalize_title(news.title)
        return f"title:{code}:{date}:{title}"


def _payload_code(news: NewsRaw) -> str:
    """
    Extract a provider payload code for dedup clustering.
    """
    for key in ("secCode", "securityCode", "SECURITY_CODE", "symbol", "code", "证券代码"):
        value = news.raw_payload.get(key)
        if value:
            return str(value).strip().upper()
    return ""


def _normalize_title(title: str) -> str:
    """
    Normalize a title enough to merge official duplicates.
    """
    text = re.sub(r"\s+", "", title.upper())
    text = re.sub(r"[：:，,。．.（）()【】\\[\\]《》<>\\-_/]", "", text)
    return text

