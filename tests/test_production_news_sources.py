from datetime import datetime


def test_official_and_global_news_providers_convert_fixture_rows():
    """CNINFO/SSE/GDELT providers should convert rows without touching the network in tests."""
    from vnpy_router.providers.news_external import (
        CninfoAnnouncementProvider,
        GdeltGlobalNewsProvider,
        NewsFetchRequest,
        SseAnnouncementProvider,
    )

    request = NewsFetchRequest(
        vt_symbols=["600519.SSE"],
        start=datetime(2024, 1, 1),
        end=datetime(2024, 1, 3),
    )

    cninfo = CninfoAnnouncementProvider(
        http_client=lambda **kwargs: {
            "announcements": [
                {
                    "secCode": "600519",
                    "secName": "贵州茅台",
                    "announcementTitle": "贵州茅台2024年年度报告",
                    "announcementTime": "2024-01-02 09:00:00",
                    "adjunctUrl": "finalpage/2024-01-02/notice.pdf",
                }
            ]
        },
        provider_version="cninfo-test",
    )
    cninfo_result = cninfo.fetch(request)

    assert cninfo_result.degraded_sources == []
    assert cninfo_result.items[0].vt_symbol == "600519.SSE"
    assert cninfo_result.items[0].event_type == "announcement"
    assert cninfo_result.items[0].news.provider_name == "cninfo_announcement"
    assert cninfo_result.items[0].news.source_quality == "official_disclosure"
    assert cninfo_result.items[0].news.trust_score >= 0.9
    assert cninfo_result.items[0].news.raw_payload["secCode"] == "600519"

    sse = SseAnnouncementProvider(
        http_client=lambda **kwargs: {
            "result": [
                {
                    "SECURITY_CODE": "600519",
                    "SECURITY_NAME": "贵州茅台",
                    "TITLE": "贵州茅台关于收到监管工作函的公告",
                    "SSEDATE": "2024-01-02",
                    "URL": "https://www.sse.com.cn/notice.pdf",
                }
            ]
        },
        provider_version="sse-test",
    )
    sse_result = sse.fetch(request)

    assert sse_result.degraded_sources == []
    assert sse_result.items[0].vt_symbol == "600519.SSE"
    assert sse_result.items[0].news.provider_name == "sse_announcement"
    assert sse_result.items[0].news.source == "sse"
    assert sse_result.items[0].news.source_quality == "official_disclosure"

    gdelt = GdeltGlobalNewsProvider(
        http_client=lambda **kwargs: {
            "articles": [
                {
                    "title": "China exporters face tariff pressure",
                    "url": "https://example.test/global/1",
                    "seendate": "20240102T100000Z",
                    "domain": "example.test",
                    "language": "English",
                    "sourcecountry": "US",
                }
            ]
        },
        provider_version="gdelt-test",
    )
    gdelt_result = gdelt.fetch(request)

    assert gdelt_result.degraded_sources == []
    assert gdelt_result.items[0].vt_symbol == ""
    assert gdelt_result.items[0].event_type == "macro"
    assert gdelt_result.items[0].news.provider_name == "gdelt_global_news"
    assert gdelt_result.items[0].news.source_quality == "global_public_news"


def test_cninfo_provider_queries_each_symbol_with_searchkey_and_parses_epoch_millis():
    """CNINFO stock-code lookup should use searchkey per symbol and parse official ms timestamps."""
    from vnpy_router.providers.news_external import CninfoAnnouncementProvider, NewsFetchRequest

    calls = []

    def fake_http_client(**kwargs):
        calls.append(kwargs)
        code = kwargs["params"]["searchkey"]
        return {
            "announcements": [
                {
                    "secCode": code,
                    "secName": "测试公司",
                    "announcementTitle": f"{code}年度报告",
                    "announcementTime": 1714492800000,
                    "adjunctUrl": f"finalpage/{code}/notice.pdf",
                }
            ]
        }

    provider = CninfoAnnouncementProvider(
        http_client=fake_http_client,
        provider_version="cninfo-test",
    )

    result = provider.fetch(
        NewsFetchRequest(
            vt_symbols=["600519.SSE", "600406.SSE"],
            start=datetime(2024, 5, 1),
            end=datetime(2024, 5, 2),
            max_items_per_symbol=1,
        )
    )

    assert [call["params"]["searchkey"] for call in calls] == ["600519", "600406"]
    assert all(call["params"]["stock"] == "" for call in calls)
    assert [item.vt_symbol for item in result.items] == ["600519.SSE", "600406.SSE"]
    assert [item.news.published_at for item in result.items] == [
        datetime(2024, 5, 1),
        datetime(2024, 5, 1),
    ]


def test_ingestion_job_persists_entity_links_and_blocks_low_quality_context(tmp_path):
    """Ingestion should persist multi-symbol links while Toolkit filters low trust news."""
    from vnpy_router.event_storage import NewsRaw
    from vnpy_router.news_entity import SecurityEntityResolver
    from vnpy_router.security_catalog import SecurityEntityCatalog
    from vnpy_router.providers.news_external import FetchedNews, NewsFetchResult
    from vnpy_tradingagents.news_ingestion import ExternalNewsIngestionJob
    from vnpy_tradingagents.toolkit import MarketDataToolkit, NewsContextFilter, SnapshotQuery

    catalog_path = tmp_path / "securities.csv"
    catalog_path.write_text(
        "\n".join(
            [
                "vt_symbol,symbol,exchange,name,short_name,industry,sector,concept_tags,aliases",
                "600519.SSE,600519,SSE,贵州茅台酒股份有限公司,贵州茅台,白酒,消费,白酒|沪深300,茅台",
                "000858.SZSE,000858,SZSE,宜宾五粮液股份有限公司,五粮液,白酒,消费,白酒|深证100,",
            ]
        ),
        encoding="utf-8",
    )
    resolver = SecurityEntityResolver(SecurityEntityCatalog.from_path(catalog_path))

    official = NewsRaw(
        source="cninfo",
        url="https://static.cninfo.com.cn/finalpage/notice.pdf",
        title="白酒行业公告：贵州茅台和五粮液经营稳健",
        content="贵州茅台和五粮液均被公告提及。",
        published_at=datetime(2024, 1, 2, 9),
        provider_name="cninfo_announcement",
        source_quality="official_disclosure",
        trust_score=0.95,
    )
    low_trust = NewsRaw(
        source="东方财富",
        url="https://example.test/rumor",
        title="贵州茅台传闻",
        content="低可信转载。",
        published_at=datetime(2024, 1, 2, 10),
        provider_name="akshare_stock_news",
        source_quality="public_web",
        trust_score=0.4,
    )
    storage = MemoryProductionEventStorage()
    job = ExternalNewsIngestionJob(
        provider=FakeExternalProvider(
            NewsFetchResult(
                items=[
                    FetchedNews(official),
                    FetchedNews(low_trust, vt_symbol="600519.SSE"),
                ]
            )
        ),
        storage=storage,
        resolver=resolver,
        clock=lambda: datetime(2024, 1, 3),
    )

    summary = job.run(["600519.SSE", "000858.SZSE"], datetime(2024, 1, 1), datetime(2024, 1, 3))

    assert summary.raw_count == 2
    assert summary.event_count == 3
    assert {link.vt_symbol for link in storage.event_symbol_links} == {
        "600519.SSE",
        "000858.SZSE",
    }
    assert all(link.confidence >= 0.75 for link in storage.event_symbol_links)
    assert storage.quality_reports

    context = MarketDataToolkit(
        FilteredReader(storage.news_events),
        news_filter=NewsContextFilter(min_trust_score=0.70, min_link_confidence=0.75),
    ).build_context(
        SnapshotQuery(
            vt_symbol="600519.SSE",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 3),
        )
    )

    assert [event["title"] for event in context["news"]["events"]] == [
        "白酒行业公告：贵州茅台和五粮液经营稳健"
    ]
    assert context["news"]["filter"]["dropped_low_trust"] == 1


def test_news_readiness_accepts_official_providers_and_requires_entity_catalog(tmp_path):
    """Readiness should know P25 providers and warn when entity catalog is missing."""
    from vnpy_tradingagents.readiness import ProductionReadinessChecker, ReadinessStatus

    report = ProductionReadinessChecker(
        settings={
            "database.name": "postgresql",
            "database.host": "localhost",
            "database.port": 5432,
            "database.database": "vnpy",
            "database.user": "postgres",
            "database.password": "secret",
            "router.providers": "local_file",
            "router.local_path": str(tmp_path),
            "tradingagents.api_key_env_var": "OPENAI_API_KEY",
            "tradingagents.worker_factory": "vnpy_tradingagents.tradingagents_factory:build",
            "news.ingestion.enabled": True,
            "news.ingestion.providers": "cninfo_announcement,sse_announcement,gdelt_global_news,akshare_stock_news",
            "news.entity.catalog_path": "",
        },
        environ={"OPENAI_API_KEY": "secret"},
        module_available=lambda name: name in {"peewee", "psycopg2", "vnpy_tradingagents.tradingagents_factory", "akshare"},
        path_exists=lambda path: True,
    ).check()

    item = report.by_name("news_ingestion")
    assert item.status == ReadinessStatus.WARNING
    assert "news.entity.catalog_path" in item.message
    assert "cninfo" not in item.message.lower()
    assert "sse" not in item.message.lower()
    assert "gdelt" not in item.message.lower()


class FakeExternalProvider:
    """External provider fake returning a prebuilt result."""

    def __init__(self, result) -> None:
        self.result = result

    def fetch(self, request, output=print):
        return self.result


class MemoryProductionEventStorage:
    """In-memory event storage fake for production news ingestion."""

    def __init__(self) -> None:
        self.raw_news = []
        self.news_events = []
        self.event_symbol_links = []
        self.quality_reports = []

    def save_news_raw(self, news) -> None:
        self.raw_news.append(news)

    def save_news_event(self, event) -> None:
        self.news_events.append(event)

    def save_event_symbol_link(self, link) -> None:
        self.event_symbol_links.append(link)

    def save_event_quality_report(self, report) -> None:
        self.quality_reports.append(report)


class FilteredReader:
    """Snapshot reader fake exposing news events."""

    def __init__(self, events) -> None:
        self.events = events

    def load_bar_snapshots(self, vt_symbol, start, end):
        return [{"datetime": "2024-01-02", "close": 1688}]

    def load_latest_snapshot(self, snapshot_type, vt_symbol, as_of):
        return {}

    def load_news_events(self, vt_symbol, start, end):
        return [event for event in self.events if event.vt_symbol == vt_symbol]

    def load_sentiment_snapshot(self, vt_symbol, as_of):
        return None
