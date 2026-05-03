from collections.abc import Callable
from pathlib import Path

from vnpy.trader.datafeed import BaseDatafeed
from vnpy.trader.object import BarData, HistoryRequest, TickData
from vnpy.trader.setting import SETTINGS

from .providers.akshare import AkshareProvider
from .providers.local_file import LocalFileProvider
from .router import DataProviderRouter


class Datafeed(BaseDatafeed):
    """
    Datafeed adapter loaded by vn.py when datafeed.name=router.
    """

    def __init__(self) -> None:
        """"""
        local_path: str = SETTINGS.get("router.local_path", "")
        providers = []

        if local_path:
            providers.append(LocalFileProvider(Path(local_path)))

        providers.append(AkshareProvider())

        self.router: DataProviderRouter = DataProviderRouter(providers)

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
