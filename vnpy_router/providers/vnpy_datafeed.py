import importlib
from collections.abc import Callable
from types import ModuleType
from typing import Any

from vnpy.trader.constant import Interval
from vnpy.trader.object import BarData, HistoryRequest

from .base import BaseProvider
from .capability import ProviderCapability, ProviderCostLevel


class VnpyDatafeedProvider(BaseProvider):
    """
    Provider wrapper around an existing vn.py datafeed plugin.

    This keeps broker/vendor integrations such as XT/QMT/RQData on the vn.py
    extension path instead of reimplementing their SDK access in this fork.
    """

    dependency_prefix: str = "vnpy_"

    def __init__(
        self,
        datafeed_name: str,
        provider_name: str | None = None,
        capability: ProviderCapability | None = None,
    ) -> None:
        """"""
        if datafeed_name == "router":
            raise ValueError("vnpy_router cannot wrap itself as a provider")

        self.datafeed_name: str = datafeed_name
        self.name: str = provider_name or f"vnpy_{datafeed_name}"
        self.module_name: str = f"{self.dependency_prefix}{datafeed_name}"
        self.module: ModuleType | None = None
        self.datafeed: Any | None = None
        self.capability: ProviderCapability = capability or _default_capability(self.name)

    def init(self, output: Callable = print) -> bool:
        """
        Import and initialize the wrapped vn.py datafeed plugin.
        """
        if self.datafeed is not None:
            return True

        try:
            self.module = importlib.import_module(self.module_name)
        except ModuleNotFoundError:
            output(
                f"{self.module_name} is not installed; {self.name} provider is disabled. "
                "Install the corresponding vn.py datafeed/gateway plugin instead of "
                "using a direct SDK provider."
            )
            return False

        datafeed_class = getattr(self.module, "Datafeed", None)
        if datafeed_class is None:
            output(f"{self.module_name} does not expose Datafeed")
            return False

        self.datafeed = datafeed_class()
        init = getattr(self.datafeed, "init", None)
        if callable(init):
            return bool(init(output))
        return True

    def query_bar_history(
        self,
        req: HistoryRequest,
        output: Callable = print,
    ) -> list[BarData]:
        """
        Delegate history requests to the wrapped vn.py datafeed.
        """
        if not self.init(output):
            return []

        query = getattr(self.datafeed, "query_bar_history", None)
        if not callable(query):
            output(f"{self.module_name}.Datafeed does not support query_bar_history")
            return []

        bars: list[BarData] = list(query(req, output) or [])
        for bar in bars:
            extra: dict[str, Any] = dict(bar.extra or {})
            extra.setdefault("provider_name", self.name)
            extra.setdefault("provider_endpoint", f"{self.module_name}.Datafeed.query_bar_history")
            extra.setdefault("provider_version", _module_version(self.module))
            extra.setdefault("source_adapter", "vnpy_datafeed")
            bar.extra = extra
        return bars


def _default_capability(provider_name: str) -> ProviderCapability:
    """
    Conservative capability for wrapped vn.py datafeeds.
    """
    return ProviderCapability(
        name=provider_name,
        intervals=frozenset({Interval.MINUTE, Interval.HOUR, Interval.DAILY, Interval.WEEKLY}),
        fields=frozenset({"open", "high", "low", "close", "volume", "turnover"}),
        adjustments=frozenset({"none", "qfq", "hfq"}),
        supports_tick=False,
        realtime=False,
        history=True,
        cost_level=ProviderCostLevel.BROKER,
        realtime_notes="Realtime quotes and trading should use the corresponding vn.py Gateway.",
    )


def _module_version(module: ModuleType | None) -> str:
    """
    Return a best-effort module version for provider traceability.
    """
    if module is None:
        return ""
    return str(getattr(module, "__version__", ""))

