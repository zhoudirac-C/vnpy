from collections.abc import Mapping
from typing import Any
from datetime import datetime

from vnpy.event import EventEngine
from vnpy.trader.engine import BaseEngine, MainEngine
from vnpy_router.security_catalog import SecurityEntityCatalog

from .runtime import (
    TradingAgentsMode,
    TradingAgentsRuntimeController,
    TradingAgentsRuntimeState,
)
from .manual_analysis import ManualAnalysisRequest


class RuntimeStateStorage:
    """
    Storage protocol for persisted TradingAgents runtime state.
    """

    def save_state(self, state: TradingAgentsRuntimeState) -> None:
        pass

    def load_state(self) -> TradingAgentsRuntimeState | None:
        pass


class TradingAgentsEngine(BaseEngine):
    """
    Runtime control engine for TradingAgents integration.
    """

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine) -> None:
        """"""
        super().__init__(main_engine, event_engine, "TradingAgents")
        self.runtime: TradingAgentsRuntimeController = TradingAgentsRuntimeController()
        self.state_storage: RuntimeStateStorage | None = None
        self.manual_analysis_service: Any | None = None
        self.analysis_history_reader: Any | None = None
        self.news_event_reader: Any | None = None
        self.news_ingestion_scheduler: Any | None = None
        self.news_ingestion_error: str = ""
        self.financial_reader: Any | None = None
        self.financial_ingestion_scheduler: Any | None = None
        self.financial_ingestion_error: str = ""
        self.seven_boll_scan_service: Any | None = None
        self.seven_boll_scan_repository: Any | None = None

    def set_seven_boll_scan_service(self, service: Any) -> None:
        """
        Attach the seven-boll scanner service.
        """
        self.seven_boll_scan_service = service

    def set_seven_boll_scan_repository(self, repository: Any) -> None:
        """
        Attach seven-boll scan result repository.
        """
        self.seven_boll_scan_repository = repository

    def run_seven_boll_scan(self, request: Any | None = None) -> Any:
        """
        Run a seven-boll daily scan without requiring TradingAgents AI.
        """
        if self.seven_boll_scan_service is None:
            raise RuntimeError("SevenBoll scan service is not configured")
        if request is None:
            from vnpy_seven_boll.scanner import SevenBollScanRequest

            request = SevenBollScanRequest()
        summary = self.seven_boll_scan_service.scan(request)
        if self.seven_boll_scan_repository is not None:
            save = getattr(self.seven_boll_scan_repository, "save_scan_summary", None)
            if callable(save):
                save(summary, scan_type=getattr(request, "scan_type", "manual"))
        return summary

    def load_latest_seven_boll_scan(self) -> Any:
        """
        Load the newest seven-boll scan summary.
        """
        if self.seven_boll_scan_repository is not None:
            latest = self.seven_boll_scan_repository.load_latest_summary()
            if latest is not None:
                return latest
        if self.seven_boll_scan_service is not None:
            return getattr(self.seven_boll_scan_service, "latest_summary", None)
        return None

    def list_seven_boll_scan_history(self, limit: int = 50) -> list[Any]:
        """
        List seven-boll scan run history.
        """
        if self.seven_boll_scan_repository is None:
            latest = self.load_latest_seven_boll_scan()
            return [latest] if latest is not None else []
        return self.seven_boll_scan_repository.list_scan_runs(limit)

    def run_scan_analysis(self, vt_symbol: str) -> str:
        """
        Trigger one TradingAgents manual analysis from a seven-boll scan row.
        """
        result = self._find_seven_boll_scan_result(vt_symbol)
        if result is None:
            return ""
        bar_datetime = result.bar_datetime if isinstance(result.bar_datetime, datetime) else datetime.now()
        analysis_result = self.run_manual_analysis(
            ManualAnalysisRequest(
                vt_symbol=result.vt_symbol,
                start=bar_datetime,
                end=bar_datetime,
                mode="seven_boll_scan_analysis",
                context_overrides={"seven_boll_scan": result.to_context()},
            )
        )
        response = getattr(analysis_result, "response", None)
        if response is not None and getattr(response, "run_id", ""):
            return response.run_id
        request = getattr(analysis_result, "request", None)
        return getattr(request, "run_id", "")

    def run_batch_scan_analysis(self, symbols: list[str] | tuple[str, ...]) -> list[str]:
        """
        Trigger TradingAgents manual analysis for selected scan symbols.
        """
        run_ids: list[str] = []
        for vt_symbol in symbols:
            run_id = self.run_scan_analysis(vt_symbol)
            if run_id:
                run_ids.append(run_id)
        return run_ids

    def set_state_storage(self, storage: RuntimeStateStorage) -> None:
        """
        Attach persistent runtime storage and restore prior state when available.
        """
        self.state_storage = storage
        restored = storage.load_state()
        if restored is not None:
            self.runtime.state = restored

    def enable(
        self,
        mode: TradingAgentsMode = TradingAgentsMode.REPORT_ONLY,
        live_enabled: bool = False,
    ) -> None:
        """
        Enable TradingAgents runtime.
        """
        self.runtime.enable(mode, live_enabled)
        self._persist_state()

    def disable(self, reason: str = "") -> None:
        """
        Disable TradingAgents runtime.
        """
        self.runtime.disable(reason)
        self._persist_state()

    def pause_manual_takeover(self, reason: str = "manual_takeover") -> None:
        """
        Pause AI usage for operator takeover.
        """
        self.runtime.pause_manual_takeover(reason)
        self._persist_state()

    def get_state(self) -> TradingAgentsRuntimeState:
        """
        Return current runtime state.
        """
        return self.runtime.state

    def set_manual_analysis_service(self, service: Any) -> None:
        """
        Attach the user-triggered manual analysis service used by the UI.
        """
        self.manual_analysis_service = service

    def run_manual_analysis(self, request: Any) -> Any:
        """
        Run TradingAgents manual analysis through the configured service.
        """
        if self.manual_analysis_service is None:
            raise RuntimeError("TradingAgents manual analysis service is not configured")
        return self.manual_analysis_service.run(request)

    def set_analysis_history_reader(self, reader: Any) -> None:
        """
        Attach persisted analysis-history reader used by the UI.
        """
        self.analysis_history_reader = reader

    def load_analysis_history(self, vt_symbol: str = "", limit: int = 100) -> list[Any]:
        """
        Load persisted TradingAgents analysis history for the UI.
        """
        if self.analysis_history_reader is None:
            raise RuntimeError("TradingAgents analysis history reader is not configured")
        return self.analysis_history_reader.load_analysis_history(vt_symbol, limit)

    def set_news_event_reader(self, reader: Any) -> None:
        """
        Attach normalized news-event reader used by the UI.
        """
        self.news_event_reader = reader

    def search_news_events(
        self,
        keyword: str = "",
        vt_symbol: str = "",
        event_type: str = "",
        limit: int = 100,
    ) -> list[Any]:
        """
        Fuzzy-search normalized TradingAgents news context rows.
        """
        if self.news_event_reader is None:
            raise RuntimeError("TradingAgents news event reader is not configured")
        return self.news_event_reader.search_news_events(
            keyword=keyword,
            vt_symbol=vt_symbol,
            event_type=event_type,
            limit=limit,
        )

    def set_news_ingestion_scheduler(self, scheduler: Any) -> None:
        """
        Attach optional in-process external news ingestion scheduler.
        """
        self.news_ingestion_scheduler = scheduler
        self.news_ingestion_error = ""

    def set_news_ingestion_error(self, error: str) -> None:
        """
        Store optional news-ingestion startup diagnostics for the UI.
        """
        self.news_ingestion_error = error

    def set_financial_reader(self, reader: Any) -> None:
        """
        Attach structured financial-context reader used by the UI and manual tools.
        """
        self.financial_reader = reader

    def load_financial_context(self, vt_symbol: str, max_periods: int = 4) -> dict[str, Any]:
        """
        Load point-in-time structured financial context for the UI.
        """
        if self.financial_reader is None:
            raise RuntimeError("TradingAgents financial reader is not configured")
        as_of = datetime.now()
        if not vt_symbol.strip():
            load_latest = getattr(self.financial_reader, "load_latest_financial_context", None)
            if not callable(load_latest):
                raise RuntimeError("TradingAgents financial reader cannot load latest context")
            return load_latest(
                as_of=as_of,
                max_periods=max_periods,
            )
        return self.financial_reader.load_financial_context(
            vt_symbol,
            as_of=as_of,
            max_periods=max_periods,
        )

    def set_financial_ingestion_scheduler(self, scheduler: Any) -> None:
        """
        Attach optional in-process financial ingestion scheduler.
        """
        self.financial_ingestion_scheduler = scheduler
        self.financial_ingestion_error = ""

    def set_financial_ingestion_error(self, error: str) -> None:
        """
        Store optional financial-ingestion startup diagnostics for the UI.
        """
        self.financial_ingestion_error = error

    def trigger_financial_ingestion(self, symbols: list[str] | tuple[str, ...] | None = None) -> str:
        """
        Trigger a one-off financial ingestion run from the UI.
        """
        if self.financial_ingestion_scheduler is None:
            raise RuntimeError("TradingAgents financial ingestion scheduler is not configured")
        selected = [symbol for symbol in (symbols or []) if symbol]
        accepted = self.financial_ingestion_scheduler.trigger(selected or None)
        label = ",".join(selected) if selected else "scheduler_batch"
        if accepted is False:
            return f"financial_ingestion_busy symbols={label}"
        return f"financial_ingestion_triggered symbols={label}"

    def get_financial_ingestion_status(self) -> dict[str, Any]:
        """
        Return financial-ingestion scheduler status for the UI.
        """
        if self.financial_ingestion_scheduler is None:
            return {
                "state": "unconfigured",
                "last_error": self.financial_ingestion_error,
            }
        status = getattr(self.financial_ingestion_scheduler, "status", None)
        if not callable(status):
            return {"state": "unknown"}
        return status()

    def cancel_financial_ingestion(self) -> bool:
        """
        Request cancellation of the current financial-ingestion run.
        """
        if self.financial_ingestion_scheduler is None:
            return False
        cancel = getattr(self.financial_ingestion_scheduler, "cancel", None)
        if not callable(cancel):
            return False
        return bool(cancel())

    def retry_failed_financial_ingestion(self) -> str:
        """
        Retry failed symbols from the previous financial-ingestion run.
        """
        if self.financial_ingestion_scheduler is None:
            raise RuntimeError("TradingAgents financial ingestion scheduler is not configured")
        retry_failed = getattr(self.financial_ingestion_scheduler, "retry_failed", None)
        if not callable(retry_failed):
            raise RuntimeError("TradingAgents financial ingestion scheduler cannot retry failures")
        accepted = retry_failed()
        if not accepted:
            return "financial_ingestion_retry_failed_empty"
        return "financial_ingestion_retry_failed_triggered"

    def apply_financial_ingestion_settings(self, settings: Mapping[str, Any]) -> str:
        """
        Hot-apply financial-ingestion scheduler settings from the UI.
        """
        if self.financial_ingestion_scheduler is None:
            raise RuntimeError("TradingAgents financial ingestion scheduler is not configured")
        apply_settings = getattr(self.financial_ingestion_scheduler, "apply_settings", None)
        if not callable(apply_settings):
            raise RuntimeError("TradingAgents financial ingestion scheduler cannot hot-apply settings")

        schedule_times = _financial_schedule_times(settings)
        apply_settings(
            enabled=_bool_setting(settings.get("financial.ingestion.enabled"), True),
            schedule_times=schedule_times,
            symbols=_financial_symbols_from_settings(settings, self.main_engine),
            lookback_years=_int_setting(settings.get("financial.ingestion.lookback_years"), 5),
            symbol_batch_size=_int_setting(settings.get("financial.ingestion.symbol_batch_size"), 0),
        )
        return "financial_ingestion_settings_applied"

    def close(self) -> None:
        """
        Stop background TradingAgents workers before vn.py exits.
        """
        for scheduler in (self.news_ingestion_scheduler, self.financial_ingestion_scheduler):
            if scheduler is None:
                continue
            stop = getattr(scheduler, "stop", None)
            if callable(stop):
                stop()

    def _persist_state(self) -> None:
        """
        Persist runtime state when storage is configured.
        """
        if self.state_storage:
            self.state_storage.save_state(self.runtime.state)

    def _find_seven_boll_scan_result(self, vt_symbol: str) -> Any | None:
        summary = self.load_latest_seven_boll_scan()
        if summary is None:
            return None
        target = str(vt_symbol or "").strip().upper()
        for result in getattr(summary, "all_candidates", []):
            if str(getattr(result, "vt_symbol", "")).upper() == target:
                return result
        return None


def _bool_setting(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _int_setting(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _split_csv_symbols(value: Any) -> tuple[str, ...]:
    return tuple(
        item.strip()
        for item in str(value or "").replace("，", ",").split(",")
        if item.strip()
    )


def _financial_schedule_times(settings: Mapping[str, Any]) -> tuple[str, ...]:
    schedule = str(settings.get("financial.ingestion.schedule", "20:30")).strip()
    if schedule == "daily_20_30":
        times = ["20:30"]
    else:
        times = [time.strip() for time in schedule.replace("，", ",").split(",") if time.strip()]
    if _bool_setting(settings.get("financial.ingestion.morning_retry_enabled"), True):
        morning = str(settings.get("financial.ingestion.morning_retry_schedule", "08:30")).strip()
        times.append("08:30" if morning == "daily_08_30" else morning)
    return tuple(time for time in times if time)


def _financial_symbols_from_settings(
    settings: Mapping[str, Any],
    main_engine: Any | None = None,
) -> tuple[str, ...]:
    explicit_symbols = _split_csv_symbols(settings.get("financial.ingestion.symbols", ""))
    if explicit_symbols:
        return explicit_symbols

    catalog_path = str(
        settings.get("financial.ingestion.catalog_path")
        or settings.get("news.entity.catalog_path", "")
        or ""
    ).strip()
    if not catalog_path:
        return _financial_symbols_from_runtime_universe(main_engine)
    try:
        catalog = SecurityEntityCatalog.from_path(catalog_path)
    except Exception:
        return _financial_symbols_from_runtime_universe(main_engine)
    return tuple(catalog.entities.keys())


def _financial_symbols_from_runtime_universe(main_engine: Any | None = None) -> tuple[str, ...]:
    """
    Fallback for hot-apply settings when no catalog is configured.
    """
    try:
        from .bootstrap import _symbols_from_akshare_universe, _symbols_from_vnpy_contracts

        contract_symbols = tuple(_symbols_from_vnpy_contracts(main_engine))
        if contract_symbols:
            return contract_symbols
        return tuple(_symbols_from_akshare_universe())
    except Exception:
        return ()
