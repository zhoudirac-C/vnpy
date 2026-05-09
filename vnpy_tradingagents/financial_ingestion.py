from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any, Protocol

from vnpy.event import EVENT_TIMER, Event, EventEngine
from vnpy.trader.setting import SETTINGS
from vnpy_router.financial_storage import (
    FinancialIndicatorSnapshot,
    FinancialReportDocument,
    FinancialStatementSnapshot,
)
from vnpy_router.providers.financial import (
    AkshareEastmoneyStatementProvider,
    AkshareFinancialIndicatorProvider,
    AkshareSinaStatementProvider,
    CninfoReportProvider,
    ExchangeReportProvider,
    FinancialFetchRequest,
    FinancialFetchResult,
    FinancialProvider,
    FinancialProviderChain,
)
from vnpy_router.storage import PayloadSnapshot


class FinancialStorage(Protocol):
    def save_statement_snapshot(self, snapshot: FinancialStatementSnapshot) -> None:
        pass

    def save_indicator_snapshot(self, snapshot: FinancialIndicatorSnapshot) -> None:
        pass

    def save_report_document(self, document: FinancialReportDocument) -> None:
        pass


class PayloadSnapshotStorage(Protocol):
    def save_payload_snapshot(self, snapshot: PayloadSnapshot) -> None:
        pass


@dataclass(frozen=True)
class FinancialIngestionSummary:
    """
    Result of one financial ingestion run.
    """

    statement_count: int
    indicator_count: int
    document_count: int
    payload_snapshot_count: int
    degraded_sources: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class FinancialQualityReport:
    """
    Compact source-quality report for one symbol's latest financial context.
    """

    vt_symbol: str
    latest_report_period: str
    quality_status: str
    missing_statement_types: list[str] = field(default_factory=list)
    has_indicator: bool = False
    has_official_document: bool = False
    provider_names: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """
        JSON-friendly representation for storage and TradingAgents context.
        """
        return {
            "vt_symbol": self.vt_symbol,
            "latest_report_period": self.latest_report_period,
            "quality_status": self.quality_status,
            "missing_statement_types": list(self.missing_statement_types),
            "has_indicator": self.has_indicator,
            "has_official_document": self.has_official_document,
            "provider_names": list(self.provider_names),
        }


class FinancialQualityScorer:
    """
    Score whether structured financial context is complete enough for AI use.
    """

    required_statement_types: tuple[str, ...] = (
        "balance_sheet",
        "income_statement",
        "cash_flow",
    )
    official_sources: frozenset[str] = frozenset({"cninfo", "sse", "szse", "bse", "exchange"})

    def score(
        self,
        vt_symbol: str,
        statements: Sequence[FinancialStatementSnapshot],
        indicators: Sequence[FinancialIndicatorSnapshot],
        documents: Sequence[FinancialReportDocument],
    ) -> FinancialQualityReport:
        latest_period = _latest_report_period(statements, indicators)
        statement_types = {
            statement.statement_type
            for statement in statements
            if not statements or statement.report_period == latest_period
        }
        if not statement_types:
            statement_types = {statement.statement_type for statement in statements}
        missing_statement_types = [
            statement_type
            for statement_type in self.required_statement_types
            if statement_type not in statement_types
        ]
        has_indicator = any(
            indicator.report_period == latest_period for indicator in indicators
        ) or bool(indicators)
        has_official_document = any(
            document.source in self.official_sources
            and (document.report_period == latest_period or latest_period == datetime(1970, 1, 1))
            for document in documents
        )
        provider_names = sorted(
            {
                item.provider_name
                for item in [*statements, *indicators, *documents]
                if item.provider_name
            }
        )
        if not statements and not indicators and not documents:
            quality_status = "failed"
        elif not missing_statement_types and has_indicator and has_official_document:
            quality_status = "primary"
        elif not missing_statement_types:
            quality_status = "fallback"
        else:
            quality_status = "degraded"
        return FinancialQualityReport(
            vt_symbol=vt_symbol,
            latest_report_period=_date(latest_period),
            quality_status=quality_status,
            missing_statement_types=missing_statement_types,
            has_indicator=has_indicator,
            has_official_document=has_official_document,
            provider_names=provider_names,
        )


class FundamentalSnapshotBuilder:
    """
    Build compact TradingAgents fundamental/valuation payload snapshots.
    """

    def __init__(
        self,
        provider_name: str = "financial_ingestion",
        quality_scorer: FinancialQualityScorer | None = None,
    ) -> None:
        self.provider_name = provider_name
        self.quality_scorer = quality_scorer or FinancialQualityScorer()

    def build(
        self,
        vt_symbol: str,
        statements: Sequence[FinancialStatementSnapshot],
        indicators: Sequence[FinancialIndicatorSnapshot],
        documents: Sequence[FinancialReportDocument],
    ) -> dict[str, PayloadSnapshot]:
        latest_period = _latest_report_period(statements, indicators)
        as_of = _latest_announcement_date(statements, indicators, documents)
        income = _latest_statement(statements, "income_statement", latest_period)
        cash_flow = _latest_statement(statements, "cash_flow", latest_period)
        balance = _latest_statement(statements, "balance_sheet", latest_period)
        indicator = _latest_indicator(indicators, latest_period)
        quality_report = self.quality_scorer.score(
            vt_symbol=vt_symbol,
            statements=statements,
            indicators=indicators,
            documents=documents,
        )

        payload = {
            "latest_report_period": _date(latest_period),
            "announcement_date": _date(as_of),
            "quality_report": quality_report.as_dict(),
            "revenue": {
                "current": _first_metric(
                    income,
                    ("OPERATE_INCOME", "TOTAL_OPERATE_INCOME", "营业收入", "营业总收入", "revenue"),
                )
            },
            "net_profit": {
                "current": _first_metric(
                    income,
                    ("NETPROFIT", "PARENT_NETPROFIT", "净利润", "归母净利润", "net_profit"),
                )
            },
            "operating_cash_flow": {
                "current": _first_metric(
                    cash_flow,
                    (
                        "NETCASH_OPERATE",
                        "经营活动产生的现金流量净额",
                        "经营现金流量净额",
                        "operating_cash_flow",
                    ),
                )
            },
            "total_assets": _first_metric(balance, ("TOTAL_ASSETS", "资产总计", "总资产", "total_assets")),
            "total_liabilities": _first_metric(
                balance,
                ("TOTAL_LIABILITIES", "负债合计", "总负债", "total_liabilities"),
            ),
            "roe": _first_metric(indicator, ("ROEJQ", "净资产收益率", "roe", "ROE")),
            "gross_margin": _first_metric(indicator, ("XSMLL", "销售毛利率", "毛利率", "gross_margin")),
            "net_margin": _first_metric(indicator, ("XSJLL", "销售净利率", "净利率", "net_margin")),
            "debt_to_assets": _first_metric(indicator, ("ZCFZL", "资产负债率", "debt_to_assets")),
            "asset_turnover": _first_metric(indicator, ("TOAZZL", "总资产周转率", "asset_turnover")),
            "bps": _first_metric(indicator, ("BPS", "每股净资产", "bps")),
            "eps": _first_metric(indicator, ("EPSJB", "BASIC_EPS", "基本每股收益", "eps")),
            "documents": [
                {
                    "title": document.title,
                    "source": document.source,
                    "pdf_url": document.pdf_url,
                }
                for document in documents
                if document.vt_symbol == vt_symbol
            ],
            "missing_fields": [],
        }
        payload["missing_fields"] = [
            key
            for key in ("revenue", "net_profit", "operating_cash_flow", "roe")
            if _is_missing(payload.get(key))
        ]

        fundamentals = PayloadSnapshot(
            snapshot_type="fundamentals",
            vt_symbol=vt_symbol,
            as_of=as_of,
            provider_name=self.provider_name,
            provider_version="p28",
            quality_status=_fundamentals_quality_status(
                payload["missing_fields"],
                quality_report.quality_status,
            ),
            payload=payload,
        )
        valuation = PayloadSnapshot(
            snapshot_type="valuation",
            vt_symbol=vt_symbol,
            as_of=as_of,
            provider_name=self.provider_name,
            provider_version="p28",
            quality_status="degraded",
            payload={
                "latest_report_period": _date(latest_period),
                "announcement_date": _date(as_of),
                "missing_fields": ["valuation_provider_missing"],
                "quality_status": "degraded",
            },
        )
        return {"fundamentals": fundamentals, "valuation": valuation}


class FinancialIngestionJob:
    """
    Fetch financial reports and persist structured records plus TradingAgents snapshots.
    """

    def __init__(
        self,
        provider: FinancialProvider,
        storage: FinancialStorage,
        snapshot_storage: PayloadSnapshotStorage | None = None,
        snapshot_builder: FundamentalSnapshotBuilder | None = None,
        lookback_years: int = 5,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self.provider = provider
        self.storage = storage
        self.snapshot_storage = snapshot_storage
        self.snapshot_builder = snapshot_builder or FundamentalSnapshotBuilder()
        self.lookback_years = lookback_years
        self.clock = clock

    def run(
        self,
        symbols: Sequence[str],
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> FinancialIngestionSummary:
        end_dt = end or self.clock()
        start_dt = start or _years_before(end_dt, self.lookback_years)
        result: FinancialFetchResult = self.provider.fetch(
            FinancialFetchRequest(
                vt_symbols=tuple(symbols),
                start=start_dt,
                end=end_dt,
                lookback_years=self.lookback_years,
            )
        )

        statement_count = 0
        indicator_count = 0
        document_count = 0
        payload_snapshot_count = 0
        errors = dict(result.errors)
        degraded_sources = list(result.degraded_sources)
        result_statements = _dedup_financial_statements(result.statements)
        result_indicators = _dedup_financial_indicators(result.indicators)
        result_documents = _dedup_financial_documents(result.documents)
        quality_by_symbol = _score_financial_records(
            self.snapshot_builder.quality_scorer,
            symbols,
            result_statements,
            result_indicators,
            result_documents,
        )
        statements = [
            _apply_statement_quality(statement, quality_by_symbol.get(statement.vt_symbol))
            for statement in result_statements
        ]
        indicators = [
            _apply_indicator_quality(indicator, quality_by_symbol.get(indicator.vt_symbol))
            for indicator in result_indicators
        ]

        for statement in statements:
            try:
                self.storage.save_statement_snapshot(statement)
                statement_count += 1
            except Exception as exc:
                errors[f"statement:{statement.vt_symbol}:{statement.statement_type}"] = str(exc)
                degraded_sources.append("financial_statement_storage")

        for indicator in indicators:
            try:
                self.storage.save_indicator_snapshot(indicator)
                indicator_count += 1
            except Exception as exc:
                errors[f"indicator:{indicator.vt_symbol}:{indicator.report_period}"] = str(exc)
                degraded_sources.append("financial_indicator_storage")

        for document in result_documents:
            try:
                self.storage.save_report_document(document)
                document_count += 1
            except Exception as exc:
                errors[f"document:{document.document_id}"] = str(exc)
                degraded_sources.append("financial_document_storage")

        if self.snapshot_storage is not None:
            for vt_symbol in symbols:
                snapshots = self.snapshot_builder.build(
                    vt_symbol=vt_symbol,
                    statements=[item for item in statements if item.vt_symbol == vt_symbol],
                    indicators=[item for item in indicators if item.vt_symbol == vt_symbol],
                    documents=[item for item in result_documents if item.vt_symbol == vt_symbol],
                )
                for snapshot in snapshots.values():
                    self.snapshot_storage.save_payload_snapshot(snapshot)
                    payload_snapshot_count += 1

        return FinancialIngestionSummary(
            statement_count=statement_count,
            indicator_count=indicator_count,
            document_count=document_count,
            payload_snapshot_count=payload_snapshot_count,
            degraded_sources=_dedup_text(degraded_sources),
            errors=errors,
        )


class FinancialIngestionScheduler:
    """
    Low-frequency EventEngine scheduler for financial report ingestion.
    """

    def __init__(
        self,
        event_engine: EventEngine,
        job: FinancialIngestionJob,
        symbols: Sequence[str],
        enabled: bool = True,
        schedule_times: Sequence[str] = ("20:30", "08:30"),
        lookback_years: int = 5,
        symbol_batch_size: int = 0,
        datetime_clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self.event_engine = event_engine
        self.job = job
        self.symbols = tuple(symbols)
        self.enabled = enabled
        self.schedule_times = frozenset(schedule_times)
        self.lookback_years = lookback_years
        self.symbol_batch_size = max(0, symbol_batch_size)
        self.datetime_clock = datetime_clock
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.future: Future | None = None
        self.active = False
        self.last_run_key = ""
        self.symbol_cursor = 0
        self.last_started_at: datetime | None = None
        self.last_finished_at: datetime | None = None
        self.last_symbols: tuple[str, ...] = ()
        self.last_failed_symbols: tuple[str, ...] = ()
        self.last_summary: Any | None = None
        self.last_error: str = ""
        self.cancel_requested = False

    def start(self) -> None:
        if self.active:
            return
        self.event_engine.register(EVENT_TIMER, self.process_timer_event)
        self.active = True

    def stop(self) -> None:
        if self.active:
            self.event_engine.unregister(EVENT_TIMER, self.process_timer_event)
            self.active = False
        self.shutdown()

    def shutdown(self) -> None:
        self.executor.shutdown(wait=True, cancel_futures=True)

    def process_timer_event(self, event: Event) -> None:
        if event.type != EVENT_TIMER or not self.enabled:
            return
        now = self.datetime_clock()
        minute = now.strftime("%H:%M")
        if minute not in self.schedule_times:
            return
        run_key = now.strftime("%Y-%m-%d %H:%M")
        if run_key == self.last_run_key:
            return
        if self.future and not self.future.done():
            return

        if self._submit(self._next_symbol_batch(), now):
            self.last_run_key = run_key

    def trigger(self, symbols: Sequence[str] | None = None) -> bool:
        """
        Manually trigger a one-off ingestion run.
        """
        now = self.datetime_clock()
        selected = tuple(symbols) if symbols is not None else self._next_symbol_batch()
        return self._submit(selected, now)

    def cancel(self) -> bool:
        """
        Request cancellation of the current ingestion run.
        """
        if not self.future or self.future.done():
            return False
        self.cancel_requested = True
        self.future.cancel()
        return True

    def retry_failed(self) -> bool:
        """
        Retry only symbols that failed in the previous run.
        """
        if not self.last_failed_symbols:
            return False
        now = self.datetime_clock()
        return self._submit(self.last_failed_symbols, now)

    def status(self) -> dict[str, Any]:
        """
        Return current scheduler state for UI progress display.
        """
        if self.future and not self.future.done():
            state = "cancel_requested" if self.cancel_requested else "running"
        elif self.last_started_at:
            state = "cancel_requested" if self.cancel_requested else "completed"
        else:
            state = "idle"

        return {
            "state": state,
            "active": self.active,
            "enabled": self.enabled,
            "schedule_times": sorted(self.schedule_times),
            "lookback_years": self.lookback_years,
            "symbol_batch_size": self.symbol_batch_size,
            "symbol_count": len(self.symbols),
            "last_started_at": self.last_started_at,
            "last_finished_at": self.last_finished_at,
            "last_symbols": list(self.last_symbols),
            "last_failed_symbols": list(self.last_failed_symbols),
            "last_summary": _summary_to_dict(self.last_summary),
            "last_error": self.last_error,
            "cancel_requested": self.cancel_requested,
        }

    def apply_settings(
        self,
        *,
        enabled: bool | None = None,
        schedule_times: Sequence[str] | None = None,
        symbols: Sequence[str] | None = None,
        lookback_years: int | None = None,
        symbol_batch_size: int | None = None,
    ) -> None:
        """
        Hot-apply low-frequency scheduler settings from the TradingAgents UI.
        """
        if enabled is not None:
            self.enabled = enabled
        if schedule_times is not None:
            self.schedule_times = frozenset(schedule_times)
        if symbols is not None:
            self.symbols = tuple(symbols)
            self.symbol_cursor = 0
        if lookback_years is not None:
            self.lookback_years = max(1, lookback_years)
        if symbol_batch_size is not None:
            self.symbol_batch_size = max(0, symbol_batch_size)

    def _submit(self, symbols: Sequence[str], now: datetime) -> bool:
        if self.future and not self.future.done():
            self.last_error = "financial_ingestion_busy"
            return False

        selected = tuple(symbols)
        self.last_started_at = now
        self.last_finished_at = None
        self.last_symbols = selected
        self.last_failed_symbols = ()
        self.last_summary = None
        self.last_error = ""
        self.cancel_requested = False
        self.future = self.executor.submit(
            self._run_job,
            selected,
            _years_before(now, self.lookback_years),
            now,
        )
        return True

    def _run_job(
        self,
        symbols: Sequence[str],
        start: datetime,
        end: datetime,
    ) -> FinancialIngestionSummary:
        try:
            if self.cancel_requested:
                summary = FinancialIngestionSummary(
                    statement_count=0,
                    indicator_count=0,
                    document_count=0,
                    payload_snapshot_count=0,
                    degraded_sources=["financial_ingestion_cancelled"],
                    errors={"cancelled": "cancelled_before_start"},
                )
            else:
                summary = self.job.run(symbols, start, end)
            self.last_summary = summary
            self.last_failed_symbols = _failed_symbols_from_summary(summary, symbols)
            return summary
        except Exception as exc:
            self.last_error = str(exc)
            summary = FinancialIngestionSummary(
                statement_count=0,
                indicator_count=0,
                document_count=0,
                payload_snapshot_count=0,
                degraded_sources=["financial_ingestion_failed"],
                errors={"financial_ingestion": str(exc)},
            )
            self.last_summary = summary
            self.last_failed_symbols = tuple(symbols)
            return summary
        finally:
            self.last_finished_at = end

    def _next_symbol_batch(self) -> tuple[str, ...]:
        if not self.symbols:
            return ()
        if self.symbol_batch_size <= 0 or self.symbol_batch_size >= len(self.symbols):
            return self.symbols
        start = self.symbol_cursor % len(self.symbols)
        end = start + self.symbol_batch_size
        if end <= len(self.symbols):
            batch = self.symbols[start:end]
        else:
            batch = self.symbols[start:] + self.symbols[: end - len(self.symbols)]
        self.symbol_cursor = end % len(self.symbols)
        return batch


def _summary_to_dict(summary: Any | None) -> dict[str, Any]:
    if summary is None:
        return {}
    if isinstance(summary, dict):
        return dict(summary)
    if isinstance(summary, FinancialIngestionSummary):
        return asdict(summary)
    return {"value": summary}


def _failed_symbols_from_summary(
    summary: Any,
    fallback_symbols: Sequence[str],
) -> tuple[str, ...]:
    summary_dict = _summary_to_dict(summary)
    errors = summary_dict.get("errors") or {}
    if not isinstance(errors, dict) or not errors:
        return ()
    fallback_set = set(fallback_symbols)
    failed = tuple(key for key in errors if key in fallback_set)
    return failed or tuple(fallback_symbols)


def build_financial_ingestion_provider(
    settings: Mapping[str, Any] | None = None,
) -> FinancialProviderChain:
    """
    Build financial provider chain from vn.py settings.
    """
    source = settings or SETTINGS
    provider_names = _split_names(
        source.get(
            "financial.ingestion.providers",
            "akshare_sina,akshare_eastmoney,akshare_indicator,cninfo_report,exchange_report",
        )
    )
    providers: list[FinancialProvider] = []
    for provider_name in provider_names:
        if provider_name == "akshare_sina":
            providers.append(AkshareSinaStatementProvider())
        elif provider_name == "akshare_eastmoney":
            providers.append(AkshareEastmoneyStatementProvider())
        elif provider_name == "akshare_indicator":
            providers.append(AkshareFinancialIndicatorProvider())
        elif provider_name == "cninfo_report":
            providers.append(CninfoReportProvider())
        elif provider_name in {"exchange_report", "sse_report"}:
            providers.append(ExchangeReportProvider())
    return FinancialProviderChain(providers)


def _score_financial_records(
    scorer: FinancialQualityScorer,
    symbols: Sequence[str],
    statements: Sequence[FinancialStatementSnapshot],
    indicators: Sequence[FinancialIndicatorSnapshot],
    documents: Sequence[FinancialReportDocument],
) -> dict[str, FinancialQualityReport]:
    reports: dict[str, FinancialQualityReport] = {}
    for vt_symbol in symbols:
        reports[vt_symbol] = scorer.score(
            vt_symbol=vt_symbol,
            statements=[item for item in statements if item.vt_symbol == vt_symbol],
            indicators=[item for item in indicators if item.vt_symbol == vt_symbol],
            documents=[item for item in documents if item.vt_symbol == vt_symbol],
        )
    return reports


def _dedup_financial_statements(
    statements: Sequence[FinancialStatementSnapshot],
) -> list[FinancialStatementSnapshot]:
    result: list[FinancialStatementSnapshot] = []
    seen: set[tuple[str, datetime, str, str]] = set()
    for statement in statements:
        key = (
            statement.vt_symbol,
            statement.report_period,
            statement.statement_type,
            statement.provider_name,
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(statement)
    return result


def _dedup_financial_indicators(
    indicators: Sequence[FinancialIndicatorSnapshot],
) -> list[FinancialIndicatorSnapshot]:
    result: list[FinancialIndicatorSnapshot] = []
    seen: set[tuple[str, datetime, str]] = set()
    for indicator in indicators:
        key = (indicator.vt_symbol, indicator.report_period, indicator.provider_name)
        if key in seen:
            continue
        seen.add(key)
        result.append(indicator)
    return result


def _dedup_financial_documents(
    documents: Sequence[FinancialReportDocument],
) -> list[FinancialReportDocument]:
    result: list[FinancialReportDocument] = []
    seen: set[str] = set()
    for document in documents:
        if document.document_id in seen:
            continue
        seen.add(document.document_id)
        result.append(document)
    return result


def _fundamentals_quality_status(missing_fields: Sequence[str], source_quality: str) -> str:
    if source_quality == "failed":
        return "failed"
    if missing_fields:
        return "degraded"
    return source_quality


def _apply_statement_quality(
    statement: FinancialStatementSnapshot,
    quality_report: FinancialQualityReport | None,
) -> FinancialStatementSnapshot:
    if quality_report is None:
        return statement
    return replace(
        statement,
        quality_status=quality_report.quality_status,
        quality_report=quality_report.as_dict(),
    )


def _apply_indicator_quality(
    indicator: FinancialIndicatorSnapshot,
    quality_report: FinancialQualityReport | None,
) -> FinancialIndicatorSnapshot:
    if quality_report is None:
        return indicator
    return replace(
        indicator,
        quality_status=quality_report.quality_status,
        quality_report=quality_report.as_dict(),
    )


def _latest_report_period(
    statements: Sequence[FinancialStatementSnapshot],
    indicators: Sequence[FinancialIndicatorSnapshot],
) -> datetime:
    values = [item.report_period for item in statements] + [item.report_period for item in indicators]
    return max(values) if values else datetime(1970, 1, 1)


def _latest_announcement_date(
    statements: Sequence[FinancialStatementSnapshot],
    indicators: Sequence[FinancialIndicatorSnapshot],
    documents: Sequence[FinancialReportDocument],
) -> datetime:
    values = (
        [item.announcement_date for item in statements]
        + [item.announcement_date for item in indicators]
        + [item.announcement_date for item in documents]
    )
    return max(values) if values else datetime(1970, 1, 1)


def _latest_statement(
    statements: Sequence[FinancialStatementSnapshot],
    statement_type: str,
    report_period: datetime,
) -> Mapping[str, Any]:
    candidates = [
        item
        for item in statements
        if item.statement_type == statement_type and item.report_period == report_period
    ]
    if not candidates:
        candidates = [item for item in statements if item.statement_type == statement_type]
    if not candidates:
        return {}
    payload = dict(candidates[0].payload)
    return payload.get("raw_fields", payload)


def _latest_indicator(
    indicators: Sequence[FinancialIndicatorSnapshot],
    report_period: datetime,
) -> Mapping[str, Any]:
    candidates = [item for item in indicators if item.report_period == report_period]
    if not candidates:
        candidates = list(indicators)
    if not candidates:
        return {}
    payload = dict(candidates[0].payload)
    return payload.get("raw_fields", payload)


def _first_metric(source: Mapping[str, Any], names: Sequence[str]) -> float | None:
    for name in names:
        value = source.get(name)
        if value not in {"", None, "--"}:
            try:
                return float(str(value).replace(",", ""))
            except ValueError:
                return None
    return None


def _is_missing(value: Any) -> bool:
    if isinstance(value, Mapping):
        return value.get("current") is None
    return value is None


def _date(value: datetime) -> str:
    return value.date().isoformat()


def _years_before(value: datetime, years: int) -> datetime:
    try:
        return value.replace(year=value.year - max(1, years))
    except ValueError:
        return value - timedelta(days=365 * max(1, years))


def _split_names(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [item.strip() for item in raw.split(",") if item.strip()]
    if isinstance(raw, Sequence) and not isinstance(raw, (bytes, bytearray)):
        return [str(item).strip() for item in raw if str(item).strip()]
    return [str(raw).strip()]


def _dedup_text(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result
