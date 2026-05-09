from datetime import datetime
from types import ModuleType

from vnpy.event import EVENT_TIMER, Event


def test_akshare_stock_news_provider_converts_rows_to_raw_news(monkeypatch):
    """AKShare stock news provider should convert public rows into traced raw news."""
    from vnpy_router.providers import news_external as news_external_module
    from vnpy_router.providers.news_external import (
        AkshareStockNewsProvider,
        NewsFetchRequest,
    )

    fake_akshare = FakeAkshareModule()
    monkeypatch.setattr(news_external_module, "import_module", lambda name: fake_akshare)

    provider = AkshareStockNewsProvider(provider_version="test-version")
    request = NewsFetchRequest(
        vt_symbols=["600519.SSE"],
        start=datetime(2024, 1, 1),
        end=datetime(2024, 1, 3),
    )

    result = provider.fetch(request)

    assert result.degraded_sources == []
    assert fake_akshare.stock_news_symbol == "600519"
    assert len(result.items) == 1
    item = result.items[0]
    assert item.vt_symbol == "600519.SSE"
    assert item.news.title == "贵州茅台公告"
    assert item.news.source == "东方财富"
    assert item.news.provider_name == "akshare_stock_news"
    assert item.news.provider_version == "test-version"
    assert item.news.raw_payload["provider_endpoint"] == "stock_news_em"


def test_akshare_stock_news_provider_degrades_when_dependency_missing(monkeypatch):
    """Missing AKShare dependency should degrade without raising."""
    from vnpy_router.providers import news_external as news_external_module
    from vnpy_router.providers.news_external import (
        AkshareStockNewsProvider,
        NewsFetchRequest,
    )

    def missing_akshare(name: str):
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(news_external_module, "import_module", missing_akshare)

    result = AkshareStockNewsProvider().fetch(
        NewsFetchRequest(
            vt_symbols=["600519.SSE"],
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 3),
        )
    )

    assert result.items == []
    assert "akshare_stock_news" in result.degraded_sources
    assert result.errors["akshare_stock_news"]


def test_akshare_global_news_provider_keeps_rows_unlinked(monkeypatch):
    """Global finance news should not be forced into a symbol-specific event."""
    from vnpy_router.providers import news_external as news_external_module
    from vnpy_router.providers.news_external import (
        AkshareGlobalNewsProvider,
        NewsFetchRequest,
    )

    fake_akshare = FakeAkshareModule()
    monkeypatch.setattr(news_external_module, "import_module", lambda name: fake_akshare)

    result = AkshareGlobalNewsProvider(
        endpoints=["stock_info_global_cls"],
        provider_version="global-test",
    ).fetch(
        NewsFetchRequest(
            vt_symbols=["600519.SSE"],
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 3),
        )
    )

    assert result.degraded_sources == []
    assert len(result.items) == 1
    assert result.items[0].vt_symbol == ""
    assert result.items[0].event_type == "global_news"
    assert result.items[0].news.provider_name == "akshare_global_news"
    assert result.items[0].news.raw_payload["provider_endpoint"] == "stock_info_global_cls"


def test_news_provider_chain_continues_after_failure_and_deduplicates():
    """Provider chain should continue after degraded providers and deduplicate raw rows."""
    from vnpy_router.event_storage import NewsRaw
    from vnpy_router.providers.news_external import (
        FetchedNews,
        NewsFetchRequest,
        NewsFetchResult,
        NewsProviderChain,
    )

    raw = NewsRaw(
        source="fixture",
        url="local://news/1",
        title="重复新闻",
        content="重复新闻内容",
        published_at=datetime(2024, 1, 2),
        provider_name="fixture_provider",
    )
    chain = NewsProviderChain(
        [
            FakeExternalProvider(
                NewsFetchResult(
                    items=[],
                    degraded_sources=["broken_provider"],
                    errors={"broken_provider": "timeout"},
                )
            ),
            FakeExternalProvider(
                NewsFetchResult(
                    items=[
                        FetchedNews(news=raw, vt_symbol="600519.SSE"),
                        FetchedNews(news=raw, vt_symbol="600519.SSE"),
                    ]
                )
            ),
        ]
    )

    result = chain.fetch(
        NewsFetchRequest(
            vt_symbols=["600519.SSE"],
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 3),
        )
    )

    assert len(result.items) == 1
    assert result.degraded_sources == ["broken_provider"]
    assert result.errors == {"broken_provider": "timeout"}


def test_local_file_external_news_provider_loads_fixture_events(tmp_path):
    """Local file provider should feed the same ingestion chain for offline validation."""
    from vnpy_router.providers.news_external import (
        LocalFileExternalNewsProvider,
        NewsFetchRequest,
    )

    path = tmp_path / "news.csv"
    path.write_text(
        "\n".join(
            [
                "vt_symbol,title,summary,event_type,occurred_at,sentiment_score",
                "600519.SSE,本地公告,本地公告摘要,announcement,2024-01-02T10:00:00,0.1",
            ]
        ),
        encoding="utf-8",
    )

    result = LocalFileExternalNewsProvider(path).fetch(
        NewsFetchRequest(
            vt_symbols=["600519.SSE"],
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 3),
        )
    )

    assert len(result.items) == 1
    assert result.items[0].vt_symbol == "600519.SSE"
    assert result.items[0].news.title == "本地公告"
    assert result.items[0].news.provider_name == "local_file_news"


def test_external_news_ingestion_job_persists_raw_and_symbol_events():
    """ExternalNewsIngestionJob should save raw rows and normalized symbol events."""
    from vnpy_router.event_storage import NewsRaw
    from vnpy_router.providers.news_external import FetchedNews, NewsFetchResult
    from vnpy_tradingagents.news_ingestion import ExternalNewsIngestionJob

    raw = NewsRaw(
        source="fixture",
        url="local://news/1",
        title="贵州茅台公告",
        content="贵州茅台发布经营公告。",
        published_at=datetime(2024, 1, 2, 10),
        provider_name="fixture_provider",
        provider_version="fixture-v1",
        source_quality="manual",
        trust_score=0.8,
        review_status="reviewed",
    )
    storage = MemoryEventStorage()
    ops_storage = MemoryOpsStorage()
    job = ExternalNewsIngestionJob(
        provider=FakeExternalProvider(NewsFetchResult(items=[FetchedNews(raw, "600519.SSE")])),
        storage=storage,
        ops_storage=ops_storage,
        clock=lambda: datetime(2024, 1, 3, 9),
    )

    summary = job.run(
        ["600519.SSE"],
        start=datetime(2024, 1, 1),
        end=datetime(2024, 1, 3),
    )

    assert summary.raw_count == 1
    assert summary.event_count == 1
    assert storage.raw_news[0].raw_hash == raw.raw_hash
    event = storage.news_events[0]
    assert event.vt_symbol == "600519.SSE"
    assert event.title == "贵州茅台公告"
    assert event.raw_hash == raw.raw_hash
    assert ops_storage.heartbeats[0].component == "external_news_ingestion"
    assert ops_storage.heartbeats[0].status == "ready"


def test_external_news_ingestion_job_deduplicates_before_writing_storage():
    """Duplicate provider rows should be filtered before raw/event storage writes."""
    from vnpy_router.event_storage import NewsRaw
    from vnpy_router.providers.news_external import FetchedNews, NewsFetchResult
    from vnpy_tradingagents.news_ingestion import ExternalNewsIngestionJob

    raw = NewsRaw(
        source="fixture",
        url="local://news/duplicate",
        title="贵州茅台公告",
        content="贵州茅台发布经营公告。",
        published_at=datetime(2024, 1, 2, 10),
        provider_name="fixture_provider",
        provider_version="fixture-v1",
        source_quality="manual",
        trust_score=0.8,
        review_status="reviewed",
    )
    storage = MemoryEventStorage()
    job = ExternalNewsIngestionJob(
        provider=FakeExternalProvider(
            NewsFetchResult(
                items=[
                    FetchedNews(raw, "600519.SSE"),
                    FetchedNews(raw, "600519.SSE"),
                ]
            )
        ),
        storage=storage,
        clock=lambda: datetime(2024, 1, 3, 9),
    )

    summary = job.run(
        ["600519.SSE"],
        start=datetime(2024, 1, 1),
        end=datetime(2024, 1, 3),
    )

    assert summary.raw_count == 1
    assert summary.event_count == 1
    assert len(storage.raw_news) == 1
    assert len(storage.news_events) == 1


def test_external_news_ingestion_scheduler_throttles_timer_events():
    """ExternalNewsIngestionScheduler should run jobs asynchronously and throttle timers."""
    from vnpy_tradingagents.news_ingestion import ExternalNewsIngestionScheduler

    event_engine = FakeEventEngine()
    job = CountingIngestionJob()
    times = iter([0, 1, 6])
    scheduler = ExternalNewsIngestionScheduler(
        event_engine,
        job,
        symbols=["600519.SSE"],
        interval_seconds=5,
        clock=lambda: next(times),
    )

    scheduler.start()
    scheduler.process_timer_event(Event(EVENT_TIMER))
    scheduler.process_timer_event(Event(EVENT_TIMER))
    if scheduler.future:
        scheduler.future.result(timeout=2)
    scheduler.process_timer_event(Event(EVENT_TIMER))
    if scheduler.future:
        scheduler.future.result(timeout=2)
    scheduler.stop()

    assert event_engine.handlers[EVENT_TIMER] == []
    assert job.runs == [["600519.SSE"], ["600519.SSE"]]


def test_external_news_ingestion_scheduler_rotates_symbol_batches():
    """Scheduler should slowly rotate a large universe instead of fetching all at once."""
    from vnpy_tradingagents.news_ingestion import ExternalNewsIngestionScheduler

    event_engine = FakeEventEngine()
    job = CountingIngestionJob()
    times = iter([0, 100, 200])
    scheduler = ExternalNewsIngestionScheduler(
        event_engine,
        job,
        symbols=["600519.SSE", "000001.SZSE", "688008.SSE"],
        interval_seconds=1,
        symbol_batch_size=2,
        clock=lambda: next(times),
    )

    scheduler.process_timer_event(Event(EVENT_TIMER))
    scheduler.future.result(timeout=2)
    scheduler.process_timer_event(Event(EVENT_TIMER))
    scheduler.future.result(timeout=2)
    scheduler.process_timer_event(Event(EVENT_TIMER))
    scheduler.future.result(timeout=2)
    scheduler.shutdown()

    assert job.runs == [
        ["600519.SSE", "000001.SZSE"],
        ["688008.SSE", "600519.SSE"],
        ["000001.SZSE", "688008.SSE"],
    ]


def test_news_ingestion_provider_builder_uses_global_settings(tmp_path):
    """Provider builder should create a configured chain from vn.py settings."""
    from vnpy_tradingagents.news_ingestion import build_news_ingestion_provider
    from vnpy_router.providers.news_external import NewsProviderChain

    provider = build_news_ingestion_provider(
        {
            "news.ingestion.providers": "local_file,akshare_stock_news,akshare_global_news",
            "news.ingestion.local_path": str(tmp_path / "news.csv"),
            "news.ingestion.akshare.endpoints": "stock_info_global_cls",
        }
    )

    assert isinstance(provider, NewsProviderChain)
    assert [child.name for child in provider.providers] == [
        "local_file_news",
        "akshare_stock_news",
        "akshare_global_news",
    ]


def test_readiness_checker_reports_news_ingestion_dependency_warning():
    """Readiness should warn when news ingestion is enabled but AKShare is unavailable."""
    from vnpy_tradingagents.readiness import ProductionReadinessChecker, ReadinessStatus

    checker = ProductionReadinessChecker(
        settings={
            "database.name": "postgresql",
            "database.host": "localhost",
            "database.port": 5432,
            "database.database": "vnpy",
            "database.user": "postgres",
            "database.password": "secret",
            "router.providers": "local_file",
            "router.local_path": "/tmp",
            "tradingagents.api_key_env_var": "TRADINGAGENTS_API_KEY",
            "tradingagents.worker_factory": "worker_factory:build",
            "news.ingestion.enabled": True,
            "news.ingestion.providers": "akshare_stock_news",
        },
        environ={"TRADINGAGENTS_API_KEY": "secret"},
        module_available=lambda name: name not in {"akshare"},
        path_exists=lambda path: True,
    )

    report = checker.check()

    assert report.status == ReadinessStatus.WARNING
    item = report.by_name("news_ingestion")
    assert item.status == ReadinessStatus.WARNING
    assert "akshare" in item.message.lower()


def test_global_setting_ui_documents_news_ingestion_configuration():
    """Global settings help should document news ingestion configuration."""
    from vnpy.trader.setting import SETTINGS
    from vnpy.trader.ui.widget import SETTING_HELP_TEXT

    assert SETTINGS["news.ingestion.enabled"] is True
    assert "news.ingestion.providers" in SETTING_HELP_TEXT["news.ingestion.enabled"]
    assert "AKShare" in SETTING_HELP_TEXT["news.ingestion.providers"]
    assert "默认开启" in SETTING_HELP_TEXT["news.ingestion.enabled"]


class FakeAkshareModule(ModuleType):
    """Tiny AKShare fake for stock_news_em."""

    def __init__(self) -> None:
        super().__init__("akshare")
        self.stock_news_symbol = ""

    def stock_news_em(self, symbol: str):
        self.stock_news_symbol = symbol
        import pandas as pd

        return pd.DataFrame(
            [
                {
                    "新闻标题": "贵州茅台公告",
                    "新闻内容": "贵州茅台发布经营公告。",
                    "发布时间": "2024-01-02 10:00:00",
                    "文章来源": "东方财富",
                    "新闻链接": "https://example.test/news/1",
                }
            ]
        )

    def stock_info_global_cls(self):
        import pandas as pd

        return pd.DataFrame(
            [
                {
                    "标题": "财联社快讯",
                    "内容": "宏观新闻。",
                    "发布时间": "2024-01-02 11:00:00",
                    "来源": "财联社",
                    "链接": "https://example.test/global/1",
                }
            ]
        )


class FakeExternalProvider:
    """External provider fake returning a prebuilt result."""

    def __init__(self, result) -> None:
        self.result = result

    def fetch(self, request, output=print):
        return self.result


class MemoryEventStorage:
    """In-memory event storage fake."""

    def __init__(self) -> None:
        self.raw_news = []
        self.news_events = []

    def save_news_raw(self, news) -> None:
        self.raw_news.append(news)

    def save_news_event(self, event) -> None:
        self.news_events.append(event)


class MemoryOpsStorage:
    """In-memory ops storage fake."""

    def __init__(self) -> None:
        self.heartbeats = []

    def save_heartbeat(self, heartbeat) -> None:
        self.heartbeats.append(heartbeat)


class FakeEventEngine:
    """Tiny EventEngine fake."""

    def __init__(self) -> None:
        self.handlers = {}

    def register(self, event_type, handler) -> None:
        self.handlers.setdefault(event_type, []).append(handler)

    def unregister(self, event_type, handler) -> None:
        self.handlers[event_type].remove(handler)


class CountingIngestionJob:
    """Scheduled job fake."""

    def __init__(self) -> None:
        self.runs = []

    def run(self, symbols, start=None, end=None):
        self.runs.append(list(symbols))
        return {
            "end": end,
            "start": start,
            "symbols": symbols,
        }
