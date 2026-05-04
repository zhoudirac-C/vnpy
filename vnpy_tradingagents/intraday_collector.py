from collections import defaultdict
from collections.abc import Callable
import json
from typing import Any, Protocol

from vnpy.event import Event, EventEngine
from vnpy.trader.event import EVENT_TICK
from vnpy.trader.object import BarData, TickData

from .intraday import IntradaySnapshot, IntradaySnapshotBuilder


CREATE_INTRADAY_SNAPSHOT_SCHEMA: str = """
CREATE TABLE IF NOT EXISTS intraday_snapshot (
    vt_symbol TEXT NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL,
    interval TEXT NOT NULL,
    context JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (vt_symbol, generated_at)
);
"""


UPSERT_INTRADAY_SNAPSHOT_SQL: str = """
INSERT INTO intraday_snapshot (
    vt_symbol,
    generated_at,
    interval,
    context
) VALUES (
    %(vt_symbol)s,
    %(generated_at)s,
    %(interval)s,
    %(context)s
)
ON CONFLICT (vt_symbol, generated_at)
DO UPDATE SET
    interval = EXCLUDED.interval,
    context = EXCLUDED.context,
    created_at = now();
"""


class IntradaySnapshotStorage(Protocol):
    """
    Storage protocol for generated intraday snapshots.
    """

    def save_snapshot(self, snapshot: IntradaySnapshot) -> None:
        pass


class Connection(Protocol):
    """
    Minimal DB-API connection protocol.
    """

    def cursor(self):
        pass

    def commit(self) -> None:
        pass


class IntradaySnapshotCollector:
    """
    Collect Gateway bars/ticks and build replayable intraday snapshots.
    """

    def __init__(
        self,
        window_size: int = 20,
        position_provider: Callable[[str], dict[str, Any]] | None = None,
        trading_rules_provider: Callable[[str], dict[str, Any]] | None = None,
        storage: IntradaySnapshotStorage | None = None,
    ) -> None:
        """"""
        self.builder: IntradaySnapshotBuilder = IntradaySnapshotBuilder(window_size)
        self.position_provider: Callable[[str], dict[str, Any]] = (
            position_provider or _empty_dict_provider
        )
        self.trading_rules_provider: Callable[[str], dict[str, Any]] = (
            trading_rules_provider or _empty_dict_provider
        )
        self.storage: IntradaySnapshotStorage | None = storage
        self.bars: defaultdict[str, list[BarData]] = defaultdict(list)

    def update_bar(self, bar: BarData) -> None:
        """
        Collect a minute bar from Gateway or strategy event flow.
        """
        self.bars[bar.vt_symbol].append(bar)

    def update_tick(self, tick: TickData) -> None:
        """
        Collect a tick by converting it into a compact synthetic bar.
        """
        self.update_bar(_tick_to_bar(tick))

    def build_snapshot(
        self,
        vt_symbol: str,
        news_events: list[dict[str, Any]] | None = None,
    ) -> IntradaySnapshot:
        """
        Build and optionally persist an intraday snapshot.
        """
        snapshot: IntradaySnapshot = self.builder.build(
            vt_symbol=vt_symbol,
            bars=self.bars[vt_symbol],
            position=self.position_provider(vt_symbol),
            trading_rules=self.trading_rules_provider(vt_symbol),
            news_events=news_events,
        )

        if self.storage:
            self.storage.save_snapshot(snapshot)

        return snapshot


class EventEngineIntradayCollector:
    """
    Register IntradaySnapshotCollector on vn.py EventEngine market events.
    """

    def __init__(
        self,
        event_engine: EventEngine,
        collector: IntradaySnapshotCollector,
        bar_event_type: str = "eBar.",
    ) -> None:
        """"""
        self.event_engine: EventEngine = event_engine
        self.collector: IntradaySnapshotCollector = collector
        self.bar_event_type: str = bar_event_type
        self.active: bool = False

    def start(self) -> None:
        """
        Register tick/bar handlers.
        """
        if self.active:
            return
        self.event_engine.register(EVENT_TICK, self.process_tick_event)
        self.event_engine.register(self.bar_event_type, self.process_bar_event)
        self.active = True

    def stop(self) -> None:
        """
        Unregister tick/bar handlers.
        """
        if not self.active:
            return
        self.event_engine.unregister(EVENT_TICK, self.process_tick_event)
        self.event_engine.unregister(self.bar_event_type, self.process_bar_event)
        self.active = False

    def process_tick_event(self, event: Event) -> None:
        """
        Collect tick events without blocking EventEngine.
        """
        tick = event.data
        if isinstance(tick, TickData):
            self.collector.update_tick(tick)

    def process_bar_event(self, event: Event) -> None:
        """
        Collect bar events when a strategy/data recorder emits them.
        """
        bar = event.data
        if isinstance(bar, BarData):
            self.collector.update_bar(bar)


class PostgresIntradaySnapshotStorage:
    """
    PostgreSQL persistence for replayable intraday snapshots.
    """

    def __init__(self, connection: Connection) -> None:
        """"""
        self.connection: Connection = connection

    def create_schema(self) -> None:
        """
        Create intraday snapshot table.
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(CREATE_INTRADAY_SNAPSHOT_SCHEMA)
            self.connection.commit()
        finally:
            cursor.close()

    def save_snapshot(self, snapshot: IntradaySnapshot) -> None:
        """
        Persist one generated snapshot.
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(UPSERT_INTRADAY_SNAPSHOT_SQL, _snapshot_params(snapshot))
            self.connection.commit()
        finally:
            cursor.close()


def _snapshot_params(snapshot: IntradaySnapshot) -> dict[str, Any]:
    """
    Convert snapshot to SQL params.
    """
    return {
        "vt_symbol": snapshot.vt_symbol,
        "generated_at": snapshot.generated_at,
        "interval": snapshot.interval,
        "context": json.dumps(snapshot.to_context(), ensure_ascii=False, sort_keys=True),
    }


def _tick_to_bar(tick: TickData) -> BarData:
    """
    Convert latest tick into a synthetic one-point bar for urgent snapshots.
    """
    bar = BarData(
        symbol=tick.symbol,
        exchange=tick.exchange,
        datetime=tick.datetime,
        interval=None,
        open_price=tick.last_price,
        high_price=tick.last_price,
        low_price=tick.last_price,
        close_price=tick.last_price,
        volume=tick.last_volume or tick.volume,
        turnover=tick.turnover,
        open_interest=tick.open_interest,
        gateway_name=tick.gateway_name,
    )
    bar.extra = {"snapshot_interval": "tick"}
    return bar


def _empty_dict_provider(vt_symbol: str) -> dict[str, Any]:
    """
    Default provider for optional context sections.
    """
    return {}
