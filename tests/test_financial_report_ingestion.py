from datetime import datetime
import threading
from types import ModuleType

from vnpy.event import EVENT_TIMER, Event


def test_financial_extension_tables_are_registered():
    """Router extension schema should include complete financial report tables."""
    from peewee import SqliteDatabase

    from vnpy_router.extension_models import (
        ROUTER_EXTENSION_TABLE_NAMES,
        build_router_extension_models,
    )
    from vnpy_tradingagents.schema_init import EXTENSION_TABLE_NAMES

    model_names = {
        model._meta.table_name
        for model in build_router_extension_models(SqliteDatabase(":memory:"))
    }

    for table_name in [
        "financial_statement_snapshot",
        "financial_indicator_snapshot",
        "financial_report_document",
    ]:
        assert table_name in ROUTER_EXTENSION_TABLE_NAMES
        assert table_name in EXTENSION_TABLE_NAMES
        assert table_name in model_names


def test_akshare_financial_providers_convert_structured_rows(monkeypatch):
    """AKShare financial providers should produce provider-traced report snapshots."""
    from vnpy_router.providers import financial as financial_module
    from vnpy_router.providers.financial import (
        AkshareFinancialIndicatorProvider,
        AkshareSinaStatementProvider,
        FinancialFetchRequest,
    )

    fake_akshare = FakeAkshareFinancialModule()
    monkeypatch.setattr(financial_module, "import_module", lambda name: fake_akshare)
    request = FinancialFetchRequest(
        vt_symbols=["600519.SSE"],
        start=datetime(2024, 1, 1),
        end=datetime(2024, 12, 31),
        lookback_years=1,
    )

    statement_result = AkshareSinaStatementProvider(provider_version="test").fetch(request)
    indicator_result = AkshareFinancialIndicatorProvider(provider_version="test").fetch(request)

    assert statement_result.degraded_sources == []
    assert fake_akshare.sina_calls[0] == ("sh600519", "资产负债表")
    assert {item.statement_type for item in statement_result.statements} == {
        "balance_sheet",
        "income_statement",
        "cash_flow",
    }
    balance = next(
        item for item in statement_result.statements if item.statement_type == "balance_sheet"
    )
    assert balance.vt_symbol == "600519.SSE"
    assert balance.report_period == datetime(2024, 12, 31)
    assert balance.announcement_date == datetime(2025, 4, 1)
    assert balance.provider_name == "akshare_sina"
    assert balance.payload["raw_fields"]["资产总计"] == 1000.0
    assert indicator_result.indicators[0].report_period == datetime(2024, 12, 31)
    assert indicator_result.indicators[0].announcement_date == datetime(2025, 4, 1)
    assert indicator_result.indicators[0].payload["raw_fields"]["净资产收益率"] == 18.5


def test_official_financial_report_providers_convert_document_metadata():
    """Official report providers should persist report PDF metadata with source tracing."""
    from vnpy_router.providers.financial import (
        CninfoReportProvider,
        ExchangeReportProvider,
        FinancialFetchRequest,
    )

    request = FinancialFetchRequest(
        vt_symbols=["600519.SSE"],
        start=datetime(2025, 1, 1),
        end=datetime(2025, 4, 30),
        lookback_years=1,
    )

    cninfo = CninfoReportProvider(
        http_client=FakeFinancialHttpClient(
            {
                "announcements": [
                    {
                        "secCode": "600519",
                        "secName": "贵州茅台",
                        "announcementTitle": "贵州茅台2024年年度报告",
                        "announcementTime": 1743436800000,
                        "adjunctUrl": "finalpage/2025-04-01/1219567890.PDF",
                    },
                    {
                        "secCode": "600519",
                        "announcementTitle": "贵州茅台董事会决议公告",
                        "announcementTime": 1743436800000,
                        "report_period": "2024-12-31",
                    },
                ]
            }
        )
    )
    exchange = ExchangeReportProvider(
        http_client=FakeFinancialHttpClient(
            {
                "result": [
                    {
                        "SECURITY_CODE": "600519",
                        "SECURITY_NAME_ABBR": "贵州茅台",
                        "TITLE": "贵州茅台2024年年度报告摘要",
                        "SSEDATE": "2025-04-01",
                        "URL": "/disclosure/listedinfo/announcement/c/new/2025-04-01.pdf",
                        "REPORT_DATE": "2024-12-31",
                    }
                ]
            }
        )
    )

    cninfo_result = cninfo.fetch(request)
    exchange_result = exchange.fetch(request)

    assert len(cninfo_result.documents) == 1
    assert cninfo_result.documents[0].vt_symbol == "600519.SSE"
    assert cninfo_result.documents[0].source == "cninfo"
    assert cninfo_result.documents[0].report_period == datetime(2024, 12, 31)
    assert cninfo_result.documents[0].report_type == "annual"
    assert cninfo_result.documents[0].announcement_date == datetime(2025, 4, 1)
    assert cninfo_result.documents[0].pdf_url.startswith("https://static.cninfo.com.cn/")
    assert len(exchange_result.documents) == 1
    assert exchange_result.documents[0].source == "sse"
    assert exchange_result.documents[0].pdf_url.startswith("https://www.sse.com.cn/")


def test_financial_quality_scorer_marks_primary_only_with_complete_sources():
    """Financial quality report should explain missing statements and official documents."""
    from vnpy_router.financial_storage import (
        FinancialIndicatorSnapshot,
        FinancialReportDocument,
        FinancialStatementSnapshot,
    )
    from vnpy_tradingagents.financial_ingestion import FinancialQualityScorer

    period = datetime(2024, 12, 31)
    announcement_date = datetime(2025, 4, 1)
    scorer = FinancialQualityScorer()

    degraded = scorer.score(
        "600519.SSE",
        statements=[
            FinancialStatementSnapshot(
                vt_symbol="600519.SSE",
                report_period=period,
                statement_type="income_statement",
                report_type="annual",
                announcement_date=announcement_date,
                provider_name="akshare_sina",
                payload={"raw_fields": {"营业收入": 1200.0}},
            )
        ],
        indicators=[],
        documents=[],
    )
    assert degraded.quality_status == "degraded"
    assert degraded.missing_statement_types == ["balance_sheet", "cash_flow"]
    assert degraded.has_indicator is False
    assert degraded.has_official_document is False

    failed = scorer.score(
        "600519.SSE",
        statements=[],
        indicators=[],
        documents=[],
    )
    assert failed.quality_status == "failed"

    fallback = scorer.score(
        "600519.SSE",
        statements=[
            FinancialStatementSnapshot(
                vt_symbol="600519.SSE",
                report_period=period,
                statement_type=statement_type,
                report_type="annual",
                announcement_date=announcement_date,
                provider_name="akshare_sina",
                payload={"raw_fields": {"field": 1}},
            )
            for statement_type in ("balance_sheet", "income_statement", "cash_flow")
        ],
        indicators=[],
        documents=[],
    )
    assert fallback.quality_status == "fallback"

    primary = scorer.score(
        "600519.SSE",
        statements=[
            FinancialStatementSnapshot(
                vt_symbol="600519.SSE",
                report_period=period,
                statement_type=statement_type,
                report_type="annual",
                announcement_date=announcement_date,
                provider_name="akshare_sina",
                payload={"raw_fields": {"field": 1}},
            )
            for statement_type in ("balance_sheet", "income_statement", "cash_flow")
        ],
        indicators=[
            FinancialIndicatorSnapshot(
                vt_symbol="600519.SSE",
                report_period=period,
                announcement_date=announcement_date,
                provider_name="akshare_indicator",
                payload={"raw_fields": {"净资产收益率": 18.5}},
            )
        ],
        documents=[
            FinancialReportDocument(
                document_id="doc-1",
                vt_symbol="600519.SSE",
                report_period=period,
                report_type="annual",
                announcement_date=announcement_date,
                title="贵州茅台2024年年度报告",
                source="cninfo",
                provider_name="cninfo_report",
                pdf_url="https://static.cninfo.com.cn/finalpage.pdf",
            )
        ],
    )
    assert primary.quality_status == "primary"
    assert primary.missing_statement_types == []
    assert primary.has_indicator is True
    assert primary.has_official_document is True


def test_financial_snapshot_builder_writes_tradingagents_payloads():
    """Financial ingestion should build compact fundamentals and valuation snapshots."""
    from vnpy_tradingagents.financial_ingestion import FundamentalSnapshotBuilder
    from vnpy_router.financial_storage import FinancialIndicatorSnapshot, FinancialStatementSnapshot

    builder = FundamentalSnapshotBuilder(provider_name="financial_test")
    snapshots = builder.build(
        vt_symbol="600519.SSE",
        statements=[
            FinancialStatementSnapshot(
                vt_symbol="600519.SSE",
                report_period=datetime(2024, 12, 31),
                statement_type="income_statement",
                report_type="annual",
                announcement_date=datetime(2025, 4, 1),
                provider_name="akshare_sina",
                payload={"raw_fields": {"营业收入": 1200.0, "净利润": 320.0}},
            ),
            FinancialStatementSnapshot(
                vt_symbol="600519.SSE",
                report_period=datetime(2024, 12, 31),
                statement_type="cash_flow",
                report_type="annual",
                announcement_date=datetime(2025, 4, 1),
                provider_name="akshare_sina",
                payload={"raw_fields": {"经营活动产生的现金流量净额": 280.0}},
            ),
        ],
        indicators=[
            FinancialIndicatorSnapshot(
                vt_symbol="600519.SSE",
                report_period=datetime(2024, 12, 31),
                announcement_date=datetime(2025, 4, 1),
                provider_name="akshare_indicator",
                payload={"raw_fields": {"净资产收益率": 18.5, "销售毛利率": 91.2}},
            )
        ],
        documents=[],
    )

    fundamentals = snapshots["fundamentals"]
    valuation = snapshots["valuation"]

    assert fundamentals.as_of == datetime(2025, 4, 1)
    assert fundamentals.payload["latest_report_period"] == "2024-12-31"
    assert fundamentals.payload["revenue"]["current"] == 1200.0
    assert fundamentals.payload["net_profit"]["current"] == 320.0
    assert fundamentals.payload["roe"] == 18.5
    assert valuation.quality_status == "degraded"
    assert "valuation_provider_missing" in valuation.payload["missing_fields"]


def test_financial_snapshot_builder_maps_akshare_em_indicator_keys():
    """AKShare EastMoney indicator keys should feed compact F10 financial metrics."""
    from vnpy_tradingagents.financial_ingestion import FundamentalSnapshotBuilder
    from vnpy_router.financial_storage import FinancialIndicatorSnapshot, FinancialStatementSnapshot

    period = datetime(2024, 12, 31)
    builder = FundamentalSnapshotBuilder(provider_name="financial_test")
    snapshots = builder.build(
        vt_symbol="600519.SSE",
        statements=[
            FinancialStatementSnapshot(
                vt_symbol="600519.SSE",
                report_period=period,
                statement_type="income_statement",
                report_type="annual",
                announcement_date=datetime(2025, 4, 1),
                provider_name="akshare_sina",
                payload={"raw_fields": {"OPERATE_INCOME": 53909.0, "NETPROFIT": 28134.0}},
            ),
            FinancialStatementSnapshot(
                vt_symbol="600519.SSE",
                report_period=period,
                statement_type="cash_flow",
                report_type="annual",
                announcement_date=datetime(2025, 4, 1),
                provider_name="akshare_sina",
                payload={"raw_fields": {"NETCASH_OPERATE": 26971.0}},
            ),
            FinancialStatementSnapshot(
                vt_symbol="600519.SSE",
                report_period=period,
                statement_type="balance_sheet",
                report_type="annual",
                announcement_date=datetime(2025, 4, 1),
                provider_name="akshare_sina",
                payload={
                    "raw_fields": {
                        "TOTAL_ASSETS": 319918.0,
                        "TOTAL_LIABILITIES": 38782.0,
                    }
                },
            ),
        ],
        indicators=[
            FinancialIndicatorSnapshot(
                vt_symbol="600519.SSE",
                report_period=period,
                announcement_date=datetime(2025, 4, 1),
                provider_name="akshare_indicator",
                payload={
                    "raw_fields": {
                        "ROEJQ": 10.57,
                        "XSMLL": 89.76,
                        "XSJLL": 52.22,
                        "ZCFZL": 12.12,
                        "BPS": 223.79,
                        "EPSJB": 22.41,
                    }
                },
            )
        ],
        documents=[],
    )

    fundamentals = snapshots["fundamentals"].payload

    assert fundamentals["revenue"]["current"] == 53909.0
    assert fundamentals["net_profit"]["current"] == 28134.0
    assert fundamentals["operating_cash_flow"]["current"] == 26971.0
    assert fundamentals["total_assets"] == 319918.0
    assert fundamentals["total_liabilities"] == 38782.0
    assert fundamentals["roe"] == 10.57
    assert fundamentals["gross_margin"] == 89.76
    assert fundamentals["net_margin"] == 52.22
    assert fundamentals["debt_to_assets"] == 12.12
    assert fundamentals["bps"] == 223.79
    assert fundamentals["eps"] == 22.41


def test_financial_snapshot_builder_includes_quality_report():
    """Fundamental snapshots should expose financial source quality for TradingAgents."""
    from vnpy_tradingagents.financial_ingestion import FundamentalSnapshotBuilder
    from vnpy_router.financial_storage import (
        FinancialIndicatorSnapshot,
        FinancialReportDocument,
        FinancialStatementSnapshot,
    )

    period = datetime(2024, 12, 31)
    announcement_date = datetime(2025, 4, 1)
    builder = FundamentalSnapshotBuilder(provider_name="financial_test")
    snapshots = builder.build(
        vt_symbol="600519.SSE",
        statements=[
            FinancialStatementSnapshot(
                vt_symbol="600519.SSE",
                report_period=period,
                statement_type="balance_sheet",
                report_type="annual",
                announcement_date=announcement_date,
                provider_name="akshare_sina",
                payload={"raw_fields": {"资产总计": 1000.0, "负债合计": 300.0}},
            ),
            FinancialStatementSnapshot(
                vt_symbol="600519.SSE",
                report_period=period,
                statement_type="income_statement",
                report_type="annual",
                announcement_date=announcement_date,
                provider_name="akshare_sina",
                payload={"raw_fields": {"营业收入": 1200.0, "净利润": 320.0}},
            ),
            FinancialStatementSnapshot(
                vt_symbol="600519.SSE",
                report_period=period,
                statement_type="cash_flow",
                report_type="annual",
                announcement_date=announcement_date,
                provider_name="akshare_sina",
                payload={"raw_fields": {"经营活动产生的现金流量净额": 280.0}},
            ),
        ],
        indicators=[
            FinancialIndicatorSnapshot(
                vt_symbol="600519.SSE",
                report_period=period,
                announcement_date=announcement_date,
                provider_name="akshare_indicator",
                payload={"raw_fields": {"净资产收益率": 18.5}},
            )
        ],
        documents=[
            FinancialReportDocument(
                document_id="doc-1",
                vt_symbol="600519.SSE",
                report_period=period,
                report_type="annual",
                announcement_date=announcement_date,
                title="贵州茅台2024年年度报告",
                source="cninfo",
                provider_name="cninfo_report",
                pdf_url="https://static.cninfo.com.cn/finalpage.pdf",
            )
        ],
    )

    fundamentals = snapshots["fundamentals"]
    assert fundamentals.quality_status == "primary"
    assert fundamentals.payload["quality_report"]["has_official_document"] is True
    assert fundamentals.payload["quality_report"]["provider_names"] == [
        "akshare_indicator",
        "akshare_sina",
        "cninfo_report",
    ]


def test_financial_ingestion_job_deduplicates_before_writing_storage():
    """Duplicate provider rows should be filtered before financial storage writes."""
    from vnpy_router.financial_storage import (
        FinancialIndicatorSnapshot,
        FinancialReportDocument,
        FinancialStatementSnapshot,
    )
    from vnpy_tradingagents.financial_ingestion import FinancialIngestionJob

    period = datetime(2024, 12, 31)
    announcement_date = datetime(2025, 4, 1)
    statement = FinancialStatementSnapshot(
        vt_symbol="600519.SSE",
        report_period=period,
        statement_type="income_statement",
        report_type="annual",
        announcement_date=announcement_date,
        provider_name="akshare_sina",
        payload={"raw_fields": {"营业收入": 1200.0}},
    )
    indicator = FinancialIndicatorSnapshot(
        vt_symbol="600519.SSE",
        report_period=period,
        announcement_date=announcement_date,
        provider_name="akshare_indicator",
        payload={"raw_fields": {"净资产收益率": 18.5}},
    )
    document = FinancialReportDocument(
        document_id="doc-1",
        vt_symbol="600519.SSE",
        report_period=period,
        report_type="annual",
        announcement_date=announcement_date,
        title="贵州茅台2024年年度报告",
        source="cninfo",
        provider_name="cninfo_report",
        pdf_url="https://static.cninfo.com.cn/finalpage.pdf",
    )
    storage = MemoryFinancialStorage()
    job = FinancialIngestionJob(
        provider=FakeFinancialProvider(
            statements=[statement, statement],
            indicators=[indicator, indicator],
            documents=[document, document],
        ),
        storage=storage,
    )

    summary = job.run(
        ["600519.SSE"],
        start=datetime(2025, 1, 1),
        end=datetime(2025, 4, 30),
    )

    assert summary.statement_count == 1
    assert summary.indicator_count == 1
    assert summary.document_count == 1
    assert len(storage.statements) == 1
    assert len(storage.indicators) == 1
    assert len(storage.documents) == 1


def test_postgres_financial_storage_saves_and_loads_context_rows():
    """Financial storage should persist records and expose point-in-time context."""
    from vnpy_router.financial_storage import (
        FinancialReportDocument,
        FinancialStatementSnapshot,
        PostgresFinancialStorage,
    )

    connection = FinancialConnection(
        fetchall_result=[
            [
                {
                    "vt_symbol": "600519.SSE",
                    "report_period": datetime(2024, 12, 31),
                    "statement_type": "income_statement",
                    "report_type": "annual",
                    "announcement_date": datetime(2025, 4, 1),
                    "provider_name": "akshare_sina",
                    "provider_version": "v1",
                    "currency": "CNY",
                    "unit": "yuan",
                    "payload": {"raw_fields": {"营业收入": 1200.0}},
                    "source_document_id": "doc-1",
                    "quality_status": "primary",
                    "quality_report": {"has_official_document": True},
                }
            ],
            [
                {
                    "vt_symbol": "600519.SSE",
                    "report_period": datetime(2024, 12, 31),
                    "announcement_date": datetime(2025, 4, 1),
                    "provider_name": "akshare_indicator",
                    "provider_version": "v1",
                    "payload": {"raw_fields": {"净资产收益率": 18.5}},
                    "quality_status": "primary",
                    "quality_report": {"has_official_document": True},
                }
            ],
            [
                {
                    "document_id": "doc-1",
                    "vt_symbol": "600519.SSE",
                    "report_period": datetime(2024, 12, 31),
                    "report_type": "annual",
                    "announcement_date": datetime(2025, 4, 1),
                    "title": "2024年年度报告",
                    "source": "cninfo",
                    "provider_name": "cninfo_report",
                    "url": "https://static.cninfo.com.cn/finalpage.pdf",
                    "pdf_url": "https://static.cninfo.com.cn/finalpage.pdf",
                    "file_hash": "",
                    "provider_version": "v1",
                    "raw_payload": {"announcementTitle": "2024年年度报告"},
                }
            ],
        ]
    )
    storage = PostgresFinancialStorage(connection)
    storage.save_statement_snapshot(
        FinancialStatementSnapshot(
            vt_symbol="600519.SSE",
            report_period=datetime(2024, 12, 31),
            statement_type="income_statement",
            report_type="annual",
            announcement_date=datetime(2025, 4, 1),
            provider_name="akshare_sina",
            payload={"raw_fields": {"营业收入": 1200.0}},
        )
    )
    storage.save_report_document(
        FinancialReportDocument(
            document_id="doc-1",
            vt_symbol="600519.SSE",
            report_period=datetime(2024, 12, 31),
            report_type="annual",
            announcement_date=datetime(2025, 4, 1),
            title="2024年年度报告",
            source="cninfo",
            provider_name="cninfo_report",
        )
    )

    context = storage.load_financial_context(
        "600519.SSE",
        as_of=datetime(2025, 4, 2),
        max_periods=4,
    )

    sql_text = "\n".join(sql for sql, _ in connection.cursor_obj.executed)
    assert "INSERT INTO financial_statement_snapshot" in sql_text
    assert "INSERT INTO financial_report_document" in sql_text
    assert context["statements"]["income_statement"]["report_period"] == "2024-12-31"
    assert context["indicators"][0]["fields"]["净资产收益率"] == 18.5
    assert context["documents"][0]["title"] == "2024年年度报告"
    assert context["quality_status"] == "primary"


def test_market_data_toolkit_includes_financials_when_reader_supports_it():
    """TradingAgents context should include complete financial statements when available."""
    from vnpy_tradingagents.toolkit import MarketDataToolkit, SnapshotQuery

    context = MarketDataToolkit(FinancialContextReader()).build_context(
        SnapshotQuery(
            vt_symbol="600519.SSE",
            start=datetime(2025, 1, 1),
            end=datetime(2025, 4, 2),
        )
    )

    assert context["financials"]["statements"]["income_statement"]["fields"]["营业收入"] == 1200.0
    assert context["f10_financial_analysis"]["methodology_version"] == "f10-financial-v1"
    assert context["f10_financial_analysis"]["profitability"]["revenue"] == 1200.0
    assert "financials" not in context["degraded_sources"]


def test_financial_ingestion_scheduler_defaults_enabled_but_waits_for_schedule():
    """Scheduler should register by default, then wait until a configured minute to run."""
    from vnpy_tradingagents.financial_ingestion import FinancialIngestionScheduler

    event_engine = FakeEventEngine()
    job = CountingFinancialJob()
    datetimes = iter(
        [
            datetime(2026, 5, 9, 10, 0),
            datetime(2026, 5, 9, 20, 30),
            datetime(2026, 5, 9, 20, 30),
        ]
    )
    scheduler = FinancialIngestionScheduler(
        event_engine=event_engine,
        job=job,
        symbols=["600519.SSE"],
        datetime_clock=lambda: next(datetimes),
    )

    scheduler.start()
    assert event_engine.handlers[EVENT_TIMER]
    assert job.runs == []

    scheduler.process_timer_event(Event(EVENT_TIMER))
    assert job.runs == []

    scheduler.process_timer_event(Event(EVENT_TIMER))
    if scheduler.future:
        scheduler.future.result(timeout=2)
    scheduler.process_timer_event(Event(EVENT_TIMER))
    scheduler.stop()

    assert job.runs == [["600519.SSE"]]
    assert event_engine.handlers[EVENT_TIMER] == []


def test_financial_ingestion_scheduler_reports_progress_and_manual_batches():
    """Manual stock-pool backfill should expose status and advance by configured batches."""
    from vnpy_tradingagents.financial_ingestion import FinancialIngestionScheduler

    event_engine = FakeEventEngine()
    job = CountingFinancialJob()
    scheduler = FinancialIngestionScheduler(
        event_engine=event_engine,
        job=job,
        symbols=["600519.SSE", "000001.SZSE", "688008.SSE"],
        symbol_batch_size=2,
        datetime_clock=lambda: datetime(2026, 5, 9, 12, 0),
    )

    assert scheduler.status()["state"] == "idle"
    assert scheduler.trigger() is True
    assert scheduler.future
    scheduler.future.result(timeout=2)

    status = scheduler.status()
    assert status["state"] == "completed"
    assert status["last_symbols"] == ["600519.SSE", "000001.SZSE"]
    assert status["last_summary"]["statement_count"] == 2
    assert status["last_failed_symbols"] == []
    assert job.runs == [["600519.SSE", "000001.SZSE"]]

    assert scheduler.trigger() is True
    assert scheduler.future
    scheduler.future.result(timeout=2)
    assert scheduler.status()["last_symbols"] == ["688008.SSE", "600519.SSE"]


def test_financial_ingestion_scheduler_retries_failed_symbols():
    """Failed symbol batches should be retryable without rebuilding the scheduler."""
    from vnpy_tradingagents.financial_ingestion import FinancialIngestionScheduler

    event_engine = FakeEventEngine()
    job = FailingFinancialJob()
    scheduler = FinancialIngestionScheduler(
        event_engine=event_engine,
        job=job,
        symbols=["600519.SSE", "000001.SZSE"],
        datetime_clock=lambda: datetime(2026, 5, 9, 12, 0),
    )

    assert scheduler.trigger(["600519.SSE", "000001.SZSE"]) is True
    assert scheduler.future
    scheduler.future.result(timeout=2)
    assert scheduler.status()["last_failed_symbols"] == ["600519.SSE"]

    assert scheduler.retry_failed() is True
    assert scheduler.future
    scheduler.future.result(timeout=2)
    assert job.runs[-1] == ["600519.SSE"]


def test_financial_ingestion_scheduler_captures_job_exceptions():
    """A failed financial job should not bubble out and break the vn.py process."""
    from vnpy_tradingagents.financial_ingestion import FinancialIngestionScheduler

    scheduler = FinancialIngestionScheduler(
        event_engine=FakeEventEngine(),
        job=RaisingFinancialJob(),
        symbols=["600519.SSE"],
        datetime_clock=lambda: datetime(2026, 5, 9, 12, 0),
    )

    assert scheduler.trigger(["600519.SSE"]) is True
    assert scheduler.future
    summary = scheduler.future.result(timeout=2)

    assert summary.errors["financial_ingestion"] == "provider down"
    status = scheduler.status()
    assert status["last_error"] == "provider down"
    assert status["last_failed_symbols"] == ["600519.SSE"]


def test_financial_ingestion_scheduler_can_request_cancel():
    """Cancel should mark the current run as cancel-requested for the UI."""
    from vnpy_tradingagents.financial_ingestion import FinancialIngestionScheduler

    event_engine = FakeEventEngine()
    job = WaitingFinancialJob()
    scheduler = FinancialIngestionScheduler(
        event_engine=event_engine,
        job=job,
        symbols=["600519.SSE"],
        datetime_clock=lambda: datetime(2026, 5, 9, 12, 0),
    )

    assert scheduler.trigger() is True
    assert scheduler.cancel() is True

    status = scheduler.status()
    assert status["state"] == "cancel_requested"
    assert status["cancel_requested"] is True
    job.release()
    if scheduler.future:
        scheduler.future.result(timeout=2)
    scheduler.shutdown()


def test_financial_settings_are_default_enabled_and_visible_in_tradingagents_config():
    """Financial ingestion settings should be default-enabled and grouped with TradingAgents."""
    from vnpy.trader.setting import SETTINGS
    from vnpy.trader.ui.widget import SETTING_HELP_TEXT
    from vnpy_tradingagents.ui.widget import collect_tradingagents_config_keys

    assert SETTINGS["financial.ingestion.enabled"] is True
    assert "默认开启" in SETTING_HELP_TEXT["financial.ingestion.enabled"]
    assert "financial.ingestion.enabled" in collect_tradingagents_config_keys()
    assert "cninfo_report" in SETTINGS["financial.ingestion.providers"]


def test_engine_delegates_financial_reader_and_manual_trigger():
    """TradingAgentsEngine should expose financial context and one-off ingestion to the UI."""
    from vnpy.event import EventEngine
    from vnpy_tradingagents.engine import TradingAgentsEngine

    engine = TradingAgentsEngine(None, EventEngine())  # type: ignore[arg-type]
    reader = FakeFinancialReader()
    scheduler = FakeFinancialScheduler()

    engine.set_financial_reader(reader)
    context = engine.load_financial_context("600519.SSE", max_periods=2)
    engine.set_financial_ingestion_scheduler(scheduler)
    message = engine.trigger_financial_ingestion(["600519.SSE"])
    status = engine.get_financial_ingestion_status()
    cancel_result = engine.cancel_financial_ingestion()
    apply_result = engine.apply_financial_ingestion_settings(
        {
            "financial.ingestion.enabled": False,
            "financial.ingestion.symbols": "600519.SSE,000001.SZSE",
            "financial.ingestion.lookback_years": 3,
            "financial.ingestion.symbol_batch_size": 1,
            "financial.ingestion.schedule": "20:30",
            "financial.ingestion.morning_retry_schedule": "08:30",
            "financial.ingestion.morning_retry_enabled": True,
        }
    )

    assert context["quality_status"] == "primary"
    assert reader.calls == [("600519.SSE", 2)]
    assert message == "financial_ingestion_triggered symbols=600519.SSE"
    assert engine.retry_failed_financial_ingestion() == "financial_ingestion_retry_failed_triggered"
    assert scheduler.calls == [["600519.SSE"]]
    assert status["state"] == "idle"
    assert cancel_result is True
    assert apply_result == "financial_ingestion_settings_applied"
    assert scheduler.applied["enabled"] is False
    assert scheduler.applied["symbols"] == ("600519.SSE", "000001.SZSE")
    assert scheduler.applied["symbol_batch_size"] == 1


class FakeAkshareFinancialModule(ModuleType):
    """Tiny AKShare fake for financial providers."""

    def __init__(self) -> None:
        super().__init__("akshare")
        self.sina_calls = []

    def stock_financial_report_sina(self, stock: str, symbol: str):
        self.sina_calls.append((stock, symbol))
        import pandas as pd

        fields_by_symbol = {
            "资产负债表": {"资产总计": 1000.0, "负债合计": 300.0},
            "利润表": {"营业收入": 1200.0, "净利润": 320.0},
            "现金流量表": {"经营活动产生的现金流量净额": 280.0},
        }
        row = {
            "报告日": "20241231",
            "公告日期": "20250401",
            **fields_by_symbol[symbol],
        }
        return pd.DataFrame([row])

    def stock_financial_analysis_indicator(self, symbol: str):
        import pandas as pd

        return pd.DataFrame([])

    def stock_financial_analysis_indicator_em(self, symbol: str, indicator: str = "按报告期"):
        import pandas as pd

        return pd.DataFrame(
            [
                {
                    "REPORT_DATE": "2024-12-31 00:00:00",
                    "NOTICE_DATE": "2025-04-01 00:00:00",
                    "净资产收益率": 18.5,
                    "销售毛利率": 91.2,
                }
            ]
        )


class FakeFinancialHttpClient:
    """Fake official financial-report HTTP client."""

    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self.payload


class FinancialConnection:
    """Tiny DB-API fake for financial storage."""

    def __init__(self, fetchall_result=None, fetchone_result=None) -> None:
        self.cursor_obj = FinancialCursor(fetchall_result or [], fetchone_result)
        self.committed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True


class FinancialCursor:
    """Cursor fake that records SQL and returns configured rows."""

    def __init__(self, fetchall_result, fetchone_result=None) -> None:
        self.executed = []
        self.fetchall_result = fetchall_result
        self.fetchone_result = fetchone_result

    def execute(self, sql, params=None):
        self.executed.append((sql, params or {}))

    def fetchall(self):
        if (
            self.fetchall_result
            and isinstance(self.fetchall_result, list)
            and isinstance(self.fetchall_result[0], list)
        ):
            return self.fetchall_result.pop(0)
        return self.fetchall_result

    def fetchone(self):
        return self.fetchone_result

    def close(self):
        pass


class FinancialContextReader:
    """Snapshot reader fake with financial context support."""

    def load_bar_snapshots(self, vt_symbol, start, end):
        return [{"datetime": end, "close_price": 10, "volume": 100}]

    def load_latest_snapshot(self, snapshot_type, vt_symbol, as_of):
        if snapshot_type == "fundamentals":
            return {"latest_report_period": "2024-12-31"}
        if snapshot_type == "valuation":
            return {"pe_ttm": 18.0}
        return {}

    def load_news_events(self, vt_symbol, start, end):
        return []

    def load_sentiment_snapshot(self, vt_symbol, as_of):
        return None

    def load_financial_context(self, vt_symbol, as_of, max_periods=4):
        return {
            "statements": {
                "income_statement": {
                    "report_period": "2024-12-31",
                    "fields": {"营业收入": 1200.0},
                }
            },
            "documents": [],
            "quality_status": "primary",
        }


class FakeEventEngine:
    """Tiny EventEngine fake."""

    def __init__(self) -> None:
        self.handlers = {}

    def register(self, event_type, handler) -> None:
        self.handlers.setdefault(event_type, []).append(handler)

    def unregister(self, event_type, handler) -> None:
        self.handlers[event_type].remove(handler)


class CountingFinancialJob:
    """Scheduled financial job fake."""

    def __init__(self) -> None:
        self.runs = []

    def run(self, symbols, start=None, end=None):
        self.runs.append(list(symbols))
        return {
            "statement_count": len(symbols),
            "indicator_count": 0,
            "document_count": 0,
            "payload_snapshot_count": 0,
            "degraded_sources": [],
            "errors": {},
            "symbols": list(symbols),
            "start": start,
            "end": end,
        }


class WaitingFinancialJob:
    """Financial job fake that blocks until the test releases it."""

    def __init__(self) -> None:
        self.release_event = threading.Event()

    def run(self, symbols, start=None, end=None):
        self.release_event.wait(timeout=2)
        return {
            "statement_count": 0,
            "indicator_count": 0,
            "document_count": 0,
            "payload_snapshot_count": 0,
            "degraded_sources": [],
            "errors": {},
        }

    def release(self) -> None:
        self.release_event.set()


class FailingFinancialJob:
    """Financial job fake returning one failed symbol."""

    def __init__(self) -> None:
        self.runs = []

    def run(self, symbols, start=None, end=None):
        self.runs.append(list(symbols))
        return {
            "statement_count": 0,
            "indicator_count": 0,
            "document_count": 0,
            "payload_snapshot_count": 0,
            "degraded_sources": ["financial_provider"],
            "errors": {"600519.SSE": "timeout"},
        }


class RaisingFinancialJob:
    """Financial job fake raising a hard provider error."""

    def run(self, symbols, start=None, end=None):
        raise RuntimeError("provider down")


class FakeFinancialReader:
    """Fake financial reader for TradingAgentsEngine delegation."""

    def __init__(self) -> None:
        self.calls = []

    def load_financial_context(self, vt_symbol, as_of, max_periods=4):
        self.calls.append((vt_symbol, max_periods))
        return {"statements": {}, "documents": [], "quality_status": "primary"}


class FakeFinancialScheduler:
    """Fake financial scheduler for manual trigger delegation."""

    def __init__(self) -> None:
        self.calls = []
        self.applied = {}

    def trigger(self, symbols=None):
        self.calls.append(list(symbols or []))

    def status(self):
        return {"state": "idle"}

    def cancel(self):
        return True

    def apply_settings(self, **settings):
        self.applied = settings

    def retry_failed(self):
        return True


class FakeFinancialProvider:
    """Fake financial provider returning configured records."""

    def __init__(self, statements=None, indicators=None, documents=None) -> None:
        self.statements = statements or []
        self.indicators = indicators or []
        self.documents = documents or []

    def fetch(self, request, output=print):
        from vnpy_router.providers.financial import FinancialFetchResult

        return FinancialFetchResult(
            statements=list(self.statements),
            indicators=list(self.indicators),
            documents=list(self.documents),
        )


class MemoryFinancialStorage:
    """In-memory financial storage fake."""

    def __init__(self) -> None:
        self.statements = []
        self.indicators = []
        self.documents = []

    def save_statement_snapshot(self, snapshot) -> None:
        self.statements.append(snapshot)

    def save_indicator_snapshot(self, snapshot) -> None:
        self.indicators.append(snapshot)

    def save_report_document(self, document) -> None:
        self.documents.append(document)
