from datetime import datetime


def test_event_storage_schema_contains_news_social_sentiment_tables():
    """Event storage schema should cover raw/news/social/sentiment/link tables."""
    from vnpy_router.event_storage import EVENT_SCHEMA

    for table in [
        "news_raw",
        "news_event",
        "social_post_raw",
        "sentiment_snapshot",
        "event_symbol_link",
    ]:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in EVENT_SCHEMA

    assert "raw_hash TEXT NOT NULL" in EVENT_SCHEMA
    assert "provider_version TEXT" in EVENT_SCHEMA
    assert "source TEXT NOT NULL" in EVENT_SCHEMA
    assert "pulled_at TIMESTAMPTZ DEFAULT now()" in EVENT_SCHEMA


def test_event_storage_saves_news_raw_with_hash_dedup():
    """PostgresEventStorage should persist raw news with a stable hash."""
    from vnpy_router.event_storage import NewsRaw, PostgresEventStorage

    connection = FakeConnection()
    storage = PostgresEventStorage(connection)
    news = NewsRaw(
        source="local",
        url="file://news.json#1",
        title="贵州茅台公告",
        content="公告内容",
        published_at=datetime(2024, 1, 3),
        provider_name="local_json",
        provider_version="v1",
    )

    storage.save_news_raw(news)

    sql, params = connection.cursor_obj.executed[0]
    assert "INSERT INTO news_raw" in sql
    assert params["raw_hash"]
    assert params["source"] == "local"
    assert connection.committed


def test_announcement_provider_generates_news_event_from_json(tmp_path):
    """AnnouncementProvider should turn local manual events into news_event records."""
    from vnpy_router.providers.announcement import AnnouncementProvider

    path = tmp_path / "events.json"
    path.write_text(
        """
        [
          {
            "vt_symbol": "600519.SSE",
            "title": "年度分红公告",
            "summary": "现金分红预案",
            "event_type": "announcement",
            "occurred_at": "2024-01-03T09:00:00"
          }
        ]
        """,
        encoding="utf-8",
    )

    events = AnnouncementProvider(path).query_events("600519.SSE")

    assert len(events) == 1
    assert events[0].vt_symbol == "600519.SSE"
    assert events[0].event_type == "announcement"


def test_news_and_sentiment_providers_build_events_and_scores(tmp_path):
    """NewsProvider and SentimentProvider should create event and sentiment snapshots."""
    from vnpy_router.providers.news import NewsProvider
    from vnpy_router.providers.sentiment import SentimentProvider

    path = tmp_path / "news.csv"
    path.write_text(
        "\n".join(
            [
                "vt_symbol,title,summary,event_type,occurred_at,sentiment_score",
                "600519.SSE,行业新闻,白酒板块回暖,industry,2024-01-03T10:00:00,0.6",
            ]
        ),
        encoding="utf-8",
    )

    events = NewsProvider(path).query_events("600519.SSE")
    snapshot = SentimentProvider().score_events("600519.SSE", events, datetime(2024, 1, 3))

    assert events[0].event_type == "industry"
    assert snapshot.vt_symbol == "600519.SSE"
    assert snapshot.payload["score"] == 0.6
    assert snapshot.payload["event_count"] == 1


def test_event_normalizer_builds_tradingagents_news_context():
    """EventNormalizer should output compact context for TradingAgents."""
    from vnpy_router.event_normalizer import EventNormalizer
    from vnpy_router.event_storage import NewsEvent, SentimentSnapshot

    normalizer = EventNormalizer()
    event = NewsEvent(
        event_id="event-1",
        vt_symbol="600519.SSE",
        title="公告",
        summary="现金分红",
        event_type="announcement",
        occurred_at=datetime(2024, 1, 3),
        source="local",
        provider_name="local_json",
    )
    sentiment = SentimentSnapshot(
        vt_symbol="600519.SSE",
        as_of=datetime(2024, 1, 3),
        provider_name="manual",
        payload={"score": 0.2},
    )

    news_context = normalizer.build_news_snapshot("600519.SSE", [event])
    sentiment_context = normalizer.build_sentiment_snapshot(sentiment)

    assert news_context["events"][0]["title"] == "公告"
    assert sentiment_context["score"] == 0.2


def test_toolkit_degrades_when_news_and_sentiment_missing():
    """MarketDataToolkit should keep market context when event sources are missing."""
    from vnpy_tradingagents.toolkit import MarketDataToolkit, SnapshotQuery

    context = MarketDataToolkit(MissingEventReader()).build_context(
        SnapshotQuery(
            vt_symbol="600519.SSE",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 3),
        )
    )

    assert context["market"]["bars"]
    assert "news" in context["degraded_sources"]
    assert "sentiment" in context["degraded_sources"]


def test_composite_snapshot_reader_feeds_news_events_to_tradingagents_context():
    """Manual TradingAgents analysis should read normalized news_event rows."""
    from vnpy_router.event_storage import NewsEvent, SentimentSnapshot
    from vnpy_tradingagents.toolkit import (
        CompositeSnapshotReader,
        MarketDataToolkit,
        SnapshotQuery,
    )

    reader = CompositeSnapshotReader(
        snapshot_reader=MissingEventReader(),
        event_reader=MemoryNewsEventReader(
            events=[
                NewsEvent(
                    event_id="event-1",
                    vt_symbol="002636.SZSE",
                    title="金安国纪分红公告",
                    summary="现金分红预案",
                    event_type="announcement",
                    occurred_at=datetime(2026, 4, 29),
                    source="cninfo",
                    provider_name="cninfo_announcement",
                    source_quality="official_disclosure",
                    trust_score=0.95,
                    relevance_score=0.8,
                    link_confidence=0.9,
                    review_status="accepted",
                )
            ],
            sentiment=SentimentSnapshot(
                vt_symbol="002636.SZSE",
                as_of=datetime(2026, 4, 29),
                provider_name="manual",
                payload={"score": 0.3},
            ),
        ),
    )

    context = MarketDataToolkit(reader).build_context(
        SnapshotQuery(
            vt_symbol="002636.SZSE",
            start=datetime(2026, 4, 1),
            end=datetime(2026, 5, 9),
        )
    )

    assert context["news"]["events"][0]["title"] == "金安国纪分红公告"
    assert context["data_quality"]["news_event_count"] == 1
    assert context["sentiment"]["score"] == 0.3
    assert "news" not in context["degraded_sources"]


def test_build_news_context_filter_uses_ui_settings():
    """TradingAgents news filters should respect vn.py UI configuration."""
    from vnpy_tradingagents.toolkit import build_news_context_filter

    news_filter = build_news_context_filter(
        {
            "news.filter.min_trust_score": 0.2,
            "news.filter.min_link_confidence": 0.3,
            "news.filter.max_items_per_symbol": 7,
            "news.filter.allowed_event_types": "announcement,news,macro",
        }
    )

    assert news_filter.min_trust_score == 0.2
    assert news_filter.min_link_confidence == 0.3
    assert news_filter.max_items == 7
    assert news_filter.allowed_event_types == frozenset({"announcement", "news", "macro"})


def test_postgres_event_storage_saves_and_loads_normalized_context_rows():
    """Event storage should expose normalized events and sentiment to Toolkit."""
    from vnpy_router.event_storage import (
        NewsEvent,
        PostgresEventStorage,
        SentimentSnapshot,
    )

    connection = EventConnection(
        fetchall_result=[
            {
                "event_id": "event-1",
                "vt_symbol": "600519.SSE",
                "title": "公告",
                "summary": "业绩增长",
                "event_type": "announcement",
                "occurred_at": datetime(2024, 1, 3),
                "source": "sse",
                "provider_name": "manual",
                "url": "",
                "provider_version": "",
                "raw_hash": "hash-1",
                "source_quality": "reviewed",
                "trust_score": 0.9,
                "spam_score": 0,
                "dedup_window_seconds": 86400,
                "review_status": "reviewed",
            }
        ],
        fetchone_result={
            "vt_symbol": "600519.SSE",
            "as_of": datetime(2024, 1, 3),
            "provider_name": "manual",
            "provider_version": "v1",
            "payload": {"score": 0.2},
        },
    )
    storage = PostgresEventStorage(connection)
    storage.save_news_event(
        NewsEvent(
            event_id="event-1",
            vt_symbol="600519.SSE",
            title="公告",
            summary="业绩增长",
            event_type="announcement",
            occurred_at=datetime(2024, 1, 3),
            source="sse",
            provider_name="manual",
        )
    )
    storage.save_sentiment_snapshot(
        SentimentSnapshot(
            vt_symbol="600519.SSE",
            as_of=datetime(2024, 1, 3),
            provider_name="manual",
            provider_version="v1",
            payload={"score": 0.2},
        )
    )

    events = storage.load_news_events(
        "600519.SSE",
        datetime(2024, 1, 1),
        datetime(2024, 1, 4),
    )
    sentiment = storage.load_sentiment_snapshot("600519.SSE", datetime(2024, 1, 4))

    executed_sql = "\n".join(sql for sql, _ in connection.cursor_obj.executed)
    assert "INSERT INTO news_event" in executed_sql
    assert "INSERT INTO sentiment_snapshot" in executed_sql
    assert events[0].title == "公告"
    assert sentiment is not None
    assert sentiment.payload["score"] == 0.2


def test_postgres_event_storage_searches_news_events_by_keyword_and_symbol():
    """News event storage should support UI fuzzy search over normalized events."""
    from vnpy_router.event_storage import PostgresEventStorage

    connection = EventConnection(
        fetchall_result=[
            {
                "event_id": "event-1",
                "vt_symbol": "600519.SSE",
                "title": "贵州茅台分红公告",
                "summary": "现金分红预案",
                "event_type": "announcement",
                "occurred_at": datetime(2024, 1, 3),
                "source": "cninfo",
                "provider_name": "manual",
                "url": "https://example.test/1",
                "provider_version": "",
                "raw_hash": "hash-1",
                "source_quality": "official",
                "trust_score": 0.95,
                "relevance_score": 0.8,
                "spam_score": 0,
                "dedup_window_seconds": 86400,
                "review_status": "accepted",
                "link_confidence": 0.9,
                "link_reason": "text_name",
                "sector": "消费",
                "topic": "白酒",
            }
        ]
    )
    storage = PostgresEventStorage(connection)

    events = storage.search_news_events(
        keyword="分红",
        vt_symbol="600519",
        event_type="announcement",
        limit=20,
    )

    sql, params = connection.cursor_obj.executed[0]
    assert "LOWER(e.title) LIKE LOWER(%(keyword_like)s)" in sql
    assert "LOWER(e.vt_symbol) LIKE LOWER(%(vt_symbol_like)s)" in sql
    assert params["keyword_like"] == "%分红%"
    assert params["vt_symbol_like"] == "%600519%"
    assert params["event_type"] == "announcement"
    assert params["limit"] == 20
    assert events[0].title == "贵州茅台分红公告"


class FakeCursor:
    """Tiny DB-API cursor fake."""

    def __init__(self) -> None:
        self.executed = []

    def execute(self, sql, params=None) -> None:
        self.executed.append((sql, params or {}))

    def close(self) -> None:
        return


class FakeConnection:
    """Tiny DB-API connection fake."""

    def __init__(self) -> None:
        self.cursor_obj = FakeCursor()
        self.committed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self) -> None:
        self.committed = True


class EventCursor:
    """Tiny DB-API cursor fake with read support."""

    def __init__(self, fetchall_result=None, fetchone_result=None) -> None:
        self.executed = []
        self.fetchall_result = fetchall_result or []
        self.fetchone_result = fetchone_result

    def execute(self, sql, params=None) -> None:
        self.executed.append((sql, params or {}))

    def fetchall(self):
        return self.fetchall_result

    def fetchone(self):
        return self.fetchone_result

    def close(self) -> None:
        return


class EventConnection:
    """Tiny DB-API connection fake for event read/write tests."""

    def __init__(self, fetchall_result=None, fetchone_result=None) -> None:
        self.cursor_obj = EventCursor(fetchall_result, fetchone_result)
        self.committed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self) -> None:
        self.committed = True


class MissingEventReader:
    """Snapshot reader with market only."""

    def load_bar_snapshots(self, vt_symbol, start, end):
        return [{"datetime": "2024-01-03", "close": 10}]

    def load_latest_snapshot(self, snapshot_type, vt_symbol, as_of):
        if snapshot_type in {"news", "sentiment"}:
            return None
        return {}


class MemoryNewsEventReader:
    """Event reader fake for composite reader tests."""

    def __init__(self, events=None, sentiment=None) -> None:
        self.events = events or []
        self.sentiment = sentiment

    def load_news_events(self, vt_symbol, start, end):
        return [
            event
            for event in self.events
            if event.vt_symbol == vt_symbol and start <= event.occurred_at <= end
        ]

    def load_sentiment_snapshot(self, vt_symbol, as_of):
        return self.sentiment
