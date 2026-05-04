import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from vnpy_router.event_storage import NewsEvent


def load_event_file(path: str | Path, provider_name: str) -> list[NewsEvent]:
    """
    Load manual event records from JSON or CSV.
    """
    file_path = Path(path)
    if file_path.suffix.lower() == ".json":
        rows: list[dict[str, Any]] = json.loads(file_path.read_text(encoding="utf-8"))
    else:
        with file_path.open("r", encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))

    return [_row_to_event(row, provider_name, file_path, index) for index, row in enumerate(rows)]


def _row_to_event(
    row: dict[str, Any],
    provider_name: str,
    file_path: Path,
    index: int,
) -> NewsEvent:
    """
    Convert one file row into NewsEvent.
    """
    vt_symbol: str = str(row["vt_symbol"])
    occurred_at: str = str(row["occurred_at"])
    event_id: str = str(row.get("event_id") or f"{provider_name}:{vt_symbol}:{index}")
    sentiment_score_raw: Any = row.get("sentiment_score")
    sentiment_score = float(sentiment_score_raw) if sentiment_score_raw not in {"", None} else None
    return NewsEvent(
        event_id=event_id,
        vt_symbol=vt_symbol,
        title=str(row["title"]),
        summary=str(row.get("summary") or row["title"]),
        event_type=str(row.get("event_type") or "news"),
        occurred_at=datetime.fromisoformat(occurred_at),
        source=str(row.get("source") or "local_file"),
        provider_name=provider_name,
        url=str(row.get("url") or f"file://{file_path}#{index}"),
        provider_version=str(row.get("provider_version") or ""),
        sentiment_score=sentiment_score,
        source_quality=str(row.get("source_quality") or "manual"),
        trust_score=_optional_float(row.get("trust_score"), default=0.5),
        spam_score=_optional_float(row.get("spam_score"), default=0),
        dedup_window_seconds=int(row.get("dedup_window_seconds") or 86400),
        review_status=str(row.get("review_status") or "pending"),
    )


def _optional_float(value: Any, default: float) -> float:
    """
    Parse optional float values from local event files.
    """
    if value in {"", None}:
        return default
    return float(value)
