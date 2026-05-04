import importlib
from collections.abc import Callable
from types import ModuleType

from vnpy.trader.constant import Interval
from vnpy.trader.object import BarData, HistoryRequest

from .base import BaseProvider
from .capability import ProviderCapability, ProviderCostLevel


class QmtProvider(BaseProvider):
    """
    QMT historical data adapter boundary.
    """

    name: str = "qmt"
    dependency: str = "xtquant.xtdata"
    capability: ProviderCapability = ProviderCapability(
        name=name,
        intervals=frozenset({Interval.MINUTE, Interval.DAILY, Interval.WEEKLY}),
        fields=frozenset({"open", "high", "low", "close", "volume", "turnover"}),
        adjustments=frozenset({"none", "qfq", "hfq"}),
        supports_tick=True,
        realtime=False,
        history=True,
        cost_level=ProviderCostLevel.BROKER,
        realtime_notes="Realtime quotes and trading should use the vn.py QMT Gateway.",
    )

    def __init__(self) -> None:
        """"""
        self.xtdata: ModuleType | None = None

    def init(self, output: Callable = print) -> bool:
        """
        Import QMT historical data dependency lazily.
        """
        if self.xtdata:
            return True

        try:
            self.xtdata = importlib.import_module(self.dependency)
        except ModuleNotFoundError:
            output(f"{self.dependency} is not installed; QmtProvider is disabled")
            return False
        return True

    def query_bar_history(
        self,
        req: HistoryRequest,
        output: Callable = print,
    ) -> list[BarData]:
        """
        Placeholder for QMT historical data integration.
        """
        if not self.init(output):
            return []

        output("QmtProvider historical query adapter is not configured yet")
        return []
