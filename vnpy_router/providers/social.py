import csv
import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from vnpy_router.event_storage import SentimentSnapshot, SocialPostRaw


class SocialProvider:
    """
    Local/manual social sentiment provider.
    """

    name: str = "social"

    def __init__(self, source_path: str | Path) -> None:
        """"""
        self.source_path: Path = Path(source_path)

    def query_posts(
        self,
        vt_symbol: str,
        output: Callable = print,
    ) -> list[SocialPostRaw]:
        """
        Return social posts for one symbol, degrading when the optional file is missing.
        """
        if not self.source_path.exists():
            output(f"SocialProvider missing optional source file: {self.source_path}")
            return []

        posts: list[SocialPostRaw] = _load_posts(self.source_path, self.name)
        return [post for post in posts if post.vt_symbol == vt_symbol]

    def score_posts(
        self,
        vt_symbol: str,
        posts: list[SocialPostRaw],
        as_of: datetime,
    ) -> SentimentSnapshot:
        """
        Aggregate local/manual social posts into one sentiment snapshot.
        """
        scores: list[float] = [
            post.sentiment_score for post in posts if post.sentiment_score is not None
        ]
        labels: dict[str, int] = {}
        for post in posts:
            if post.label:
                labels[post.label] = labels.get(post.label, 0) + 1

        score: float = sum(scores) / len(scores) if scores else 0
        return SentimentSnapshot(
            vt_symbol=vt_symbol,
            as_of=as_of,
            provider_name=self.name,
            payload={
                "score": score,
                "post_count": len(posts),
                "scored_post_count": len(scores),
                "labels": labels,
            },
        )


def _load_posts(path: Path, provider_name: str) -> list[SocialPostRaw]:
    """
    Load manual social posts from JSON or CSV.
    """
    if path.suffix.lower() == ".json":
        rows: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    else:
        with path.open("r", encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))

    return [_row_to_post(row, provider_name, path, index) for index, row in enumerate(rows)]


def _row_to_post(
    row: dict[str, Any],
    provider_name: str,
    path: Path,
    index: int,
) -> SocialPostRaw:
    """
    Convert one local/manual social row into SocialPostRaw.
    """
    published_at = str(row.get("published_at") or "")
    sentiment_score = _optional_float(row.get("sentiment_score"))
    return SocialPostRaw(
        vt_symbol=str(row["vt_symbol"]),
        source=str(row.get("source") or "manual"),
        author=str(row.get("author") or ""),
        content=str(row["content"]),
        published_at=datetime.fromisoformat(published_at) if published_at else None,
        provider_name=provider_name,
        url=str(row.get("url") or f"file://{path}#{index}"),
        provider_version=str(row.get("provider_version") or ""),
        sentiment_score=sentiment_score,
        label=str(row.get("label") or ""),
        raw_payload=dict(row),
        source_quality=str(row.get("source_quality") or "manual"),
        trust_score=_optional_float(row.get("trust_score"), default=0.5) or 0,
        spam_score=_optional_float(row.get("spam_score"), default=0) or 0,
        dedup_window_seconds=int(row.get("dedup_window_seconds") or 3600),
        review_status=str(row.get("review_status") or "pending"),
    )


def _optional_float(value: Any, default: float | None = None) -> float | None:
    """
    Parse optional float values from local social files.
    """
    if value in {"", None}:
        return default
    return float(value)
