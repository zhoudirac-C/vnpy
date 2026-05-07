from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Protocol, Any

from vnpy.event import EVENT_TIMER, Event, EventEngine
from vnpy.trader.setting import SETTINGS

from vnpy_router.event_storage import EventQualityReport, EventSymbolLink, NewsEvent, NewsRaw
from vnpy_router.news_classifier import EventClassifier
from vnpy_router.news_dedup import NewsDeduper
from vnpy_router.news_entity import EntityResolution, ResolvedEntityLink, SecurityEntityResolver
from vnpy_router.news_llm_classifier import LlmMessageClassification, LlmMessageClassifier
from vnpy_router.news_quality import NewsQualityScorer
from vnpy_router.providers.news_external import (
    AkshareGlobalNewsProvider,
    AkshareStockNewsProvider,
    CninfoAnnouncementProvider,
    ExternalNewsProvider,
    FetchedNews,
    GdeltGlobalNewsProvider,
    LocalFileExternalNewsProvider,
    NewsFetchRequest,
    NewsFetchResult,
    NewsProviderChain,
    SseAnnouncementProvider,
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

    def save_event_symbol_link(self, link: EventSymbolLink) -> None:
        pass

    def save_event_quality_report(self, report: EventQualityReport) -> None:
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
        resolver: SecurityEntityResolver | None = None,
        classifier: EventClassifier | None = None,
        scorer: NewsQualityScorer | None = None,
        deduper: NewsDeduper | None = None,
        llm_classifier: LlmMessageClassifier | None = None,
        llm_mode: str = "scheduled_ingestion",
    ) -> None:
        """"""
        self.provider: ExternalNewsProvider = provider
        self.storage: EventStorage = storage
        self.ops_storage: OpsStorage | None = ops_storage
        self.lookback_minutes: int = lookback_minutes
        self.max_items_per_symbol: int = max_items_per_symbol
        self.clock: Callable[[], datetime] = clock
        self.resolver: SecurityEntityResolver = resolver or SecurityEntityResolver()
        self.classifier: EventClassifier = classifier or EventClassifier()
        self.scorer: NewsQualityScorer = scorer or NewsQualityScorer()
        self.deduper: NewsDeduper = deduper or NewsDeduper()
        self.llm_classifier: LlmMessageClassifier | None = llm_classifier
        self.llm_mode: str = llm_mode

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

            event_type = self.classifier.classify(item.news)
            if item.event_type and item.event_type not in {"news", "global_news"}:
                event_type = item.event_type

            resolution = self.resolver.resolve(
                title=item.news.title,
                content=item.news.content,
                payload=item.news.raw_payload,
            )
            links = _links_for_item(item, resolution, event_type)
            llm_result: LlmMessageClassification | None = None
            if not links and self.llm_classifier and event_type in {"industry", "macro", "news"}:
                try:
                    llm_result = self.llm_classifier.classify_and_link(
                        item.news,
                        mode=self.llm_mode,
                    )
                    event_type = _normalize_llm_event_type(llm_result.event_type, event_type)
                    links = llm_result.links
                except Exception as exc:
                    degraded_sources.append("llm_message_classifier")
                    errors[f"llm_classifier:{item.news.raw_hash}"] = str(exc)

            if not links:
                self._save_quality_report(
                    item.news,
                    event_type=event_type,
                    status="pending",
                    duplicate_count=0,
                    blocked_count=0,
                    payload={
                        "warnings": resolution.warnings,
                        "reason": "no_symbol_link",
                        "llm_dropped_symbols": llm_result.dropped_symbols if llm_result else [],
                        "llm_limitations": llm_result.limitations if llm_result else [],
                    },
                    as_of=end_dt,
                )
                continue

            for link in links:
                dedup = self.deduper.register(item.news, vt_symbol=link.vt_symbol)
                quality = self.scorer.score(
                    item.news,
                    link_confidence=link.confidence,
                    event_type=event_type,
                    duplicate=dedup.is_duplicate,
                )
                event = _to_news_event(
                    item,
                    fallback_time=end_dt,
                    vt_symbol=link.vt_symbol,
                    event_type=event_type,
                    trust_score=quality.trust_score,
                    relevance_score=quality.relevance_score,
                    spam_score=quality.spam_score,
                    review_status=quality.review_status,
                    cluster_id=dedup.cluster_id,
                    link=link,
                )
                try:
                    self.storage.save_news_event(event)
                    event_count += 1
                except Exception as exc:
                    degraded_sources.append("news_event_storage")
                    errors[f"news_event:{item.news.raw_hash}:{link.vt_symbol}"] = str(exc)
                    continue

                self._save_event_symbol_link(event, link, quality.relevance_score)
                self._save_quality_report(
                    item.news,
                    event_type=event_type,
                    status=quality.review_status,
                    duplicate_count=dedup.duplicate_count,
                    blocked_count=1 if quality.review_status == "blocked" else 0,
                    payload={
                        "event_id": event.event_id,
                        "vt_symbol": link.vt_symbol,
                        "link_reason": link.link_reason or link.reason,
                        "quality_reason": quality.reason,
                        "warnings": resolution.warnings,
                        "llm_dropped_symbols": llm_result.dropped_symbols if llm_result else [],
                        "llm_limitations": llm_result.limitations if llm_result else [],
                    },
                    as_of=end_dt,
                )

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

    def _save_event_symbol_link(
        self,
        event: NewsEvent,
        link: ResolvedEntityLink,
        relevance_score: float,
    ) -> None:
        """
        Persist link best-effort for storages that support it.
        """
        save_link = getattr(self.storage, "save_event_symbol_link", None)
        if not callable(save_link):
            return
        save_link(
            EventSymbolLink(
                event_id=event.event_id,
                vt_symbol=link.vt_symbol,
                sector=link.sector,
                topic=link.topic,
                confidence=link.confidence,
                relevance_score=relevance_score,
                link_reason=link.link_reason or link.reason,
                provider_name=event.provider_name,
                provider_version=event.provider_version,
            )
        )

    def _save_quality_report(
        self,
        news: NewsRaw,
        event_type: str,
        status: str,
        duplicate_count: int,
        blocked_count: int,
        payload: dict[str, Any],
        as_of: datetime,
    ) -> None:
        """
        Persist quality report best-effort for storages that support it.
        """
        save_report = getattr(self.storage, "save_event_quality_report", None)
        if not callable(save_report):
            return
        report_payload = dict(payload)
        report_payload["event_type"] = event_type
        report_payload["review_status"] = status
        save_report(
            EventQualityReport(
                report_id=_event_id(news.raw_hash, f"quality:{payload.get('vt_symbol', event_type)}"),
                source=news.source,
                provider_name=news.provider_name,
                as_of=as_of,
                source_quality=news.source_quality,
                trust_score=news.trust_score,
                spam_score=news.spam_score,
                duplicate_count=duplicate_count,
                reviewed_count=1 if status in {"accepted", "pending", "duplicate"} else 0,
                blocked_count=blocked_count,
                payload=report_payload,
            )
        )


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
        source.get(
            "news.ingestion.providers",
            "cninfo_announcement,sse_announcement,gdelt_global_news,akshare_stock_news",
        )
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
        elif provider_name == "cninfo_announcement":
            providers.append(
                CninfoAnnouncementProvider(
                    timeout_seconds=int(source.get("news.ingestion.timeout_seconds", 30) or 30)
                )
            )
        elif provider_name == "sse_announcement":
            providers.append(
                SseAnnouncementProvider(
                    timeout_seconds=int(source.get("news.ingestion.timeout_seconds", 30) or 30)
                )
            )
        elif provider_name == "gdelt_global_news":
            providers.append(
                GdeltGlobalNewsProvider(
                    query=str(source.get("news.ingestion.gdelt_query", "")).strip()
                    or "China economy OR China market OR tariff OR exports",
                    timeout_seconds=int(source.get("news.ingestion.timeout_seconds", 30) or 30),
                )
            )
    return NewsProviderChain(providers)


def _to_news_event(
    item: FetchedNews,
    fallback_time: datetime,
    vt_symbol: str | None = None,
    event_type: str | None = None,
    trust_score: float | None = None,
    relevance_score: float | None = None,
    spam_score: float | None = None,
    review_status: str | None = None,
    cluster_id: str = "",
    link: ResolvedEntityLink | None = None,
) -> NewsEvent:
    """
    Convert fetched raw news into a symbol-scoped event.
    """
    news = item.news
    occurred_at: datetime = news.published_at or fallback_time
    symbol = vt_symbol or item.vt_symbol
    return NewsEvent(
        event_id=_event_id(news.raw_hash, symbol),
        vt_symbol=symbol,
        title=news.title,
        summary=news.content,
        event_type=event_type or item.event_type,
        occurred_at=occurred_at,
        source=news.source,
        provider_name=news.provider_name,
        url=news.url,
        provider_version=news.provider_version,
        raw_hash=news.raw_hash,
        source_quality=news.source_quality,
        trust_score=news.trust_score if trust_score is None else trust_score,
        relevance_score=news.relevance_score if relevance_score is None else relevance_score,
        spam_score=news.spam_score if spam_score is None else spam_score,
        cluster_id=cluster_id or news.cluster_id,
        link_confidence=link.confidence if link else 0,
        link_reason=(link.link_reason or link.reason) if link else "",
        sector=link.sector if link else "",
        topic=link.topic if link else "",
        dedup_window_seconds=news.dedup_window_seconds,
        review_status=news.review_status if review_status is None else review_status,
    )


def _links_for_item(
    item: FetchedNews,
    resolution: EntityResolution,
    event_type: str,
) -> list[ResolvedEntityLink]:
    """
    Combine direct provider symbol links and entity resolver links.
    """
    links: dict[str, ResolvedEntityLink] = {}
    if item.vt_symbol:
        links[item.vt_symbol] = ResolvedEntityLink(
            vt_symbol=item.vt_symbol,
            confidence=0.9,
            reason="provider_symbol",
        )

    for link in resolution.links:
        current = links.get(link.vt_symbol)
        if current is None or link.confidence > current.confidence:
            links[link.vt_symbol] = link

    if not links and event_type == "macro":
        links["GLOBAL.MACRO"] = ResolvedEntityLink(
            vt_symbol="GLOBAL.MACRO",
            confidence=0.8,
            reason="macro_event",
            sector="macro",
            topic="macro",
        )

    return sorted(links.values(), key=lambda link: link.vt_symbol)


def _normalize_llm_event_type(event_type: str, fallback: str) -> str:
    """
    Keep LLM event type compatible with current event taxonomy.
    """
    normalized = event_type.strip().lower()
    if normalized in {"industry", "macro"}:
        return normalized
    if normalized == "policy":
        if fallback in {"industry", "macro"}:
            return fallback
        return "macro"
    return fallback


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
