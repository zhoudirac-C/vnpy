from pathlib import Path

from vnpy_router.event_storage import NewsEvent

from .event_file import load_event_file


class NewsProvider:
    """
    Local/news-file provider for symbol, sector and earnings events.
    """

    name: str = "news"

    def __init__(self, source_path: str | Path) -> None:
        """"""
        self.source_path: Path = Path(source_path)

    def query_events(self, vt_symbol: str) -> list[NewsEvent]:
        """
        Return news events for a symbol.
        """
        events: list[NewsEvent] = load_event_file(self.source_path, self.name)
        return [event for event in events if event.vt_symbol == vt_symbol]
