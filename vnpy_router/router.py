from collections.abc import Callable, Sequence

from vnpy.trader.object import BarData, HistoryRequest

from .providers.base import BaseProvider


class DataProviderRouter:
    """
    Route historical data requests across multiple providers.
    """

    def __init__(self, providers: Sequence[BaseProvider] | None = None) -> None:
        """"""
        self.providers: list[BaseProvider] = list(providers or [])

    def init(self, output: Callable = print) -> bool:
        """
        Initialize all providers and return whether any provider is usable.
        """
        active: bool = False
        for provider in self.providers:
            active = provider.init(output) or active
        return active

    def query_bar_history(
        self,
        req: HistoryRequest,
        output: Callable = print,
    ) -> list[BarData]:
        """
        Return data from the first provider that has bars for the request.
        """
        for provider in self.providers:
            try:
                bars: list[BarData] = provider.query_bar_history(req, output)
            except Exception as exc:
                output(f"{provider.name} provider failed: {exc}")
                continue

            if bars:
                return bars

        return []
