from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from importlib import import_module
from typing import Any

from vnpy.trader.constant import Exchange, Product
from vnpy.trader.setting import SETTINGS
from vnpy_router.event_storage import PostgresEventStorage
from vnpy_router.financial_storage import PostgresFinancialStorage
from vnpy_router.news_entity import SecurityEntityResolver
from vnpy_router.peewee import connect_vnpy_postgres_adapter
from vnpy_router.security_catalog import SecurityEntityCatalog
from vnpy_router.storage import PostgresSnapshotReader, PostgresSnapshotStorage
from vnpy_seven_boll.scanner import SevenBollScanService, VnpySevenBollHistoryProvider
from vnpy_seven_boll.storage import PeeweeSevenBollScanRepository

from .financial_ingestion import (
    FinancialIngestionJob,
    FinancialIngestionScheduler,
    build_financial_ingestion_provider,
)
from .manual_analysis import ManualAnalysisRequest, ManualAnalysisResult, TradingAgentsManualAnalysisService
from .news_ingestion import (
    ExternalNewsIngestionJob,
    ExternalNewsIngestionScheduler,
    build_news_ingestion_provider,
)
from .ops_storage import PostgresOpsStorage
from .runtime import TradingAgentsRuntimeController
from .storage import PostgresAgentStorage, PostgresRuntimeStateStorage
from .toolkit import CompositeSnapshotReader, MarketDataToolkit, build_news_context_filter
from .worker_adapter import TradingAgentsWorkerAdapter
from .worker_process import load_configured_worker


ConnectionFactory = Callable[[Mapping[str, Any]], Any]
WorkerFactory = Callable[[], Any | None]
NewsProviderFactory = Callable[[Mapping[str, Any]], Any]
NewsSchedulerFactory = Callable[..., Any]
FinancialProviderFactory = Callable[[Mapping[str, Any]], Any]
FinancialSchedulerFactory = Callable[..., Any]
AkshareLoader = Callable[[], Any | None]

A_SHARE_EXCHANGES: set[Exchange] = {Exchange.SSE, Exchange.SZSE, Exchange.BSE}
AKSHARE_STOCK_UNIVERSE_ENDPOINTS: tuple[str, ...] = (
    "stock_info_a_code_name",
    "stock_zh_a_spot_em",
    "stock_zh_a_spot",
)


@dataclass(frozen=True)
class NewsIngestionSymbolPlan:
    """
    Symbol universe selected for optional external news ingestion.
    """

    symbols: tuple[str, ...]
    source: str
    batch_size: int


@dataclass(frozen=True)
class FinancialIngestionSymbolPlan:
    """
    Symbol universe selected for low-frequency financial report ingestion.
    """

    symbols: tuple[str, ...]
    source: str
    batch_size: int


class UnavailableManualAnalysisService:
    """
    Report an actionable startup/configuration error to the TradingAgents UI.
    """

    def __init__(self, error_message: str) -> None:
        self.error_message: str = error_message

    def run(self, request: ManualAnalysisRequest) -> ManualAnalysisResult:
        """
        Return a UI-renderable failed result instead of raising not-configured.
        """
        return ManualAnalysisResult(
            status="failed",
            request=None,
            response=None,
            error_message=self.error_message,
        )


def configure_tradingagents_services(
    main_engine: Any,
    settings: Mapping[str, Any] | None = None,
    connection_factory: ConnectionFactory = connect_vnpy_postgres_adapter,
    worker_factory: WorkerFactory = load_configured_worker,
    news_provider_factory: NewsProviderFactory = build_news_ingestion_provider,
    news_scheduler_factory: NewsSchedulerFactory = ExternalNewsIngestionScheduler,
    financial_provider_factory: FinancialProviderFactory = build_financial_ingestion_provider,
    financial_scheduler_factory: FinancialSchedulerFactory = FinancialIngestionScheduler,
) -> bool:
    """
    Wire TradingAgents runtime services after ``TradingAgentsApp`` is added.

    The GUI app registration only creates ``TradingAgentsEngine``. Manual
    analysis additionally needs vn.py PostgreSQL, a snapshot toolkit, a worker
    adapter and persistence. This helper keeps that startup wiring in one place.
    """
    engine = main_engine.get_engine("TradingAgents")
    if engine is None:
        return False

    source_settings: Mapping[str, Any] = settings or SETTINGS
    try:
        connection = connection_factory(source_settings)

        snapshot_storage = PostgresSnapshotStorage(connection)
        snapshot_storage.create_schema()

        agent_storage = PostgresAgentStorage(connection)
        agent_storage.create_schema()

        set_analysis_history_reader = getattr(engine, "set_analysis_history_reader", None)
        if callable(set_analysis_history_reader):
            set_analysis_history_reader(agent_storage)

        event_storage = PostgresEventStorage(connection)
        event_storage.create_schema()
        set_news_event_reader = getattr(engine, "set_news_event_reader", None)
        if callable(set_news_event_reader):
            set_news_event_reader(event_storage)

        financial_storage = PostgresFinancialStorage(connection)
        financial_storage.create_schema()
        set_financial_reader = getattr(engine, "set_financial_reader", None)
        if callable(set_financial_reader):
            set_financial_reader(financial_storage)

        set_state_storage = getattr(engine, "set_state_storage", None)
        if callable(set_state_storage):
            set_state_storage(PostgresRuntimeStateStorage(connection))

        worker = worker_factory() or TradingAgentsWorkerAdapter()
        context_reader = CompositeSnapshotReader(
            snapshot_reader=PostgresSnapshotReader(connection),
            event_reader=event_storage,
            financial_reader=financial_storage,
        )
        engine.set_manual_analysis_service(
            TradingAgentsManualAnalysisService(
                runtime=_runtime(engine),
                toolkit=MarketDataToolkit(
                    context_reader,
                    news_filter=build_news_context_filter(dict(source_settings)),
                ),
                worker=worker,
                storage=agent_storage,
            )
        )
        _configure_news_ingestion(
            engine=engine,
            main_engine=main_engine,
            settings=source_settings,
            connection=connection,
            event_storage=event_storage,
            news_provider_factory=news_provider_factory,
            news_scheduler_factory=news_scheduler_factory,
        )
        _configure_financial_ingestion(
            engine=engine,
            main_engine=main_engine,
            settings=source_settings,
            financial_storage=financial_storage,
            snapshot_storage=snapshot_storage,
            financial_provider_factory=financial_provider_factory,
            financial_scheduler_factory=financial_scheduler_factory,
        )
        _configure_seven_boll_scan(
            engine=engine,
            main_engine=main_engine,
            settings=source_settings,
            connection=connection,
        )
    except Exception as exc:
        engine.set_manual_analysis_service(
            UnavailableManualAnalysisService(
                "TradingAgents manual analysis startup failed: " + str(exc)
            )
        )
        return False

    return True


def _configure_seven_boll_scan(
    *,
    engine: Any,
    main_engine: Any,
    settings: Mapping[str, Any],
    connection: Any,
) -> None:
    """
    Attach seven-boll daily scan service and persistence for the UI.
    """
    provider = VnpySevenBollHistoryProvider(
        main_engine=main_engine,
        settings=settings,
    )
    service = SevenBollScanService(provider)

    set_service = getattr(engine, "set_seven_boll_scan_service", None)
    if callable(set_service):
        set_service(service)
    else:
        engine.seven_boll_scan_service = service

    database = getattr(connection, "database", None)
    if database is None:
        return

    try:
        repository = PeeweeSevenBollScanRepository(database)
        repository.create_schema()
    except Exception as exc:
        write_log = getattr(main_engine, "write_log", None)
        if callable(write_log):
            write_log(f"七轨布林线扫描结果表初始化失败：{exc}")
        return

    set_repository = getattr(engine, "set_seven_boll_scan_repository", None)
    if callable(set_repository):
        set_repository(repository)
    else:
        engine.seven_boll_scan_repository = repository


def build_news_ingestion_symbol_plan(
    settings: Mapping[str, Any] | None = None,
    main_engine: Any | None = None,
    akshare_loader: AkshareLoader | None = None,
) -> NewsIngestionSymbolPlan:
    """
    Resolve the symbol list for optional external news ingestion.

    ``news.ingestion.symbols`` is the explicit watch list. When it is empty,
    ``news.entity.catalog_path`` can be used as a slowly-rotated full-universe
    source. If neither is configured, the live vn.py contract cache is reused
    first, then AKShare is used as a no-account A-share universe fallback.
    If all symbol sources are empty, only global/non-symbol providers can
    produce rows.
    """
    source: Mapping[str, Any] = settings or SETTINGS
    batch_size = max(0, _to_int(source.get("news.ingestion.symbol_batch_size", 50), 50))

    explicit_symbols = _split_symbols(source.get("news.ingestion.symbols", ""))
    if explicit_symbols:
        return NewsIngestionSymbolPlan(
            symbols=tuple(explicit_symbols),
            source="manual",
            batch_size=batch_size,
        )

    symbol_source = str(source.get("news.ingestion.symbol_source", "auto")).strip().lower()
    if symbol_source in {"none", "global_only", "global-only"}:
        return NewsIngestionSymbolPlan(symbols=(), source="global_only", batch_size=batch_size)

    catalog_path = str(source.get("news.entity.catalog_path", "") or "").strip()
    if catalog_path:
        catalog = SecurityEntityCatalog.from_path(catalog_path)
        symbols = tuple(catalog.entities.keys())
        if symbols:
            return NewsIngestionSymbolPlan(
                symbols=symbols,
                source="catalog",
                batch_size=batch_size,
            )

    if symbol_source in {"auto", "vnpy", "vnpy_contracts", "contracts"}:
        symbols = tuple(_symbols_from_vnpy_contracts(main_engine))
        if symbols:
            return NewsIngestionSymbolPlan(
                symbols=symbols,
                source="vnpy_contracts",
                batch_size=batch_size,
            )

    if symbol_source in {"auto", "akshare", "akshare_universe"}:
        symbols = tuple(_symbols_from_akshare_universe(akshare_loader))
        if symbols:
            return NewsIngestionSymbolPlan(
                symbols=symbols,
                source="akshare",
                batch_size=batch_size,
            )

    return NewsIngestionSymbolPlan(symbols=(), source="global_only", batch_size=batch_size)


def build_financial_ingestion_symbol_plan(
    settings: Mapping[str, Any] | None = None,
    main_engine: Any | None = None,
    akshare_loader: AkshareLoader | None = None,
) -> FinancialIngestionSymbolPlan:
    """
    Resolve the symbol list for financial report ingestion.

    Explicit ``financial.ingestion.symbols`` wins. When it is empty, the
    scheduler reuses ``financial.ingestion.catalog_path`` or
    ``news.entity.catalog_path`` as a slow batch stock pool. If no catalog is
    configured, it reuses live vn.py A-share contracts, then AKShare's stock
    universe as a no-account fallback.
    """
    source: Mapping[str, Any] = settings or SETTINGS
    batch_size = max(0, _to_int(source.get("financial.ingestion.symbol_batch_size", 20), 20))

    explicit_symbols = _split_symbols(source.get("financial.ingestion.symbols", ""))
    if explicit_symbols:
        return FinancialIngestionSymbolPlan(
            symbols=tuple(explicit_symbols),
            source="manual",
            batch_size=batch_size,
        )

    catalog_path = str(
        source.get("financial.ingestion.catalog_path")
        or source.get("news.entity.catalog_path", "")
        or ""
    ).strip()
    if catalog_path:
        catalog = SecurityEntityCatalog.from_path(catalog_path)
        symbols = tuple(catalog.entities.keys())
        if symbols:
            return FinancialIngestionSymbolPlan(
                symbols=symbols,
                source="catalog",
                batch_size=batch_size,
            )

    symbols = tuple(_symbols_from_vnpy_contracts(main_engine))
    if symbols:
        return FinancialIngestionSymbolPlan(
            symbols=symbols,
            source="vnpy_contracts",
            batch_size=batch_size,
        )

    symbols = tuple(_symbols_from_akshare_universe(akshare_loader))
    if symbols:
        return FinancialIngestionSymbolPlan(
            symbols=symbols,
            source="akshare",
            batch_size=batch_size,
        )

    return FinancialIngestionSymbolPlan(symbols=(), source="empty", batch_size=batch_size)


def _runtime(engine: Any) -> TradingAgentsRuntimeController:
    """
    Return the engine runtime or a disabled fallback runtime.
    """
    runtime = getattr(engine, "runtime", None)
    if runtime is not None:
        return runtime
    return TradingAgentsRuntimeController()


def _configure_news_ingestion(
    *,
    engine: Any,
    main_engine: Any,
    settings: Mapping[str, Any],
    connection: Any,
    event_storage: PostgresEventStorage,
    news_provider_factory: NewsProviderFactory,
    news_scheduler_factory: NewsSchedulerFactory,
) -> None:
    """
    Start optional external news ingestion in the existing vn.py process.
    """
    if not _to_bool(settings.get("news.ingestion.enabled", False)):
        return

    try:
        ops_storage = PostgresOpsStorage(connection)
        ops_storage.create_schema()

        symbol_plan = build_news_ingestion_symbol_plan(settings, main_engine=main_engine)
        job = ExternalNewsIngestionJob(
            provider=news_provider_factory(settings),
            storage=event_storage,
            ops_storage=ops_storage,
            lookback_minutes=_to_int(settings.get("news.ingestion.lookback_minutes", 1440), 1440),
            max_items_per_symbol=_to_int(
                settings.get("news.ingestion.max_items_per_symbol", 50),
                50,
            ),
            resolver=_build_entity_resolver(settings),
        )

        event_engine = getattr(main_engine, "event_engine", None) or getattr(
            engine,
            "event_engine",
            None,
        )
        scheduler = news_scheduler_factory(
            event_engine=event_engine,
            job=job,
            symbols=symbol_plan.symbols,
            interval_seconds=_to_int(settings.get("news.ingestion.interval_seconds", 900), 900),
            lookback_minutes=_to_int(settings.get("news.ingestion.lookback_minutes", 1440), 1440),
            symbol_batch_size=symbol_plan.batch_size,
        )
        scheduler.start()

        set_scheduler = getattr(engine, "set_news_ingestion_scheduler", None)
        if callable(set_scheduler):
            set_scheduler(scheduler)
        else:
            engine.news_ingestion_scheduler = scheduler
    except Exception as exc:
        set_error = getattr(engine, "set_news_ingestion_error", None)
        if callable(set_error):
            set_error(str(exc))

        write_log = getattr(main_engine, "write_log", None)
        if callable(write_log):
            write_log(f"TradingAgents 新闻定时任务启动失败：{exc}")


def _configure_financial_ingestion(
    *,
    engine: Any,
    main_engine: Any,
    settings: Mapping[str, Any],
    financial_storage: PostgresFinancialStorage,
    snapshot_storage: PostgresSnapshotStorage,
    financial_provider_factory: FinancialProviderFactory,
    financial_scheduler_factory: FinancialSchedulerFactory,
) -> None:
    """
    Register default-on low-frequency financial report ingestion.
    """
    try:
        symbol_plan = build_financial_ingestion_symbol_plan(
            settings,
            main_engine=main_engine,
        )
        schedule_times = _financial_schedule_times(settings)
        job = FinancialIngestionJob(
            provider=financial_provider_factory(settings),
            storage=financial_storage,
            snapshot_storage=snapshot_storage,
            lookback_years=_to_int(settings.get("financial.ingestion.lookback_years", 5), 5),
        )
        event_engine = getattr(main_engine, "event_engine", None) or getattr(
            engine,
            "event_engine",
            None,
        )
        scheduler = financial_scheduler_factory(
            event_engine=event_engine,
            job=job,
            symbols=symbol_plan.symbols,
            enabled=_to_bool(settings.get("financial.ingestion.enabled", True)),
            schedule_times=schedule_times,
            lookback_years=_to_int(settings.get("financial.ingestion.lookback_years", 5), 5),
            symbol_batch_size=symbol_plan.batch_size,
        )
        scheduler.start()

        set_scheduler = getattr(engine, "set_financial_ingestion_scheduler", None)
        if callable(set_scheduler):
            set_scheduler(scheduler)
        else:
            engine.financial_ingestion_scheduler = scheduler
    except Exception as exc:
        set_error = getattr(engine, "set_financial_ingestion_error", None)
        if callable(set_error):
            set_error(str(exc))

        write_log = getattr(main_engine, "write_log", None)
        if callable(write_log):
            write_log(f"TradingAgents 财报定时任务启动失败：{exc}")


def _financial_schedule_times(settings: Mapping[str, Any]) -> tuple[str, ...]:
    """
    Build daily schedule minute list from settings.
    """
    times = [str(settings.get("financial.ingestion.schedule", "20:30") or "20:30")]
    if _to_bool(settings.get("financial.ingestion.morning_retry_enabled", True)):
        times.append(
            str(settings.get("financial.ingestion.morning_retry_schedule", "08:30") or "08:30")
        )
    return tuple(time.strip() for time in times if time.strip())


def _split_symbols(value: Any) -> list[str]:
    """
    Split comma/semicolon separated vt_symbols.
    """
    if isinstance(value, Sequence) and not isinstance(value, str):
        return [str(item).strip().upper() for item in value if str(item).strip()]
    text = str(value or "").strip()
    if not text:
        return []
    for sep in (";", "，", "\n"):
        text = text.replace(sep, ",")
    return [item.strip().upper() for item in text.split(",") if item.strip()]


def _symbols_from_vnpy_contracts(main_engine: Any | None) -> list[str]:
    """
    Build an A-share stock pool from vn.py's cached contracts.
    """
    if main_engine is None:
        return []

    get_all_contracts = getattr(main_engine, "get_all_contracts", None)
    if not callable(get_all_contracts):
        return []

    try:
        contracts = get_all_contracts()
    except Exception:
        return []

    symbols: list[str] = []
    seen: set[str] = set()
    for contract in contracts or []:
        if not _is_ashare_equity_contract(contract):
            continue

        vt_symbol = _normalize_ashare_vt_symbol(
            getattr(contract, "vt_symbol", "") or getattr(contract, "symbol", ""),
            getattr(contract, "exchange", None),
        )
        if vt_symbol and vt_symbol not in seen:
            seen.add(vt_symbol)
            symbols.append(vt_symbol)

    return symbols


def _symbols_from_akshare_universe(akshare_loader: AkshareLoader | None = None) -> list[str]:
    """
    Build an A-share stock pool from low-cost AKShare stock-list endpoints.
    """
    loader = akshare_loader or _load_akshare
    try:
        akshare = loader()
    except Exception:
        return []
    if akshare is None:
        return []

    for endpoint in AKSHARE_STOCK_UNIVERSE_ENDPOINTS:
        query = getattr(akshare, endpoint, None)
        if not callable(query):
            continue
        try:
            rows = _iter_table_rows(query())
        except Exception:
            continue

        symbols = _symbols_from_stock_rows(rows)
        if symbols:
            return symbols

    return []


def _symbols_from_stock_rows(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """
    Convert AKShare stock-list rows into vn.py vt_symbols.
    """
    symbols: list[str] = []
    seen: set[str] = set()
    for row in rows:
        raw_symbol = _first_text(row, "code", "代码", "symbol", "股票代码")
        vt_symbol = _normalize_ashare_vt_symbol(raw_symbol)
        if vt_symbol and vt_symbol not in seen:
            seen.add(vt_symbol)
            symbols.append(vt_symbol)
    return symbols


def _is_ashare_equity_contract(contract: Any) -> bool:
    """
    Return true for Shanghai/Shenzhen/Beijing stock contracts.
    """
    exchange = getattr(contract, "exchange", None)
    product = getattr(contract, "product", None)
    if exchange not in A_SHARE_EXCHANGES:
        return False
    return product == Product.EQUITY


def _normalize_ashare_vt_symbol(value: Any, exchange: Exchange | None = None) -> str:
    """
    Normalize A-share code variants into vn.py vt_symbol form.
    """
    text = str(value or "").strip().upper()
    if not text:
        return ""

    parsed_exchange = exchange
    if "." in text:
        symbol_part, suffix = text.split(".", 1)
        text = symbol_part
        parsed_exchange = parsed_exchange or _exchange_from_suffix(suffix)

    for prefix, prefix_exchange in (
        ("SSE", Exchange.SSE),
        ("SZSE", Exchange.SZSE),
        ("BSE", Exchange.BSE),
        ("SH", Exchange.SSE),
        ("SZ", Exchange.SZSE),
        ("BJ", Exchange.BSE),
    ):
        if text.startswith(prefix):
            text = text[len(prefix) :]
            parsed_exchange = parsed_exchange or prefix_exchange
            break

    symbol = text.zfill(6) if text.isdigit() and len(text) <= 6 else text
    if not symbol.isdigit() or len(symbol) != 6:
        return ""

    final_exchange = parsed_exchange or _infer_ashare_exchange(symbol)
    if final_exchange not in A_SHARE_EXCHANGES:
        return ""
    return f"{symbol}.{final_exchange.value}"


def _exchange_from_suffix(value: str) -> Exchange | None:
    """
    Parse common A-share exchange suffixes.
    """
    return {
        "SH": Exchange.SSE,
        "SSE": Exchange.SSE,
        "SZ": Exchange.SZSE,
        "SZSE": Exchange.SZSE,
        "BJ": Exchange.BSE,
        "BSE": Exchange.BSE,
    }.get(str(value or "").strip().upper())


def _infer_ashare_exchange(symbol: str) -> Exchange:
    """
    Infer A-share exchange from code prefix.
    """
    if symbol.startswith(("6", "9")):
        return Exchange.SSE
    if symbol.startswith(("8", "4")):
        return Exchange.BSE
    return Exchange.SZSE


def _iter_table_rows(data: Any) -> list[Mapping[str, Any]]:
    """
    Convert pandas-like tables or iterable mapping rows into dictionaries.
    """
    if data is None:
        return []
    to_dict = getattr(data, "to_dict", None)
    if callable(to_dict):
        return list(to_dict(orient="records"))
    return [row for row in data if isinstance(row, Mapping)]


def _first_text(row: Mapping[str, Any], *keys: str) -> str:
    """
    Return the first non-empty row value as text.
    """
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _load_akshare() -> Any | None:
    """
    Lazily import AKShare only when it is needed as a fallback universe source.
    """
    try:
        return import_module("akshare")
    except ModuleNotFoundError:
        return None


def _build_entity_resolver(settings: Mapping[str, Any]) -> SecurityEntityResolver:
    """
    Build entity resolver from optional security catalog.
    """
    catalog_path = str(settings.get("news.entity.catalog_path", "") or "").strip()
    if not catalog_path:
        return SecurityEntityResolver()
    return SecurityEntityResolver(SecurityEntityCatalog.from_path(catalog_path))


def _to_bool(value: Any) -> bool:
    """
    Convert common UI setting values to bool.
    """
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _to_int(value: Any, default: int) -> int:
    """
    Convert an integer setting with fallback.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
