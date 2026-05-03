from abc import ABC, abstractmethod
from collections.abc import Callable

from vnpy.trader.object import BarData, HistoryRequest


class BaseProvider(ABC):
    """
    Abstract market data provider used by DataProviderRouter.
    """

    name: str = ""

    def init(self, output: Callable = print) -> bool:
        """
        Initialize provider resources.
        """
        return True

    @abstractmethod
    def query_bar_history(
        self,
        req: HistoryRequest,
        output: Callable = print,
    ) -> list[BarData]:
        """
        Query historical bar data.
        """
        pass
