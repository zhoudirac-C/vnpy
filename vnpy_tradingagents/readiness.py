import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from importlib.util import find_spec
from pathlib import Path
from typing import Any

from vnpy.trader.setting import SETTINGS
from vnpy_router.peewee import missing_vnpy_postgres_fields

from .llm_secret import resolve_llm_api_key


class ReadinessStatus(Enum):
    """
    Production readiness severity.
    """

    READY = "ready"
    WARNING = "warning"
    FAILED = "failed"


@dataclass(frozen=True)
class ReadinessItem:
    """
    One production readiness check result.
    """

    name: str
    status: ReadinessStatus
    message: str


@dataclass(frozen=True)
class ReadinessReport:
    """
    Aggregated production readiness report.
    """

    items: list[ReadinessItem]

    @property
    def status(self) -> ReadinessStatus:
        """
        Return the worst readiness status.
        """
        statuses: set[ReadinessStatus] = {item.status for item in self.items}
        if ReadinessStatus.FAILED in statuses:
            return ReadinessStatus.FAILED
        if ReadinessStatus.WARNING in statuses:
            return ReadinessStatus.WARNING
        return ReadinessStatus.READY

    def by_name(self, name: str) -> ReadinessItem:
        """
        Return one readiness item by name.
        """
        for item in self.items:
            if item.name == name:
                return item
        raise KeyError(name)


ModuleAvailable = Callable[[str], bool]
PathExists = Callable[[str], bool]


class ProductionReadinessChecker:
    """
    Check runtime prerequisites before production-like TradingAgents runs.
    """

    def __init__(
        self,
        settings: Mapping[str, Any] | None = None,
        environ: Mapping[str, str] | None = None,
        module_available: ModuleAvailable | None = None,
        path_exists: PathExists | None = None,
    ) -> None:
        """"""
        self.settings: Mapping[str, Any] = settings or SETTINGS
        self._environ_supplied: bool = environ is not None
        self.environ: Mapping[str, str] = environ if environ is not None else os.environ
        self.module_available: ModuleAvailable = module_available or _module_available
        self.path_exists: PathExists = path_exists or _path_exists

    def check(self) -> ReadinessReport:
        """
        Run all production readiness checks.
        """
        items: list[ReadinessItem] = []
        missing_postgres_fields: list[str] = missing_vnpy_postgres_fields(self.settings)

        if missing_postgres_fields:
            items.append(
                _failed(
                    "vnpy_postgres_config",
                    "vn.py PostgreSQL settings are incomplete: "
                    + ", ".join(missing_postgres_fields),
                )
            )
        else:
            items.append(
                _ready(
                    "vnpy_postgres_config",
                    "vn.py database.* selects the shared PostgreSQL database",
                )
            )

        if not self.module_available("peewee"):
            items.append(_failed("peewee", "peewee is required for PostgreSQL extension tables"))
        else:
            items.append(_ready("peewee", "peewee dependency is available"))

        if not missing_postgres_fields:
            if not self.module_available("psycopg2"):
                items.append(_failed("psycopg2", "psycopg2 is required for Peewee PostgreSQL connections"))
            else:
                items.append(_ready("psycopg2", "psycopg2 PostgreSQL driver is available"))

        api_key_env_var: str = str(
            self.settings.get("tradingagents.api_key_env_var", "OPENAI_API_KEY")
        )
        api_key = resolve_llm_api_key(
            api_key_env_var,
            environ=self.environ if self._environ_supplied else None,
        )
        if not api_key:
            items.append(_failed("tradingagents_api_key", f"missing API key environment variable: {api_key_env_var}"))
        else:
            items.append(_ready("tradingagents_api_key", "TradingAgents API key environment variable is present"))

        items.extend(self._worker_checks())
        items.extend(self._provider_checks())
        items.append(self._news_ingestion_check())
        return ReadinessReport(items)

    def _worker_checks(self) -> list[ReadinessItem]:
        """
        Check whether a context-only worker factory is configured.
        """
        factory_path = (
            str(self.settings.get("tradingagents.worker_factory", "")).strip()
            or self.environ.get("TRADINGAGENTS_WORKER_FACTORY", "").strip()
        )
        if not factory_path:
            return [
                _warning(
                    "tradingagents_worker",
                    "context-only TradingAgents worker factory is not configured",
                )
            ]

        if ":" not in factory_path:
            return [
                _failed(
                    "tradingagents_worker",
                    "worker factory must use module:function format",
                )
            ]

        module_name, _ = factory_path.split(":", 1)
        if not self.module_available(module_name):
            return [
                _failed(
                    "tradingagents_worker",
                    f"worker factory module is not importable: {module_name}",
                )
            ]

        return [_ready("tradingagents_worker", "context-only worker factory is configured")]

    def _provider_checks(self) -> list[ReadinessItem]:
        """
        Check configured providers for obvious missing dependencies or files.
        """
        providers: list[tuple[str, str]] = _parse_provider_specs(
            self.settings.get("router.providers", "")
        )
        if not providers:
            return [_failed("provider_config", "router.providers is empty")]

        items: list[ReadinessItem] = []
        for name, value in providers:
            if name == "local_file":
                path: str = str(self.settings.get("router.local_path", "")).strip()
                if value:
                    items.append(
                        _warning(
                            "local_file_provider",
                            "local_file path in router.providers is ignored; configure router.local_path for vn.py Datafeed compatibility",
                        )
                    )
                    continue
                if not path:
                    items.append(_warning("local_file_provider", "local_file provider has no router.local_path configured"))
                elif not self.path_exists(path):
                    items.append(_warning("local_file_provider", f"router.local_path does not exist: {path}"))
                else:
                    items.append(_ready("local_file_provider", f"router.local_path exists: {path}"))
            elif name == "akshare":
                if self.module_available("akshare"):
                    items.append(_ready("akshare_provider", "akshare dependency is available"))
                else:
                    items.append(_warning("akshare_provider", "akshare dependency is not installed"))
            elif name == "tushare":
                token = (
                    value
                    or str(self.settings.get("router.tushare.token", ""))
                    or self.environ.get("TUSHARE_TOKEN", "")
                )
                if not token.strip():
                    items.append(_warning("tushare_provider", "TuShare token is not configured"))
                elif not self.module_available("tushare"):
                    items.append(_warning("tushare_provider", "tushare dependency is not installed"))
                else:
                    items.append(_ready("tushare_provider", "TuShare token and dependency are configured"))
            elif name == "qmt":
                if self.module_available("vnpy_xt"):
                    items.append(_ready("qmt_provider", "vnpy_xt datafeed/Gateway plugin is available"))
                else:
                    items.append(_warning("qmt_provider", "QMT should be routed through a vn.py datafeed/Gateway plugin such as vnpy_xt"))
            elif name == "xt":
                if self.module_available("vnpy_xt"):
                    items.append(_ready("xt_provider", "vnpy_xt datafeed/Gateway plugin is available"))
                else:
                    items.append(_warning("xt_provider", "XT should be routed through the vn.py vnpy_xt datafeed/Gateway plugin"))
            elif name == "social":
                if not value:
                    items.append(_warning("social_provider", "social provider has no local/manual source path configured"))
                elif not self.path_exists(value):
                    items.append(_warning("social_provider", f"social source path does not exist: {value}"))
                else:
                    items.append(_ready("social_provider", f"social source path exists: {value}"))
            else:
                items.append(_warning(f"{name}_provider", f"provider has no production readiness checker: {name}"))

        items.append(self._intraday_minute_source_check(providers))
        return items

    def _intraday_minute_source_check(
        self,
        providers: list[tuple[str, str]],
    ) -> ReadinessItem:
        """
        Check whether intraday TradingAgents can rely on a production minute source.
        """
        if not _to_bool(self.settings.get("tradingagents.intraday.enabled", False)):
            return _ready(
                "intraday_minute_source",
                "intraday TradingAgents is disabled; minute source is not required",
            )

        provider_names: set[str] = {name for name, _ in providers}
        if provider_names.intersection({"qmt", "xt"}) and self.module_available("vnpy_xt"):
            return _ready(
                "intraday_minute_source",
                "QMT/XT vn.py plugin is available for production intraday minute data",
            )

        if provider_names.intersection({"qmt", "xt"}):
            return _warning(
                "intraday_minute_source",
                "QMT/XT is configured but vnpy_xt is not available; intraday AI should stay degraded",
            )

        return _warning(
            "intraday_minute_source",
            "no production minute source is configured; AKShare/local_file/TuShare daily data is not enough for intraday AI",
        )

    def _news_ingestion_check(self) -> ReadinessItem:
        """
        Check optional external news ingestion configuration.
        """
        if not _to_bool(self.settings.get("news.ingestion.enabled", False)):
            return _ready(
                "news_ingestion",
                "external news ingestion is disabled; news context may degrade without blocking",
            )

        provider_names: list[str] = _split_names(
            self.settings.get("news.ingestion.providers", "")
        )
        if not provider_names:
            return _warning(
                "news_ingestion",
                "news.ingestion.enabled is true but news.ingestion.providers is empty",
            )

        warnings: list[str] = []
        for provider in provider_names:
            if provider == "local_file":
                path = str(self.settings.get("news.ingestion.local_path", "")).strip()
                if not path:
                    warnings.append("local_file has no news.ingestion.local_path configured")
                elif not self.path_exists(path):
                    warnings.append(f"news.ingestion.local_path does not exist: {path}")
            elif provider in {"akshare_stock_news", "akshare_global_news"}:
                if not self.module_available("akshare"):
                    warnings.append(f"{provider} requires akshare")
            elif provider in {"cninfo_announcement", "sse_announcement", "gdelt_global_news"}:
                continue
            else:
                warnings.append(f"provider has no news ingestion readiness checker: {provider}")

        official_enabled = any(
            provider in {"cninfo_announcement", "sse_announcement"}
            for provider in provider_names
        )
        catalog_path = str(self.settings.get("news.entity.catalog_path", "")).strip()
        if official_enabled:
            if not catalog_path:
                warnings.append("news.entity.catalog_path is required for production entity linking")
            elif not self.path_exists(catalog_path):
                warnings.append(f"news.entity.catalog_path does not exist: {catalog_path}")

        if _to_bool(self.settings.get("news.llm_classifier.enabled", False)):
            env_var = str(self.settings.get("news.llm_classifier.api_key_env_var", "ZHIPU_API_KEY"))
            if not resolve_llm_api_key(env_var, environ=self.environ if self._environ_supplied else None):
                warnings.append(f"news.llm_classifier API key is missing: {env_var}")
            if not catalog_path:
                warnings.append("news.entity.catalog_path is required for LLM stock-link validation")

        if warnings:
            return _warning("news_ingestion", "; ".join(warnings))

        return _ready("news_ingestion", "external news ingestion providers are configured")


def _parse_provider_specs(raw: Any) -> list[tuple[str, str]]:
    """
    Parse provider specs while keeping path-like values for provider types that
    explicitly support them, such as social:/path.
    """
    if not raw:
        return []
    if isinstance(raw, str):
        specs: list[tuple[str, str]] = []
        for item in raw.split(","):
            text: str = item.strip()
            if not text:
                continue
            if ":" in text:
                name, value = text.split(":", 1)
                specs.append((name.strip(), value.strip()))
            else:
                specs.append((text, ""))
        return specs
    if isinstance(raw, list):
        specs = []
        for item in raw:
            if isinstance(item, Mapping):
                specs.append((str(item.get("name", "")), str(item.get("token") or item.get("path") or "")))
            else:
                specs.append((str(item), ""))
        return [(name, value) for name, value in specs if name]
    return []


def _split_names(raw: Any) -> list[str]:
    """
    Split comma/list configuration values into names.
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        return [item.strip() for item in raw.split(",") if item.strip()]
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return [str(raw).strip()]


def _ready(name: str, message: str) -> ReadinessItem:
    """"""
    return ReadinessItem(name, ReadinessStatus.READY, message)


def _warning(name: str, message: str) -> ReadinessItem:
    """"""
    return ReadinessItem(name, ReadinessStatus.WARNING, message)


def _failed(name: str, message: str) -> ReadinessItem:
    """"""
    return ReadinessItem(name, ReadinessStatus.FAILED, message)


def _to_bool(value: Any) -> bool:
    """"""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _module_available(name: str) -> bool:
    """"""
    return find_spec(name) is not None


def _path_exists(path: str) -> bool:
    """"""
    return Path(path).exists()
