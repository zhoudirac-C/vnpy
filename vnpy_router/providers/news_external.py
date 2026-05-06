from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import Any, Protocol

import pandas as pd

from vnpy_router.event_storage import NewsEvent, NewsRaw
from vnpy_router.providers.news import NewsProvider


@dataclass(frozen=True)
class NewsFetchRequest:
    """
    Request window for external news providers.
    """

    vt_symbols: Sequence[str]
    start: datetime
    end: datetime
    max_items_per_symbol: int = 50


@dataclass(frozen=True)
class FetchedNews:
    """
    One raw news item plus an optional symbol link.
    """

    news: NewsRaw
    vt_symbol: str = ""
    event_type: str = "news"


@dataclass(frozen=True)
class NewsFetchResult:
    """
    Provider-neutral external news fetch result.
    """

    items: list[FetchedNews] = field(default_factory=list)
    degraded_sources: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)


class ExternalNewsProvider(Protocol):
    """
    Protocol for low-trust external news ingestion providers.
    """

    name: str

    def fetch(
        self,
        request: NewsFetchRequest,
        output: Callable = print,
    ) -> NewsFetchResult:
        pass


class NewsProviderChain:
    """
    Sequential provider chain with degraded-source aggregation and deduplication.
    """

    def __init__(self, providers: Sequence[ExternalNewsProvider]) -> None:
        """"""
        self.providers: tuple[ExternalNewsProvider, ...] = tuple(providers)

    def fetch(
        self,
        request: NewsFetchRequest,
        output: Callable = print,
    ) -> NewsFetchResult:
        """
        Fetch from each provider and keep the first copy of each raw/symbol pair.
        """
        items: list[FetchedNews] = []
        degraded_sources: list[str] = []
        errors: dict[str, str] = {}
        seen_keys: set[tuple[str, str]] = set()

        for provider in self.providers:
            try:
                result: NewsFetchResult = provider.fetch(request, output=output)
            except Exception as exc:
                name: str = getattr(provider, "name", provider.__class__.__name__)
                degraded_sources.append(name)
                errors[name] = str(exc)
                continue

            degraded_sources.extend(result.degraded_sources)
            errors.update(result.errors)
            for item in result.items:
                key = (item.news.raw_hash, item.vt_symbol)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                items.append(item)

        return NewsFetchResult(
            items=items,
            degraded_sources=_dedup_text(degraded_sources),
            errors=errors,
        )


class LocalFileExternalNewsProvider:
    """
    ExternalNewsProvider wrapper for existing local NewsProvider fixtures.
    """

    name: str = "local_file_news"

    def __init__(self, source_path: str | Path) -> None:
        """"""
        self.source_path: Path = Path(source_path)
        self.provider = NewsProvider(self.source_path)

    def fetch(
        self,
        request: NewsFetchRequest,
        output: Callable = print,
    ) -> NewsFetchResult:
        """
        Load local normalized events and convert them back to raw rows for ingestion smoke.
        """
        if not self.source_path.exists():
            return NewsFetchResult(
                degraded_sources=[self.name],
                errors={self.name: f"local news source does not exist: {self.source_path}"},
            )

        items: list[FetchedNews] = []
        for vt_symbol in request.vt_symbols:
            for event in self.provider.query_events(vt_symbol):
                if not _event_in_window(event, request.start, request.end):
                    continue
                items.append(
                    FetchedNews(
                        news=_event_to_raw(event, self.name),
                        vt_symbol=event.vt_symbol,
                        event_type=event.event_type,
                    )
                )

        return NewsFetchResult(items=items[: request.max_items_per_symbol * len(request.vt_symbols)])


class AkshareStockNewsProvider:
    """
    AKShare stock_news_em provider for low-cost A-share news ingestion.
    """

    name: str = "akshare_stock_news"

    def __init__(self, provider_version: str = "") -> None:
        """"""
        self.provider_version: str = provider_version or "akshare:stock_news_em"
        self.akshare: ModuleType | None = None

    def fetch(
        self,
        request: NewsFetchRequest,
        output: Callable = print,
    ) -> NewsFetchResult:
        """
        Fetch symbol-linked public stock news from AKShare.
        """
        if not self._init(output):
            return NewsFetchResult(
                degraded_sources=[self.name],
                errors={self.name: "akshare is not installed"},
            )

        if not self.akshare:
            return NewsFetchResult(degraded_sources=[self.name])

        items: list[FetchedNews] = []
        degraded_sources: list[str] = []
        errors: dict[str, str] = {}
        for vt_symbol in request.vt_symbols:
            symbol: str = _symbol_without_exchange(vt_symbol)
            try:
                df = self.akshare.stock_news_em(symbol=symbol)
            except Exception as exc:
                degraded_sources.append(self.name)
                errors[f"{self.name}:{vt_symbol}"] = str(exc)
                continue

            rows = _dataframe_rows(df)
            count: int = 0
            for row in rows:
                raw: NewsRaw | None = _row_to_raw_news(
                    row,
                    provider_name=self.name,
                    provider_version=self.provider_version,
                    provider_endpoint="stock_news_em",
                )
                if raw is None or not _published_in_window(raw, request.start, request.end):
                    continue
                items.append(FetchedNews(news=raw, vt_symbol=vt_symbol))
                count += 1
                if count >= request.max_items_per_symbol:
                    break

        return NewsFetchResult(
            items=items,
            degraded_sources=_dedup_text(degraded_sources),
            errors=errors,
        )

    def _init(self, output: Callable) -> bool:
        """
        Import AKShare lazily.
        """
        if self.akshare:
            return True
        try:
            self.akshare = import_module("akshare")
            return True
        except ModuleNotFoundError:
            output("akshare is not installed; AkshareStockNewsProvider is degraded")
            return False


class AkshareGlobalNewsProvider:
    """
    AKShare global finance news provider. Rows are intentionally unlinked to symbols.
    """

    name: str = "akshare_global_news"

    def __init__(
        self,
        endpoints: Sequence[str] | None = None,
        provider_version: str = "",
    ) -> None:
        """"""
        self.endpoints: tuple[str, ...] = tuple(endpoints or ("stock_info_global_cls",))
        self.provider_version: str = provider_version or "akshare:global_news"
        self.akshare: ModuleType | None = None

    def fetch(
        self,
        request: NewsFetchRequest,
        output: Callable = print,
    ) -> NewsFetchResult:
        """
        Fetch global finance news without forcing symbol linkage.
        """
        if not self._init(output):
            return NewsFetchResult(
                degraded_sources=[self.name],
                errors={self.name: "akshare is not installed"},
            )

        if not self.akshare:
            return NewsFetchResult(degraded_sources=[self.name])

        items: list[FetchedNews] = []
        degraded_sources: list[str] = []
        errors: dict[str, str] = {}
        for endpoint in self.endpoints:
            query = getattr(self.akshare, endpoint, None)
            if not callable(query):
                degraded_sources.append(self.name)
                errors[f"{self.name}:{endpoint}"] = "endpoint is not available"
                continue
            try:
                df = query()
            except Exception as exc:
                degraded_sources.append(self.name)
                errors[f"{self.name}:{endpoint}"] = str(exc)
                continue

            for row in _dataframe_rows(df):
                raw = _row_to_raw_news(
                    row,
                    provider_name=self.name,
                    provider_version=self.provider_version,
                    provider_endpoint=endpoint,
                )
                if raw is None or not _published_in_window(raw, request.start, request.end):
                    continue
                items.append(FetchedNews(news=raw, vt_symbol="", event_type="global_news"))

        return NewsFetchResult(
            items=items,
            degraded_sources=_dedup_text(degraded_sources),
            errors=errors,
        )

    def _init(self, output: Callable) -> bool:
        """
        Import AKShare lazily.
        """
        if self.akshare:
            return True
        try:
            self.akshare = import_module("akshare")
            return True
        except ModuleNotFoundError:
            output("akshare is not installed; AkshareGlobalNewsProvider is degraded")
            return False


def _event_to_raw(event: NewsEvent, provider_name: str) -> NewsRaw:
    """
    Convert a local normalized event into a raw row for repeatable ingestion tests.
    """
    return NewsRaw(
        source=event.source,
        url=event.url,
        title=event.title,
        content=event.summary,
        published_at=event.occurred_at,
        provider_name=provider_name,
        provider_version=event.provider_version,
        source_quality=event.source_quality,
        trust_score=event.trust_score,
        spam_score=event.spam_score,
        dedup_window_seconds=event.dedup_window_seconds,
        review_status=event.review_status,
        raw_payload={"event_id": event.event_id},
    )


def _row_to_raw_news(
    row: dict[str, Any],
    provider_name: str,
    provider_version: str,
    provider_endpoint: str,
) -> NewsRaw | None:
    """
    Convert one public news row into NewsRaw using flexible Chinese/English columns.
    """
    title: str = _first_text(row, "新闻标题", "标题", "title", "headline")
    if not title:
        return None
    content: str = _first_text(row, "新闻内容", "内容", "摘要", "content", "summary") or title
    published_at = _parse_datetime(
        _first_text(row, "发布时间", "时间", "日期", "date", "datetime", "published_at")
    )
    source: str = _first_text(row, "文章来源", "来源", "source") or provider_endpoint
    url: str = _first_text(row, "新闻链接", "链接", "url", "link")
    payload = dict(row)
    payload["provider_endpoint"] = provider_endpoint

    return NewsRaw(
        source=source,
        url=url,
        title=title,
        content=content,
        published_at=published_at,
        provider_name=provider_name,
        provider_version=provider_version,
        raw_payload=payload,
        source_quality="public_web",
        trust_score=0.4,
        review_status="pending",
    )


def _dataframe_rows(value: Any) -> list[dict[str, Any]]:
    """
    Convert AKShare DataFrame-like values into dictionaries.
    """
    if value is None:
        return []
    if isinstance(value, pd.DataFrame):
        return [dict(row) for row in value.to_dict(orient="records")]
    if isinstance(value, list):
        return [dict(row) for row in value if isinstance(row, dict)]
    return []


def _published_in_window(news: NewsRaw, start: datetime, end: datetime) -> bool:
    """
    Include undated rows and rows inside the requested window.
    """
    if news.published_at is None:
        return True
    return start <= news.published_at <= end


def _event_in_window(event: NewsEvent, start: datetime, end: datetime) -> bool:
    """
    Return whether an event happened inside the requested window.
    """
    return start <= event.occurred_at <= end


def _first_text(row: dict[str, Any], *keys: str) -> str:
    """
    Return the first non-empty value from a row.
    """
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _parse_datetime(value: str) -> datetime | None:
    """
    Parse provider datetime text into a datetime.
    """
    if not value:
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime()


def _symbol_without_exchange(vt_symbol: str) -> str:
    """
    Convert vt_symbol into provider symbol text.
    """
    return vt_symbol.split(".", 1)[0]


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
