from datetime import datetime

from vnpy.trader.constant import Exchange, Product
from vnpy.trader.object import ContractData
from vnpy_tradingagents.engine import TradingAgentsEngine
from vnpy_tradingagents.manual_analysis import ManualAnalysisRequest
from vnpy_tradingagents.runtime import TradingAgentsMode
from vnpy_tradingagents.worker import TradingAgentsWorkerResponse


def test_configure_tradingagents_services_attaches_manual_analysis_service():
    """App startup should wire the UI button to a real manual analysis service."""
    from vnpy_tradingagents.bootstrap import configure_tradingagents_services

    engine = object.__new__(TradingAgentsEngine)
    engine.runtime = FakeRuntime()
    engine.manual_analysis_service = None
    engine.state_storage = None
    engine.set_manual_analysis_service = lambda service: setattr(
        engine, "manual_analysis_service", service
    )
    engine.set_state_storage = lambda storage: setattr(engine, "state_storage", storage)
    engine.set_analysis_history_reader = lambda reader: setattr(
        engine, "analysis_history_reader", reader
    )
    engine.set_news_event_reader = lambda reader: setattr(engine, "news_event_reader", reader)

    ok = configure_tradingagents_services(
        FakeMainEngine(engine),
        settings={"database.name": "postgresql"},
        connection_factory=lambda settings: FakeConnection(),
        worker_factory=lambda: FakeWorker(),
    )

    assert ok
    assert engine.manual_analysis_service is not None
    assert engine.state_storage is not None
    assert engine.analysis_history_reader is not None
    assert engine.news_event_reader is not None
    assert callable(engine.manual_analysis_service.toolkit.reader.load_news_events)
    assert callable(engine.manual_analysis_service.toolkit.reader.load_sentiment_snapshot)

    result = engine.manual_analysis_service.run(
        ManualAnalysisRequest(
            vt_symbol="600519.SSE",
            start=datetime(2026, 5, 1),
            end=datetime(2026, 5, 8),
        )
    )

    assert result.status == "completed"
    assert result.response is not None
    assert result.response.action == "watch"


def test_configure_tradingagents_services_installs_degraded_service_on_failure():
    """Startup should show an actionable error instead of service-not-configured."""
    from vnpy_tradingagents.bootstrap import configure_tradingagents_services

    engine = object.__new__(TradingAgentsEngine)
    engine.manual_analysis_service = None
    engine.set_manual_analysis_service = lambda service: setattr(
        engine, "manual_analysis_service", service
    )

    ok = configure_tradingagents_services(
        FakeMainEngine(engine),
        settings={},
        connection_factory=lambda settings: (_ for _ in ()).throw(RuntimeError("db down")),
    )

    assert not ok
    assert engine.manual_analysis_service is not None

    result = engine.manual_analysis_service.run(
        ManualAnalysisRequest(
            vt_symbol="600519.SSE",
            start=datetime(2026, 5, 1),
            end=datetime(2026, 5, 8),
        )
    )

    assert result.status == "failed"
    assert "db down" in result.error_message


def test_configure_tradingagents_services_starts_news_scheduler_when_enabled():
    """Startup should attach the optional in-process news ingestion scheduler."""
    from vnpy_tradingagents.bootstrap import configure_tradingagents_services

    engine = object.__new__(TradingAgentsEngine)
    engine.runtime = FakeRuntime()
    engine.manual_analysis_service = None
    engine.state_storage = None
    engine.news_ingestion_scheduler = None
    engine.set_manual_analysis_service = lambda service: setattr(
        engine, "manual_analysis_service", service
    )
    engine.set_state_storage = lambda storage: setattr(engine, "state_storage", storage)
    engine.set_analysis_history_reader = lambda reader: setattr(
        engine, "analysis_history_reader", reader
    )
    engine.set_news_ingestion_scheduler = lambda scheduler: setattr(
        engine, "news_ingestion_scheduler", scheduler
    )

    scheduler_holder = {}

    def scheduler_factory(**kwargs):
        scheduler = FakeNewsScheduler(**kwargs)
        scheduler_holder["scheduler"] = scheduler
        return scheduler

    ok = configure_tradingagents_services(
        FakeMainEngine(engine),
        settings={
            "database.name": "postgresql",
            "news.ingestion.enabled": True,
            "news.ingestion.symbols": "600519.SSE, 000001.SZSE",
            "news.ingestion.interval_seconds": 300,
            "news.ingestion.symbol_batch_size": 1,
        },
        connection_factory=lambda settings: FakeConnection(),
        worker_factory=lambda: FakeWorker(),
        news_provider_factory=lambda settings: FakeNewsProvider(),
        news_scheduler_factory=scheduler_factory,
    )

    assert ok
    scheduler = scheduler_holder["scheduler"]
    assert engine.news_ingestion_scheduler is scheduler
    assert scheduler.started
    assert scheduler.symbols == ("600519.SSE", "000001.SZSE")
    assert scheduler.symbol_batch_size == 1


def test_configure_tradingagents_services_starts_financial_scheduler_by_default():
    """Financial ingestion should be registered by default in the existing vn.py process."""
    from vnpy_tradingagents.bootstrap import configure_tradingagents_services

    engine = object.__new__(TradingAgentsEngine)
    engine.runtime = FakeRuntime()
    engine.manual_analysis_service = None
    engine.financial_ingestion_scheduler = None
    engine.financial_reader = None
    engine.set_manual_analysis_service = lambda service: setattr(
        engine, "manual_analysis_service", service
    )
    engine.set_financial_reader = lambda reader: setattr(engine, "financial_reader", reader)
    engine.set_financial_ingestion_scheduler = lambda scheduler: setattr(
        engine, "financial_ingestion_scheduler", scheduler
    )

    scheduler_holder = {}

    def scheduler_factory(**kwargs):
        scheduler = FakeFinancialScheduler(**kwargs)
        scheduler_holder["scheduler"] = scheduler
        return scheduler

    ok = configure_tradingagents_services(
        FakeMainEngine(engine),
        settings={
            "database.name": "postgresql",
            "financial.ingestion.symbols": "600519.SSE",
            "financial.ingestion.schedule": "20:30",
            "financial.ingestion.morning_retry_enabled": True,
            "financial.ingestion.morning_retry_schedule": "08:30",
        },
        connection_factory=lambda settings: FakeConnection(),
        worker_factory=lambda: FakeWorker(),
        financial_provider_factory=lambda settings: FakeFinancialProvider(),
        financial_scheduler_factory=scheduler_factory,
    )

    assert ok
    scheduler = scheduler_holder["scheduler"]
    assert engine.financial_reader is not None
    assert engine.financial_ingestion_scheduler is scheduler
    assert scheduler.started
    assert scheduler.symbols == ("600519.SSE",)
    assert scheduler.schedule_times == ("20:30", "08:30")


def test_configure_tradingagents_services_registers_disabled_financial_scheduler_from_catalog(tmp_path):
    """Disabled financial ingestion should stay registered and use catalog symbols for manual batches."""
    from vnpy_tradingagents.bootstrap import configure_tradingagents_services

    catalog_path = tmp_path / "catalog.csv"
    catalog_path.write_text(
        "vt_symbol,symbol,exchange,name,short_name\n"
        "600519.SSE,600519,SSE,贵州茅台,茅台\n"
        "000001.SZSE,000001,SZSE,平安银行,平安银行\n",
        encoding="utf-8",
    )

    engine = object.__new__(TradingAgentsEngine)
    engine.runtime = FakeRuntime()
    engine.manual_analysis_service = None
    engine.financial_ingestion_scheduler = None
    engine.financial_reader = None
    engine.set_manual_analysis_service = lambda service: setattr(
        engine,
        "manual_analysis_service",
        service,
    )
    engine.set_financial_reader = lambda reader: setattr(engine, "financial_reader", reader)
    engine.set_financial_ingestion_scheduler = lambda scheduler: setattr(
        engine,
        "financial_ingestion_scheduler",
        scheduler,
    )

    ok = configure_tradingagents_services(
        FakeMainEngine(engine),
        settings={
            "database.name": "postgresql",
            "financial.ingestion.enabled": False,
            "financial.ingestion.symbols": "",
            "financial.ingestion.symbol_batch_size": 1,
            "news.entity.catalog_path": str(catalog_path),
        },
        connection_factory=lambda settings: FakeConnection(),
        worker_factory=lambda: FakeWorker(),
        financial_provider_factory=lambda settings: FakeFinancialProvider(),
        financial_scheduler_factory=lambda **kwargs: FakeFinancialScheduler(**kwargs),
    )

    scheduler = engine.financial_ingestion_scheduler
    assert ok
    assert scheduler.started
    assert scheduler.enabled is False
    assert scheduler.symbols == ("600519.SSE", "000001.SZSE")
    assert scheduler.symbol_batch_size == 1


def test_configure_tradingagents_services_keeps_news_scheduler_disabled_by_default():
    """News ingestion should remain opt-in at vn.py startup."""
    from vnpy_tradingagents.bootstrap import configure_tradingagents_services

    engine = object.__new__(TradingAgentsEngine)
    engine.runtime = FakeRuntime()
    engine.manual_analysis_service = None
    engine.news_ingestion_scheduler = None
    engine.set_manual_analysis_service = lambda service: setattr(
        engine, "manual_analysis_service", service
    )

    ok = configure_tradingagents_services(
        FakeMainEngine(engine),
        settings={"database.name": "postgresql"},
        connection_factory=lambda settings: FakeConnection(),
        worker_factory=lambda: FakeWorker(),
        news_scheduler_factory=lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("news scheduler should not be built")
        ),
    )

    assert ok
    assert engine.news_ingestion_scheduler is None


def test_news_ingestion_symbol_plan_uses_catalog_when_manual_symbols_are_empty(tmp_path):
    """Empty symbols can slowly rotate a configured catalog instead of requiring manual input."""
    from vnpy_tradingagents.bootstrap import build_news_ingestion_symbol_plan

    catalog_path = tmp_path / "catalog.csv"
    catalog_path.write_text(
        "vt_symbol,symbol,exchange,name,short_name\n"
        "600519.SSE,600519,SSE,贵州茅台,茅台\n"
        "000001.SZSE,000001,SZSE,平安银行,平安银行\n",
        encoding="utf-8",
    )

    plan = build_news_ingestion_symbol_plan(
        {
            "news.ingestion.symbols": "",
            "news.entity.catalog_path": str(catalog_path),
            "news.ingestion.symbol_source": "auto",
            "news.ingestion.symbol_batch_size": 50,
        }
    )

    assert plan.symbols == ("600519.SSE", "000001.SZSE")
    assert plan.source == "catalog"
    assert plan.batch_size == 50


def test_news_ingestion_symbol_plan_uses_vnpy_contracts_before_akshare_fallback():
    """No manual/catalog symbols should reuse live vn.py A-share contracts first."""
    from vnpy_tradingagents.bootstrap import build_news_ingestion_symbol_plan

    plan = build_news_ingestion_symbol_plan(
        {
            "news.ingestion.symbols": "",
            "news.entity.catalog_path": "",
            "news.ingestion.symbol_source": "auto",
            "news.ingestion.symbol_batch_size": 2,
        },
        main_engine=FakeMainEngineWithContracts(
            [
                make_contract("600519", Exchange.SSE, Product.EQUITY),
                make_contract("000001", Exchange.SZSE, Product.EQUITY),
                make_contract("rb2410", Exchange.SHFE, Product.FUTURES),
            ]
        ),
        akshare_loader=lambda: (_ for _ in ()).throw(
            AssertionError("AKShare should not be loaded when vn.py contracts exist")
        ),
    )

    assert plan.symbols == ("600519.SSE", "000001.SZSE")
    assert plan.source == "vnpy_contracts"
    assert plan.batch_size == 2


def test_news_ingestion_symbol_plan_falls_back_to_akshare_stock_universe():
    """No manual/catalog/contracts should lazily build an A-share universe from AKShare."""
    from vnpy_tradingagents.bootstrap import build_news_ingestion_symbol_plan

    plan = build_news_ingestion_symbol_plan(
        {
            "news.ingestion.symbols": "",
            "news.entity.catalog_path": "",
            "news.ingestion.symbol_source": "auto",
        },
        main_engine=FakeMainEngineWithContracts([]),
        akshare_loader=lambda: FakeAkshareModule(),
    )

    assert plan.symbols == ("600519.SSE", "000001.SZSE", "430047.BSE")
    assert plan.source == "akshare"


def test_news_ingestion_symbol_plan_empty_without_contracts_or_akshare_is_global_only():
    """No manual/catalog/contracts and no AKShare keeps global feeds usable."""
    from vnpy_tradingagents.bootstrap import build_news_ingestion_symbol_plan

    plan = build_news_ingestion_symbol_plan(
        {
            "news.ingestion.symbols": "",
            "news.entity.catalog_path": "",
            "news.ingestion.symbol_source": "auto",
        },
        main_engine=FakeMainEngineWithContracts([]),
        akshare_loader=lambda: None,
    )

    assert plan.symbols == ()
    assert plan.source == "global_only"


class FakeMainEngine:
    """Small MainEngine fake."""

    def __init__(self, engine) -> None:
        self.engine = engine

    def get_engine(self, name: str):
        return self.engine if name == "TradingAgents" else None


class FakeMainEngineWithContracts:
    """MainEngine fake exposing cached contracts."""

    def __init__(self, contracts) -> None:
        self.contracts = contracts

    def get_all_contracts(self):
        return list(self.contracts)


class FakeAkshareModule:
    """AKShare fake exposing static A-share code/name rows."""

    def stock_info_a_code_name(self):
        return [
            {"code": "600519", "name": "贵州茅台"},
            {"code": "000001", "name": "平安银行"},
            {"code": "430047", "name": "诺思兰德"},
        ]


def make_contract(symbol: str, exchange: Exchange, product: Product) -> ContractData:
    """Build a minimal vn.py contract for symbol planning tests."""
    return ContractData(
        symbol=symbol,
        exchange=exchange,
        name=symbol,
        product=product,
        size=1,
        pricetick=0.01,
        gateway_name="TEST",
    )


class FakeRuntime:
    """Runtime fake allowing report generation."""

    def __init__(self) -> None:
        self.state = type(
            "State",
            (),
            {
                "enabled": True,
                "mode": TradingAgentsMode.PAPER_ONLY,
                "disabled_reason": "",
            },
        )()

    def can_generate_report(self) -> bool:
        return True

    def mark_success(self, run_id: str) -> None:
        self.last_success = run_id

    def mark_degraded(self, reason: str) -> None:
        self.degraded_reason = reason


class FakeWorker:
    """Worker fake returning a safe report-only result."""

    def run(self, request):
        return TradingAgentsWorkerResponse(
            run_id=request.run_id,
            vt_symbol=request.vt_symbol,
            rating="neutral",
            action="watch",
            confidence=0.5,
            target_weight_hint=0,
            holding_period_hint="manual",
            risk_notes="test",
            report="manual analysis ok",
            raw_state={},
        )


class FakeConnection:
    """Connection fake used by SQL-backed storage wrappers."""

    def __init__(self) -> None:
        self.cursor_obj = FakeCursor()

    def cursor(self):
        return self.cursor_obj

    def commit(self) -> None:
        pass


class FakeCursor:
    """Cursor fake returning empty snapshot rows."""

    description = []

    def execute(self, sql, params=None) -> None:
        pass

    def fetchall(self):
        return []

    def fetchone(self):
        return None

    def close(self) -> None:
        pass


class FakeNewsProvider:
    """No-op news provider for bootstrap tests."""


class FakeNewsScheduler:
    """Scheduler fake recording startup parameters."""

    def __init__(self, **kwargs) -> None:
        self.started = False
        self.symbols = tuple(kwargs["symbols"])
        self.symbol_batch_size = kwargs.get("symbol_batch_size")

    def start(self) -> None:
        self.started = True


class FakeFinancialProvider:
    """No-op financial provider for bootstrap tests."""


class FakeFinancialScheduler:
    """Scheduler fake recording financial startup parameters."""

    def __init__(self, **kwargs) -> None:
        self.started = False
        self.symbols = tuple(kwargs["symbols"])
        self.schedule_times = tuple(kwargs["schedule_times"])
        self.enabled = kwargs["enabled"]
        self.symbol_batch_size = kwargs.get("symbol_batch_size")

    def start(self) -> None:
        self.started = True
