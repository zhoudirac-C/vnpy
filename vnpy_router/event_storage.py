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
    source_quality TEXT,
    trust_score DOUBLE PRECISION,
    spam_score DOUBLE PRECISION,
    dedup_window_seconds INTEGER,
    review_status TEXT,
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
    source_quality TEXT,
    trust_score DOUBLE PRECISION,
    spam_score DOUBLE PRECISION,
    dedup_window_seconds INTEGER,
    review_status TEXT,
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
    source_quality TEXT,
    trust_score DOUBLE PRECISION,
    spam_score DOUBLE PRECISION,
    dedup_window_seconds INTEGER,
    review_status TEXT,
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

CREATE TABLE IF NOT EXISTS event_quality_report (
    report_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    provider_name TEXT NOT NULL,
    as_of TIMESTAMPTZ NOT NULL,
    source_quality TEXT NOT NULL,
    trust_score DOUBLE PRECISION,
    spam_score DOUBLE PRECISION,
    duplicate_count INTEGER DEFAULT 0,
    reviewed_count INTEGER DEFAULT 0,
    blocked_count INTEGER DEFAULT 0,
    payload JSONB,
    pulled_at TIMESTAMPTZ DEFAULT now()
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
    source_quality,
    trust_score,
    spam_score,
    dedup_window_seconds,
    review_status,
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
    %(source_quality)s,
    %(trust_score)s,
    %(spam_score)s,
    %(dedup_window_seconds)s,
    %(review_status)s,
    %(raw_payload)s
)
ON CONFLICT (raw_hash) DO NOTHING;
"""


INSERT_SOCIAL_POST_RAW_SQL: str = """
INSERT INTO social_post_raw (
    raw_hash,
    source,
    author,
    url,
    content,
    published_at,
    provider_name,
    provider_version,
    source_quality,
    trust_score,
    spam_score,
    dedup_window_seconds,
    review_status,
    raw_payload
) VALUES (
    %(raw_hash)s,
    %(source)s,
    %(author)s,
    %(url)s,
    %(content)s,
    %(published_at)s,
    %(provider_name)s,
    %(provider_version)s,
    %(source_quality)s,
    %(trust_score)s,
    %(spam_score)s,
    %(dedup_window_seconds)s,
    %(review_status)s,
    %(raw_payload)s
)
ON CONFLICT (raw_hash) DO NOTHING;
"""


EVENT_SOURCE_QUALITY_MIGRATION_SQL: str = """
ALTER TABLE news_raw ADD COLUMN IF NOT EXISTS source_quality TEXT;
ALTER TABLE news_raw ADD COLUMN IF NOT EXISTS trust_score DOUBLE PRECISION;
ALTER TABLE news_raw ADD COLUMN IF NOT EXISTS spam_score DOUBLE PRECISION;
ALTER TABLE news_raw ADD COLUMN IF NOT EXISTS dedup_window_seconds INTEGER;
ALTER TABLE news_raw ADD COLUMN IF NOT EXISTS review_status TEXT;

ALTER TABLE news_event ADD COLUMN IF NOT EXISTS source_quality TEXT;
ALTER TABLE news_event ADD COLUMN IF NOT EXISTS trust_score DOUBLE PRECISION;
ALTER TABLE news_event ADD COLUMN IF NOT EXISTS spam_score DOUBLE PRECISION;
ALTER TABLE news_event ADD COLUMN IF NOT EXISTS dedup_window_seconds INTEGER;
ALTER TABLE news_event ADD COLUMN IF NOT EXISTS review_status TEXT;

ALTER TABLE social_post_raw ADD COLUMN IF NOT EXISTS source_quality TEXT;
ALTER TABLE social_post_raw ADD COLUMN IF NOT EXISTS trust_score DOUBLE PRECISION;
ALTER TABLE social_post_raw ADD COLUMN IF NOT EXISTS spam_score DOUBLE PRECISION;
ALTER TABLE social_post_raw ADD COLUMN IF NOT EXISTS dedup_window_seconds INTEGER;
ALTER TABLE social_post_raw ADD COLUMN IF NOT EXISTS review_status TEXT;

CREATE TABLE IF NOT EXISTS event_quality_report (
    report_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    provider_name TEXT NOT NULL,
    as_of TIMESTAMPTZ NOT NULL,
    source_quality TEXT NOT NULL,
    trust_score DOUBLE PRECISION,
    spam_score DOUBLE PRECISION,
    duplicate_count INTEGER DEFAULT 0,
    reviewed_count INTEGER DEFAULT 0,
    blocked_count INTEGER DEFAULT 0,
    payload JSONB,
    pulled_at TIMESTAMPTZ DEFAULT now()
);

INSERT INTO schema_version (
    namespace,
    version
) VALUES (
    'tradingagents',
    'p9'
)
ON CONFLICT (namespace)
DO UPDATE SET
    version = EXCLUDED.version,
    applied_at = now();
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
    source_quality: str = "unverified"
    trust_score: float = 0
    spam_score: float = 0
    dedup_window_seconds: int = 86400
    review_status: str = "pending"

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
    source_quality: str = "unverified"
    trust_score: float = 0
    spam_score: float = 0
    dedup_window_seconds: int = 86400
    review_status: str = "pending"


@dataclass(frozen=True)
class SocialPostRaw:
    """
    Raw social/media post before normalization and aggregation.
    """

    vt_symbol: str
    source: str
    author: str
    content: str
    published_at: datetime | None
    provider_name: str
    url: str = ""
    provider_version: str = ""
    sentiment_score: float | None = None
    label: str = ""
    raw_payload: dict[str, Any] = field(default_factory=dict)
    source_quality: str = "manual"
    trust_score: float = 0.5
    spam_score: float = 0
    dedup_window_seconds: int = 3600
    review_status: str = "pending"

    @property
    def raw_hash(self) -> str:
        """
        Stable dedup hash for raw social content.
        """
        return _hash_text(self.source, self.url, self.author, self.content)


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
        validate_source_trace(news.source, news.provider_name)
        cursor = self.connection.cursor()
        try:
            cursor.execute(INSERT_NEWS_RAW_SQL, _news_raw_params(news))
            self.connection.commit()
        finally:
            cursor.close()

    def save_social_post_raw(self, post: SocialPostRaw) -> None:
        """
        Persist one raw social post with hash deduplication.
        """
        validate_source_trace(post.source, post.provider_name)
        cursor = self.connection.cursor()
        try:
            cursor.execute(INSERT_SOCIAL_POST_RAW_SQL, _social_post_raw_params(post))
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
        "source_quality": news.source_quality,
        "trust_score": news.trust_score,
        "spam_score": news.spam_score,
        "dedup_window_seconds": news.dedup_window_seconds,
        "review_status": news.review_status,
        "raw_payload": json.dumps(news.raw_payload, ensure_ascii=False, sort_keys=True),
    }


def _social_post_raw_params(post: SocialPostRaw) -> dict[str, Any]:
    """
    Convert raw social post to SQL params.
    """
    return {
        "raw_hash": post.raw_hash,
        "source": post.source,
        "author": post.author,
        "url": post.url,
        "content": post.content,
        "published_at": post.published_at,
        "provider_name": post.provider_name,
        "provider_version": post.provider_version,
        "source_quality": post.source_quality,
        "trust_score": post.trust_score,
        "spam_score": post.spam_score,
        "dedup_window_seconds": post.dedup_window_seconds,
        "review_status": post.review_status,
        "raw_payload": json.dumps(post.raw_payload, ensure_ascii=False, sort_keys=True),
    }


def validate_source_trace(source: str, provider_name: str) -> None:
    """
    Validate source traceability before data can enter storage or context.
    """
    if not str(source).strip():
        raise ValueError("event source is required")
    if not str(provider_name).strip():
        raise ValueError("event provider_name is required")


def validate_event_for_context(event: NewsEvent) -> None:
    """
    Validate a normalized event before exposing it to TradingAgents context.
    """
    validate_source_trace(event.source, event.provider_name)


def _hash_text(*parts: str) -> str:
    """
    Hash text parts for deduplication.
    """
    raw_text: str = "\n".join(part.strip() for part in parts)
    return hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
