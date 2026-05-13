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
    relevance_score DOUBLE PRECISION,
    spam_score DOUBLE PRECISION,
    cluster_id TEXT,
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
    relevance_score DOUBLE PRECISION,
    spam_score DOUBLE PRECISION,
    cluster_id TEXT,
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
    relevance_score DOUBLE PRECISION,
    link_reason TEXT,
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

CREATE TABLE IF NOT EXISTS security_entity (
    vt_symbol TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    name TEXT NOT NULL,
    short_name TEXT,
    industry TEXT,
    sector TEXT,
    concept_tags JSONB,
    provider_name TEXT NOT NULL,
    provider_version TEXT,
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS security_alias (
    alias TEXT NOT NULL,
    vt_symbol TEXT NOT NULL,
    alias_type TEXT,
    confidence DOUBLE PRECISION,
    is_ambiguous BOOLEAN DEFAULT false,
    provider_name TEXT NOT NULL,
    provider_version TEXT,
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (alias, vt_symbol)
);

CREATE TABLE IF NOT EXISTS concept_board (
    board_id TEXT PRIMARY KEY,
    board_type TEXT NOT NULL,
    board_code TEXT NOT NULL,
    board_name TEXT NOT NULL,
    provider_name TEXT NOT NULL,
    provider_version TEXT,
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS concept_board_member (
    board_id TEXT NOT NULL,
    vt_symbol TEXT NOT NULL,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    name TEXT,
    rank INTEGER DEFAULT 0,
    provider_name TEXT NOT NULL,
    provider_version TEXT,
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (board_id, vt_symbol, provider_name)
);

CREATE TABLE IF NOT EXISTS security_concept_link (
    vt_symbol TEXT NOT NULL,
    board_id TEXT NOT NULL,
    board_name TEXT NOT NULL,
    board_type TEXT NOT NULL,
    relevance_score DOUBLE PRECISION,
    is_primary BOOLEAN DEFAULT false,
    provider_name TEXT NOT NULL,
    provider_version TEXT,
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (vt_symbol, board_id, provider_name)
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
    relevance_score,
    spam_score,
    cluster_id,
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
    %(relevance_score)s,
    %(spam_score)s,
    %(cluster_id)s,
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


UPSERT_NEWS_EVENT_SQL: str = """
INSERT INTO news_event (
    event_id,
    vt_symbol,
    title,
    summary,
    event_type,
    occurred_at,
    source,
    url,
    provider_name,
    provider_version,
    raw_hash,
    source_quality,
    trust_score,
    relevance_score,
    spam_score,
    cluster_id,
    dedup_window_seconds,
    review_status
) VALUES (
    %(event_id)s,
    %(vt_symbol)s,
    %(title)s,
    %(summary)s,
    %(event_type)s,
    %(occurred_at)s,
    %(source)s,
    %(url)s,
    %(provider_name)s,
    %(provider_version)s,
    %(raw_hash)s,
    %(source_quality)s,
    %(trust_score)s,
    %(relevance_score)s,
    %(spam_score)s,
    %(cluster_id)s,
    %(dedup_window_seconds)s,
    %(review_status)s
)
ON CONFLICT (event_id)
DO UPDATE SET
    vt_symbol = EXCLUDED.vt_symbol,
    title = EXCLUDED.title,
    summary = EXCLUDED.summary,
    event_type = EXCLUDED.event_type,
    occurred_at = EXCLUDED.occurred_at,
    source = EXCLUDED.source,
    url = EXCLUDED.url,
    provider_name = EXCLUDED.provider_name,
    provider_version = EXCLUDED.provider_version,
    raw_hash = EXCLUDED.raw_hash,
    source_quality = EXCLUDED.source_quality,
    trust_score = EXCLUDED.trust_score,
    relevance_score = EXCLUDED.relevance_score,
    spam_score = EXCLUDED.spam_score,
    cluster_id = EXCLUDED.cluster_id,
    dedup_window_seconds = EXCLUDED.dedup_window_seconds,
    review_status = EXCLUDED.review_status,
    pulled_at = now();
"""


UPSERT_SENTIMENT_SNAPSHOT_SQL: str = """
INSERT INTO sentiment_snapshot (
    vt_symbol,
    as_of,
    provider_name,
    provider_version,
    payload
) VALUES (
    %(vt_symbol)s,
    %(as_of)s,
    %(provider_name)s,
    %(provider_version)s,
    %(payload)s
)
ON CONFLICT (vt_symbol, as_of, provider_name)
DO UPDATE SET
    provider_version = EXCLUDED.provider_version,
    payload = EXCLUDED.payload,
    pulled_at = now();
"""


UPSERT_EVENT_SYMBOL_LINK_SQL: str = """
INSERT INTO event_symbol_link (
    event_id,
    vt_symbol,
    sector,
    topic,
    confidence,
    relevance_score,
    link_reason,
    provider_name,
    provider_version
) VALUES (
    %(event_id)s,
    %(vt_symbol)s,
    %(sector)s,
    %(topic)s,
    %(confidence)s,
    %(relevance_score)s,
    %(link_reason)s,
    %(provider_name)s,
    %(provider_version)s
)
ON CONFLICT (event_id, vt_symbol)
DO UPDATE SET
    sector = EXCLUDED.sector,
    topic = EXCLUDED.topic,
    confidence = EXCLUDED.confidence,
    relevance_score = EXCLUDED.relevance_score,
    link_reason = EXCLUDED.link_reason,
    provider_name = EXCLUDED.provider_name,
    provider_version = EXCLUDED.provider_version,
    pulled_at = now();
"""


UPSERT_EVENT_QUALITY_REPORT_SQL: str = """
INSERT INTO event_quality_report (
    report_id,
    source,
    provider_name,
    as_of,
    source_quality,
    trust_score,
    spam_score,
    duplicate_count,
    reviewed_count,
    blocked_count,
    payload
) VALUES (
    %(report_id)s,
    %(source)s,
    %(provider_name)s,
    %(as_of)s,
    %(source_quality)s,
    %(trust_score)s,
    %(spam_score)s,
    %(duplicate_count)s,
    %(reviewed_count)s,
    %(blocked_count)s,
    %(payload)s
)
ON CONFLICT (report_id)
DO UPDATE SET
    source = EXCLUDED.source,
    provider_name = EXCLUDED.provider_name,
    as_of = EXCLUDED.as_of,
    source_quality = EXCLUDED.source_quality,
    trust_score = EXCLUDED.trust_score,
    spam_score = EXCLUDED.spam_score,
    duplicate_count = EXCLUDED.duplicate_count,
    reviewed_count = EXCLUDED.reviewed_count,
    blocked_count = EXCLUDED.blocked_count,
    payload = EXCLUDED.payload,
    pulled_at = now();
"""


SELECT_NEWS_EVENTS_SQL: str = """
SELECT
    e.event_id,
    e.vt_symbol,
    e.title,
    e.summary,
    e.event_type,
    e.occurred_at,
    e.source,
    e.url,
    e.provider_name,
    e.provider_version,
    e.raw_hash,
    e.source_quality,
    e.trust_score,
    e.relevance_score,
    e.spam_score,
    e.cluster_id,
    e.dedup_window_seconds,
    e.review_status,
    l.confidence AS link_confidence,
    l.link_reason,
    l.sector,
    l.topic
FROM news_event e
LEFT JOIN event_symbol_link l
  ON e.event_id = l.event_id
 AND e.vt_symbol = l.vt_symbol
WHERE e.vt_symbol = %(vt_symbol)s
  AND e.occurred_at >= %(start)s
  AND e.occurred_at <= %(end)s
  AND (%(source)s = '' OR e.source = %(source)s)
  AND (%(quality_status)s = '' OR e.review_status = %(quality_status)s OR e.source_quality = %(quality_status)s)
ORDER BY e.occurred_at DESC
LIMIT %(limit)s;
"""


SELECT_SEARCH_NEWS_EVENTS_SQL: str = """
SELECT
    e.event_id,
    e.vt_symbol,
    e.title,
    e.summary,
    e.event_type,
    e.occurred_at,
    e.source,
    e.url,
    e.provider_name,
    e.provider_version,
    e.raw_hash,
    e.source_quality,
    e.trust_score,
    e.relevance_score,
    e.spam_score,
    e.cluster_id,
    e.dedup_window_seconds,
    e.review_status,
    l.confidence AS link_confidence,
    l.link_reason,
    l.sector,
    l.topic
FROM news_event e
LEFT JOIN event_symbol_link l
  ON e.event_id = l.event_id
 AND e.vt_symbol = l.vt_symbol
WHERE (
    %(keyword)s = ''
    OR LOWER(e.vt_symbol) LIKE LOWER(%(keyword_like)s)
    OR LOWER(e.title) LIKE LOWER(%(keyword_like)s)
    OR LOWER(e.summary) LIKE LOWER(%(keyword_like)s)
    OR LOWER(e.source) LIKE LOWER(%(keyword_like)s)
    OR LOWER(e.provider_name) LIKE LOWER(%(keyword_like)s)
)
  AND (%(vt_symbol)s = '' OR LOWER(e.vt_symbol) LIKE LOWER(%(vt_symbol_like)s))
  AND (%(event_type)s = '' OR e.event_type = %(event_type)s)
ORDER BY e.occurred_at DESC, e.pulled_at DESC
LIMIT %(limit)s;
"""


SELECT_SENTIMENT_SNAPSHOT_SQL: str = """
SELECT
    vt_symbol,
    as_of,
    provider_name,
    provider_version,
    payload
FROM sentiment_snapshot
WHERE vt_symbol = %(vt_symbol)s
  AND as_of <= %(as_of)s
ORDER BY as_of DESC, pulled_at DESC
LIMIT 1;
"""


EVENT_SOURCE_QUALITY_MIGRATION_SQL: str = """
ALTER TABLE news_raw ADD COLUMN IF NOT EXISTS source_quality TEXT;
ALTER TABLE news_raw ADD COLUMN IF NOT EXISTS trust_score DOUBLE PRECISION;
ALTER TABLE news_raw ADD COLUMN IF NOT EXISTS relevance_score DOUBLE PRECISION;
ALTER TABLE news_raw ADD COLUMN IF NOT EXISTS spam_score DOUBLE PRECISION;
ALTER TABLE news_raw ADD COLUMN IF NOT EXISTS cluster_id TEXT;
ALTER TABLE news_raw ADD COLUMN IF NOT EXISTS dedup_window_seconds INTEGER;
ALTER TABLE news_raw ADD COLUMN IF NOT EXISTS review_status TEXT;

ALTER TABLE news_event ADD COLUMN IF NOT EXISTS source_quality TEXT;
ALTER TABLE news_event ADD COLUMN IF NOT EXISTS trust_score DOUBLE PRECISION;
ALTER TABLE news_event ADD COLUMN IF NOT EXISTS relevance_score DOUBLE PRECISION;
ALTER TABLE news_event ADD COLUMN IF NOT EXISTS spam_score DOUBLE PRECISION;
ALTER TABLE news_event ADD COLUMN IF NOT EXISTS cluster_id TEXT;
ALTER TABLE news_event ADD COLUMN IF NOT EXISTS dedup_window_seconds INTEGER;
ALTER TABLE news_event ADD COLUMN IF NOT EXISTS review_status TEXT;

ALTER TABLE event_symbol_link ADD COLUMN IF NOT EXISTS relevance_score DOUBLE PRECISION;
ALTER TABLE event_symbol_link ADD COLUMN IF NOT EXISTS link_reason TEXT;

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

CREATE TABLE IF NOT EXISTS security_entity (
    vt_symbol TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    name TEXT NOT NULL,
    short_name TEXT,
    industry TEXT,
    sector TEXT,
    concept_tags JSONB,
    provider_name TEXT NOT NULL,
    provider_version TEXT,
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS security_alias (
    alias TEXT NOT NULL,
    vt_symbol TEXT NOT NULL,
    alias_type TEXT,
    confidence DOUBLE PRECISION,
    is_ambiguous BOOLEAN DEFAULT false,
    provider_name TEXT NOT NULL,
    provider_version TEXT,
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (alias, vt_symbol)
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
    relevance_score: float = 0
    spam_score: float = 0
    cluster_id: str = ""
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
    relevance_score: float = 0
    spam_score: float = 0
    cluster_id: str = ""
    link_confidence: float = 0
    link_reason: str = ""
    sector: str = ""
    topic: str = ""
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


@dataclass(frozen=True)
class EventSymbolLink:
    """
    Symbol/entity link for one normalized event.
    """

    event_id: str
    vt_symbol: str
    provider_name: str
    sector: str = ""
    topic: str = ""
    confidence: float = 0
    relevance_score: float = 0
    link_reason: str = ""
    provider_version: str = ""


@dataclass(frozen=True)
class EventQualityReport:
    """
    Quality report for one provider run or event cluster.
    """

    report_id: str
    source: str
    provider_name: str
    as_of: datetime
    source_quality: str
    trust_score: float = 0
    spam_score: float = 0
    duplicate_count: int = 0
    reviewed_count: int = 0
    blocked_count: int = 0
    payload: dict[str, Any] = field(default_factory=dict)


class Cursor(Protocol):
    """
    Minimal DB-API cursor protocol.
    """

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> None:
        pass

    def close(self) -> None:
        pass

    def fetchall(self) -> list[dict[str, Any]]:
        pass

    def fetchone(self) -> dict[str, Any] | None:
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

    def save_news_event(self, event: NewsEvent) -> None:
        """
        Persist one normalized news/announcement/social event.
        """
        validate_event_for_context(event)
        cursor = self.connection.cursor()
        try:
            cursor.execute(UPSERT_NEWS_EVENT_SQL, _news_event_params(event))
            self.connection.commit()
        finally:
            cursor.close()

    def save_sentiment_snapshot(self, snapshot: SentimentSnapshot) -> None:
        """
        Persist one aggregated sentiment snapshot.
        """
        validate_source_trace("sentiment", snapshot.provider_name)
        cursor = self.connection.cursor()
        try:
            cursor.execute(UPSERT_SENTIMENT_SNAPSHOT_SQL, _sentiment_snapshot_params(snapshot))
            self.connection.commit()
        finally:
            cursor.close()

    def save_event_symbol_link(self, link: EventSymbolLink) -> None:
        """
        Persist one symbol/entity link for a normalized event.
        """
        validate_source_trace(link.vt_symbol, link.provider_name)
        cursor = self.connection.cursor()
        try:
            cursor.execute(UPSERT_EVENT_SYMBOL_LINK_SQL, _event_symbol_link_params(link))
            self.connection.commit()
        finally:
            cursor.close()

    def save_event_quality_report(self, report: EventQualityReport) -> None:
        """
        Persist one event quality report.
        """
        validate_source_trace(report.source, report.provider_name)
        cursor = self.connection.cursor()
        try:
            cursor.execute(UPSERT_EVENT_QUALITY_REPORT_SQL, _event_quality_report_params(report))
            self.connection.commit()
        finally:
            cursor.close()

    def load_news_events(
        self,
        vt_symbol: str,
        start: datetime,
        end: datetime,
        source: str = "",
        quality_status: str = "",
        limit: int = 50,
    ) -> list[NewsEvent]:
        """
        Load normalized events for a symbol/time window.
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                SELECT_NEWS_EVENTS_SQL,
                {
                    "vt_symbol": vt_symbol,
                    "start": start,
                    "end": end,
                    "source": source,
                    "quality_status": quality_status,
                    "limit": limit,
                },
            )
            return [_news_event_from_row(row) for row in cursor.fetchall()]
        finally:
            cursor.close()

    def search_news_events(
        self,
        keyword: str = "",
        vt_symbol: str = "",
        event_type: str = "",
        limit: int = 100,
    ) -> list[NewsEvent]:
        """
        Fuzzy-search normalized news events for the TradingAgents UI.
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                SELECT_SEARCH_NEWS_EVENTS_SQL,
                {
                    "keyword": keyword.strip(),
                    "keyword_like": _like_pattern(keyword),
                    "vt_symbol": vt_symbol.strip(),
                    "vt_symbol_like": _like_pattern(vt_symbol),
                    "event_type": event_type.strip(),
                    "limit": max(1, min(int(limit), 1000)),
                },
            )
            return [_news_event_from_row(row) for row in cursor.fetchall()]
        finally:
            cursor.close()

    def load_sentiment_snapshot(
        self,
        vt_symbol: str,
        as_of: datetime,
    ) -> SentimentSnapshot | None:
        """
        Load the latest sentiment snapshot at or before as_of.
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                SELECT_SENTIMENT_SNAPSHOT_SQL,
                {
                    "vt_symbol": vt_symbol,
                    "as_of": as_of,
                },
            )
            row = cursor.fetchone()
            if not row:
                return None
            return _sentiment_snapshot_from_row(row)
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
        "relevance_score": news.relevance_score,
        "spam_score": news.spam_score,
        "cluster_id": news.cluster_id,
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


def _news_event_params(event: NewsEvent) -> dict[str, Any]:
    """
    Convert a normalized event to SQL params.
    """
    return {
        "event_id": event.event_id,
        "vt_symbol": event.vt_symbol,
        "title": event.title,
        "summary": event.summary,
        "event_type": event.event_type,
        "occurred_at": event.occurred_at,
        "source": event.source,
        "url": event.url,
        "provider_name": event.provider_name,
        "provider_version": event.provider_version,
        "raw_hash": event.raw_hash,
        "source_quality": event.source_quality,
        "trust_score": event.trust_score,
        "relevance_score": event.relevance_score,
        "spam_score": event.spam_score,
        "cluster_id": event.cluster_id,
        "dedup_window_seconds": event.dedup_window_seconds,
        "review_status": event.review_status,
    }


def _sentiment_snapshot_params(snapshot: SentimentSnapshot) -> dict[str, Any]:
    """
    Convert sentiment snapshot to SQL params.
    """
    return {
        "vt_symbol": snapshot.vt_symbol,
        "as_of": snapshot.as_of,
        "provider_name": snapshot.provider_name,
        "provider_version": snapshot.provider_version,
        "payload": json.dumps(snapshot.payload, ensure_ascii=False, sort_keys=True),
    }


def _event_symbol_link_params(link: EventSymbolLink) -> dict[str, Any]:
    """
    Convert event symbol link to SQL params.
    """
    return {
        "event_id": link.event_id,
        "vt_symbol": link.vt_symbol,
        "sector": link.sector,
        "topic": link.topic,
        "confidence": link.confidence,
        "relevance_score": link.relevance_score,
        "link_reason": link.link_reason,
        "provider_name": link.provider_name,
        "provider_version": link.provider_version,
    }


def _event_quality_report_params(report: EventQualityReport) -> dict[str, Any]:
    """
    Convert event quality report to SQL params.
    """
    return {
        "report_id": report.report_id,
        "source": report.source,
        "provider_name": report.provider_name,
        "as_of": report.as_of,
        "source_quality": report.source_quality,
        "trust_score": report.trust_score,
        "spam_score": report.spam_score,
        "duplicate_count": report.duplicate_count,
        "reviewed_count": report.reviewed_count,
        "blocked_count": report.blocked_count,
        "payload": json.dumps(report.payload, ensure_ascii=False, sort_keys=True),
    }


def _news_event_from_row(row: dict[str, Any]) -> NewsEvent:
    """
    Convert SQL row into NewsEvent.
    """
    return NewsEvent(
        event_id=str(row["event_id"]),
        vt_symbol=str(row["vt_symbol"]),
        title=str(row["title"]),
        summary=str(row["summary"]),
        event_type=str(row["event_type"]),
        occurred_at=row["occurred_at"],
        source=str(row["source"]),
        provider_name=str(row["provider_name"]),
        url=str(row.get("url") or ""),
        provider_version=str(row.get("provider_version") or ""),
        raw_hash=str(row.get("raw_hash") or ""),
        source_quality=str(row.get("source_quality") or "unverified"),
        trust_score=float(row.get("trust_score") or 0),
        relevance_score=float(row.get("relevance_score") or 0),
        spam_score=float(row.get("spam_score") or 0),
        cluster_id=str(row.get("cluster_id") or ""),
        link_confidence=float(row.get("link_confidence") or 0),
        link_reason=str(row.get("link_reason") or ""),
        sector=str(row.get("sector") or ""),
        topic=str(row.get("topic") or ""),
        dedup_window_seconds=int(row.get("dedup_window_seconds") or 86400),
        review_status=str(row.get("review_status") or "pending"),
    )


def _like_pattern(value: str) -> str:
    """
    Build a simple SQL LIKE pattern for UI fuzzy search.
    """
    text = value.strip()
    if not text:
        return "%%"
    return f"%{text}%"


def _sentiment_snapshot_from_row(row: dict[str, Any]) -> SentimentSnapshot:
    """
    Convert SQL row into SentimentSnapshot.
    """
    payload = row.get("payload") or {}
    if isinstance(payload, str):
        payload = json.loads(payload)
    return SentimentSnapshot(
        vt_symbol=str(row["vt_symbol"]),
        as_of=row["as_of"],
        provider_name=str(row["provider_name"]),
        provider_version=str(row.get("provider_version") or ""),
        payload=dict(payload),
    )


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
