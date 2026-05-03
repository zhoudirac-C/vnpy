import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


EVENT_SCHEMA: str = """
CREATE TABLE IF NOT EXISTS news_raw (
    raw_hash TEXT NOT NULL PRIMARY KEY,
    source TEXT NOT NULL,
    url TEXT,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    published_at TIMESTAMPTZ,
    provider_name TEXT NOT NULL,
    provider_version TEXT,
    pulled_at TIMESTAMPTZ DEFAULT now(),
    raw_payload JSONB
);

CREATE TABLE IF NOT EXISTS news_event (
    event_id TEXT PRIMARY KEY,
    vt_symbol TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    event_type TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    source TEXT NOT NULL,
    url TEXT,
    provider_name TEXT NOT NULL,
    provider_version TEXT,
    raw_hash TEXT,
    pulled_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS social_post_raw (
    raw_hash TEXT NOT NULL PRIMARY KEY,
    source TEXT NOT NULL,
    author TEXT,
    url TEXT,
    content TEXT NOT NULL,
    published_at TIMESTAMPTZ,
    provider_name TEXT NOT NULL,
    provider_version TEXT,
    pulled_at TIMESTAMPTZ DEFAULT now(),
    raw_payload JSONB
);

CREATE TABLE IF NOT EXISTS sentiment_snapshot (
    vt_symbol TEXT NOT NULL,
    as_of TIMESTAMPTZ NOT NULL,
    provider_name TEXT NOT NULL,
    provider_version TEXT,
    payload JSONB NOT NULL,
    pulled_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (vt_symbol, as_of, provider_name)
);

CREATE TABLE IF NOT EXISTS event_symbol_link (
    event_id TEXT NOT NULL,
    vt_symbol TEXT NOT NULL,
    sector TEXT,
    topic TEXT,
    confidence DOUBLE PRECISION,
    provider_name TEXT NOT NULL,
    provider_version TEXT,
    pulled_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (event_id, vt_symbol)
);
"""


INSERT_NEWS_RAW_SQL: str = """
INSERT INTO news_raw (
    raw_hash,
    source,
    url,
    title,
    content,
    published_at,
    provider_name,
    provider_version,
    raw_payload
) VALUES (
    %(raw_hash)s,
    %(source)s,
    %(url)s,
    %(title)s,
    %(content)s,
    %(published_at)s,
    %(provider_name)s,
    %(provider_version)s,
    %(raw_payload)s
)
ON CONFLICT (raw_hash) DO NOTHING;
"""


@dataclass(frozen=True)
class NewsRaw:
    """
    Raw news record before normalization.
    """

    source: str
    url: str
    title: str
    content: str
    published_at: datetime | None
    provider_name: str
    provider_version: str = ""
    raw_payload: dict[str, Any] = field(default_factory=dict)

    @property
    def raw_hash(self) -> str:
        """
        Stable dedup hash for raw text.
        """
        return _hash_text(self.source, self.url, self.title, self.content)


@dataclass(frozen=True)
class NewsEvent:
    """
    Normalized news/announcement event linked to a symbol.
    """

    event_id: str
    vt_symbol: str
    title: str
    summary: str
    event_type: str
    occurred_at: datetime
    source: str
    provider_name: str
    url: str = ""
    provider_version: str = ""
    raw_hash: str = ""
    sentiment_score: float | None = None


@dataclass(frozen=True)
class SentimentSnapshot:
    """
    Aggregated sentiment snapshot.
    """

    vt_symbol: str
    as_of: datetime
    provider_name: str
    payload: dict[str, Any]
    provider_version: str = ""


class Cursor(Protocol):
    """
    Minimal DB-API cursor protocol.
    """

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> None:
        pass

    def close(self) -> None:
        pass


class Connection(Protocol):
    """
    Minimal DB-API connection protocol.
    """

    def cursor(self) -> Cursor:
        pass

    def commit(self) -> None:
        pass


class PostgresEventStorage:
    """
    PostgreSQL storage for event/news/sentiment pipeline.
    """

    def __init__(self, connection: Connection) -> None:
        """"""
        self.connection: Connection = connection

    def create_schema(self) -> None:
        """
        Create event pipeline tables.
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(EVENT_SCHEMA)
            self.connection.commit()
        finally:
            cursor.close()

    def save_news_raw(self, news: NewsRaw) -> None:
        """
        Persist one raw news item with hash deduplication.
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(INSERT_NEWS_RAW_SQL, _news_raw_params(news))
            self.connection.commit()
        finally:
            cursor.close()


def _news_raw_params(news: NewsRaw) -> dict[str, Any]:
    """
    Convert raw news to SQL params.
    """
    return {
        "raw_hash": news.raw_hash,
        "source": news.source,
        "url": news.url,
        "title": news.title,
        "content": news.content,
        "published_at": news.published_at,
        "provider_name": news.provider_name,
        "provider_version": news.provider_version,
        "raw_payload": json.dumps(news.raw_payload, ensure_ascii=False, sort_keys=True),
    }


def _hash_text(*parts: str) -> str:
    """
    Hash text parts for deduplication.
    """
    raw_text: str = "\n".join(part.strip() for part in parts)
    return hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
