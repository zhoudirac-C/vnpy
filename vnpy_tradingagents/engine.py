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
        return self.financial_reader.load_financial_context(
            vt_symbol,
            as_of=datetime.now(),
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
            symbols=_financial_symbols_from_settings(settings),
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


def _financial_symbols_from_settings(settings: Mapping[str, Any]) -> tuple[str, ...]:
    explicit_symbols = _split_csv_symbols(settings.get("financial.ingestion.symbols", ""))
    if explicit_symbols:
        return explicit_symbols

    catalog_path = str(
        settings.get("financial.ingestion.catalog_path")
        or settings.get("news.entity.catalog_path", "")
        or ""
    ).strip()
    if not catalog_path:
        return ()
    try:
        catalog = SecurityEntityCatalog.from_path(catalog_path)
    except Exception:
        return ()
    return tuple(catalog.entities.keys())
