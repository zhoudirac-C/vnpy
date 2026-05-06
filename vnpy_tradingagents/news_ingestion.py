from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Protocol, Any

from vnpy.event import EVENT_TIMER, Event, EventEngine
from vnpy.trader.setting import SETTINGS

from vnpy_router.event_storage import NewsEvent, NewsRaw
from vnpy_router.providers.news_external import (
    AkshareGlobalNewsProvider,
    AkshareStockNewsProvider,
    ExternalNewsProvider,
    FetchedNews,
    LocalFileExternalNewsProvider,
    NewsFetchRequest,
    NewsFetchResult,
    NewsProviderChain,
)

from .ops_storage import OpsHeartbeat


@dataclass(frozen=True)
class NewsIngestionSummary:
    """
    Result of one external news ingestion run.
    """

    raw_count: int
    event_count: int
    degraded_sources: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)


class EventStorage(Protocol):
    """
    Storage protocol for news ingestion.
    """

    def save_news_raw(self, news: NewsRaw) -> None:
        pass

    def save_news_event(self, event: NewsEvent) -> None:
        pass


class OpsStorage(Protocol):
    """
    Optional ops storage protocol.
    """

    def save_heartbeat(self, heartbeat: OpsHeartbeat) -> None:
        pass


class ExternalNewsIngestionJob:
    """
    Fetch external news and persist it into local event tables.
    """

    component_name: str = "external_news_ingestion"

    def __init__(
        self,
        provider: ExternalNewsProvider,
        storage: EventStorage,
        ops_storage: OpsStorage | None = None,
        lookback_minutes: int = 1440,
        max_items_per_symbol: int = 50,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        """"""
        self.provider: ExternalNewsProvider = provider
        self.storage: EventStorage = storage
        self.ops_storage: OpsStorage | None = ops_storage
        self.lookback_minutes: int = lookback_minutes
        self.max_items_per_symbol: int = max_items_per_symbol
        self.clock: Callable[[], datetime] = clock

    def run(
        self,
        symbols: Sequence[str],
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> NewsIngestionSummary:
        """
        Run one ingestion batch for symbols/window.
        """
        end_dt: datetime = end or self.clock()
        start_dt: datetime = start or end_dt - timedelta(minutes=self.lookback_minutes)
        result: NewsFetchResult = self.provider.fetch(
            NewsFetchRequest(
                vt_symbols=list(symbols),
                start=start_dt,
                end=end_dt,
                max_items_per_symbol=self.max_items_per_symbol,
            )
        )

        raw_count: int = 0
        event_count: int = 0
        errors: dict[str, str] = dict(result.errors)
        degraded_sources: list[str] = list(result.degraded_sources)

        for item in result.items:
            try:
                self.storage.save_news_raw(item.news)
                raw_count += 1
            except Exception as exc:
                degraded_sources.append("news_raw_storage")
                errors[f"news_raw:{item.news.raw_hash}"] = str(exc)
                continue

            if not item.vt_symbol:
                continue

            try:
                self.storage.save_news_event(_to_news_event(item, end_dt))
                event_count += 1
            except Exception as exc:
                degraded_sources.append("news_event_storage")
                errors[f"news_event:{item.news.raw_hash}:{item.vt_symbol}"] = str(exc)

        summary = NewsIngestionSummary(
            raw_count=raw_count,
            event_count=event_count,
            degraded_sources=_dedup_text(degraded_sources),
            errors=errors,
        )
        self._save_heartbeat(summary)
        return summary

    def _save_heartbeat(self, summary: NewsIngestionSummary) -> None:
        """
        Save best-effort ops heartbeat.
        """
        if not self.ops_storage:
            return
        status: str = "ready" if not summary.errors else "warning"
        heartbeat = OpsHeartbeat(
            component=self.component_name,
            heartbeat_at=self.clock(),
            status=status,
            last_error="; ".join(summary.errors.values()),
            degraded_sources=summary.degraded_sources,
            payload={
                "raw_count": summary.raw_count,
                "event_count": summary.event_count,
                "errors": summary.errors,
            },
        )
        self.ops_storage.save_heartbeat(heartbeat)


class ExternalNewsIngestionScheduler:
    """
    EventEngine timer scheduler for external news ingestion.
    """

    def __init__(
        self,
        event_engine: EventEngine,
        job: ExternalNewsIngestionJob,
        symbols: Sequence[str],
        interval_seconds: int = 900,
        lookback_minutes: int = 1440,
        clock: Callable[[], float] | None = None,
        datetime_clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        """"""
        from time import monotonic

        self.event_engine: EventEngine = event_engine
        self.job: ExternalNewsIngestionJob = job
        self.symbols: tuple[str, ...] = tuple(symbols)
        self.interval_seconds: int = interval_seconds
        self.lookback_minutes: int = lookback_minutes
        self.clock: Callable[[], float] = clock or monotonic
        self.datetime_clock: Callable[[], datetime] = datetime_clock
        self.last_run_at: float | None = None
        self.executor: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=1)
        self.future: Future | None = None
        self.active: bool = False

    def start(self) -> None:
        """
        Register timer callback.
        """
        if self.active:
            return
        self.event_engine.register(EVENT_TIMER, self.process_timer_event)
        self.active = True

    def stop(self) -> None:
        """
        Unregister timer callback and shutdown executor.
        """
        if self.active:
            self.event_engine.unregister(EVENT_TIMER, self.process_timer_event)
            self.active = False
        self.shutdown()

    def shutdown(self) -> None:
        """
        Shutdown scheduler executor.
        """
        self.executor.shutdown(wait=True, cancel_futures=True)

    def process_timer_event(self, event: Event) -> None:
        """
        Throttled EventEngine timer callback.
        """
        if event.type != EVENT_TIMER:
            return
        now: float = self.clock()
        if self.last_run_at is not None and now - self.last_run_at < self.interval_seconds:
            return
        if self.future and not self.future.done():
            return

        self.last_run_at = now
        end_dt: datetime = self.datetime_clock()
        start_dt: datetime = end_dt - timedelta(minutes=self.lookback_minutes)
        self.future = self.executor.submit(
            self.job.run,
            self.symbols,
            start_dt,
            end_dt,
        )

    def trigger(self) -> None:
        """
        Manually trigger using the same async boundary.
        """
        self.process_timer_event(Event(EVENT_TIMER))


def build_news_ingestion_provider(
    settings: Mapping[str, Any] | None = None,
) -> NewsProviderChain:
    """
    Build an external news provider chain from vn.py global settings.
    """
    source: Mapping[str, Any] = settings or SETTINGS
    provider_names: list[str] = _split_names(
        source.get("news.ingestion.providers", "local_file,akshare_stock_news")
    )
    providers: list[ExternalNewsProvider] = []
    for provider_name in provider_names:
        if provider_name == "local_file":
            providers.append(
                LocalFileExternalNewsProvider(
                    str(source.get("news.ingestion.local_path", ""))
                )
            )
        elif provider_name == "akshare_stock_news":
            providers.append(AkshareStockNewsProvider())
        elif provider_name == "akshare_global_news":
            providers.append(
                AkshareGlobalNewsProvider(
                    endpoints=_split_names(
                        source.get(
                            "news.ingestion.akshare.endpoints",
                            "stock_info_global_cls",
                        )
                    )
                )
            )
    return NewsProviderChain(providers)


def _to_news_event(item: FetchedNews, fallback_time: datetime) -> NewsEvent:
    """
    Convert fetched raw news into a symbol-scoped event.
    """
    news = item.news
    occurred_at: datetime = news.published_at or fallback_time
    return NewsEvent(
        event_id=_event_id(news.raw_hash, item.vt_symbol),
        vt_symbol=item.vt_symbol,
        title=news.title,
        summary=news.content,
        event_type=item.event_type,
        occurred_at=occurred_at,
        source=news.source,
        provider_name=news.provider_name,
        url=news.url,
        provider_version=news.provider_version,
        raw_hash=news.raw_hash,
        source_quality=news.source_quality,
        trust_score=news.trust_score,
        spam_score=news.spam_score,
        dedup_window_seconds=news.dedup_window_seconds,
        review_status=news.review_status,
    )


def _event_id(raw_hash: str, vt_symbol: str) -> str:
    """
    Build a stable event id from raw hash and symbol.
    """
    return sha256(f"{raw_hash}:{vt_symbol}".encode()).hexdigest()


def _dedup_text(values: Sequence[str]) -> list[str]:
    """
    Deduplicate text while preserving order.
    """
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result


def _split_names(raw: Any) -> list[str]:
    """
    Split comma/list setting values into names.
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        return [item.strip() for item in raw.split(",") if item.strip()]
    if isinstance(raw, Sequence) and not isinstance(raw, (bytes, bytearray)):
        return [str(item).strip() for item in raw if str(item).strip()]
    return [str(raw).strip()]
