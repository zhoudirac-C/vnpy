import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from vnpy.trader.datafeed import BaseDatafeed
from vnpy.trader.object import BarData, HistoryRequest, TickData
from vnpy.trader.setting import SETTINGS

from .providers.akshare import AkshareProvider
from .providers.base import BaseProvider
from .providers.local_file import LocalFileProvider
from .router import DataProviderRouter


DEFAULT_PROVIDER_ORDER: tuple[str, ...] = ("local_file", "akshare")


class Datafeed(BaseDatafeed):
    """
    Datafeed adapter loaded by vn.py when datafeed.name=router.
    """

    def __init__(self) -> None:
        """"""
        self.router: DataProviderRouter = DataProviderRouter(_build_providers())

    def init(self, output: Callable = print) -> bool:
        """
        Initialize configured data providers.
        """
        return self.router.init(output)

    def query_bar_history(
        self,
        req: HistoryRequest,
        output: Callable = print,
    ) -> list[BarData]:
        """
        Query bar history from the first provider with available data.
        """
        return self.router.query_bar_history(req, output)

    def query_tick_history(
        self,
        req: HistoryRequest,
        output: Callable = print,
    ) -> list[TickData]:
        """
        Tick history is provider dependent and unsupported in Phase 1.
        """
        output("vnpy_router Phase 1 does not provide tick history")
        return []


def _build_providers() -> list[BaseProvider]:
    """
    Build providers from SETTINGS while preserving legacy router.local_path.
    """
    provider_configs: list[dict[str, Any]] = _parse_provider_configs(
        SETTINGS.get("router.providers", "")
    )
    providers: list[BaseProvider] = []

    for config in provider_configs:
        provider: BaseProvider | None = _build_provider(config)
        if provider is not None:
            providers.append(provider)

    return providers


def _parse_provider_configs(raw_config: Any) -> list[dict[str, Any]]:
    """
    Parse provider config from comma-separated text, JSON text, list, or dict.
    """
    if raw_config is None:
        return _default_provider_configs()

    if isinstance(raw_config, str):
        text: str = raw_config.strip()
        if not text:
            return _default_provider_configs()

        if text.startswith(("[", "{")):
            try:
                parsed_config: Any = json.loads(text)
            except json.JSONDecodeError:
                parsed_config = None
            else:
                return _parse_provider_configs(parsed_config)

        return [{"name": name} for name in _split_provider_names(text)]

    if isinstance(raw_config, Mapping):
        providers: Any = raw_config.get("providers")
        if providers is not None:
            return _parse_provider_configs(providers)

        name: str = str(raw_config.get("name", "")).strip()
        return [dict(raw_config)] if name else []

    if isinstance(raw_config, Sequence):
        configs: list[dict[str, Any]] = []
        for item in raw_config:
            if isinstance(item, str):
                configs.extend({"name": name} for name in _split_provider_names(item))
            elif isinstance(item, Mapping) and item.get("name"):
                configs.append(dict(item))
        return configs

    return _default_provider_configs()


def _split_provider_names(text: str) -> list[str]:
    """
    Split a comma-separated provider list.
    """
    return [name.strip() for name in text.split(",") if name.strip()]


def _default_provider_configs() -> list[dict[str, Any]]:
    """
    Return default provider order.
    """
    return [{"name": name} for name in DEFAULT_PROVIDER_ORDER]


def _build_provider(config: Mapping[str, Any]) -> BaseProvider | None:
    """
    Instantiate a provider from a normalized config dictionary.
    """
    name: str = str(config.get("name", "")).strip()

    if name == "local_file":
        local_path: Any = config.get("path") or SETTINGS.get("router.local_path", "")
        if not local_path:
            return None
        return LocalFileProvider(Path(str(local_path)))

    if name == "akshare":
        return AkshareProvider()

    return None
