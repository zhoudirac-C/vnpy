import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import Any, Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

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


class CninfoAnnouncementProvider:
    """
    CNINFO official disclosure provider.
    """

    name: str = "cninfo_announcement"
    endpoint: str = "https://www.cninfo.com.cn/new/hisAnnouncement/query"

    def __init__(
        self,
        http_client: Callable[..., Any] | None = None,
        provider_version: str = "",
        timeout_seconds: int = 30,
    ) -> None:
        """"""
        self.http_client = http_client or _json_http_request
        self.provider_version = provider_version or "cninfo:hisAnnouncement"
        self.timeout_seconds = timeout_seconds

    def fetch(
        self,
        request: NewsFetchRequest,
        output: Callable = print,
    ) -> NewsFetchResult:
        """
        Fetch official CNINFO announcements.
        """
        items: list[FetchedNews] = []
        degraded_sources: list[str] = []
        errors: dict[str, str] = {}
        seen_keys: set[tuple[str, str]] = set()
        symbols = list(request.vt_symbols)
        if not symbols:
            return NewsFetchResult()

        for vt_symbol in symbols:
            try:
                payload = self.http_client(
                    url=self.endpoint,
                    method="POST",
                    params=_cninfo_query_params(request, vt_symbol),
                    timeout=self.timeout_seconds,
                    headers={
                        "User-Agent": "Mozilla/5.0 vnpy-router",
                        "Referer": "https://www.cninfo.com.cn/",
                    },
                )
            except Exception as exc:
                degraded_sources.append(self.name)
                errors[f"{self.name}:{vt_symbol}"] = str(exc)
                continue

            count = 0
            for row in _announcement_rows(payload):
                row_vt_symbol = _vt_symbol_from_payload(row)
                if row_vt_symbol and row_vt_symbol != vt_symbol:
                    continue
                raw = _cninfo_row_to_raw(row, self.provider_version)
                if raw is None or not _published_in_window(raw, request.start, request.end):
                    continue
                key = (raw.raw_hash, vt_symbol)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                items.append(
                    FetchedNews(
                        news=raw,
                        vt_symbol=vt_symbol,
                        event_type="announcement",
                    )
                )
                count += 1
                if count >= request.max_items_per_symbol:
                    break

        return NewsFetchResult(
            items=items,
            degraded_sources=_dedup_text(degraded_sources),
            errors=errors,
        )


class SseAnnouncementProvider:
    """
    Shanghai Stock Exchange official announcement provider.
    """

    name: str = "sse_announcement"
    endpoint: str = "https://query.sse.com.cn/security/stock/queryCompanyBulletinNew.do"

    def __init__(
        self,
        http_client: Callable[..., Any] | None = None,
        provider_version: str = "",
        timeout_seconds: int = 30,
    ) -> None:
        """"""
        self.http_client = http_client or _json_http_request
        self.provider_version = provider_version or "sse:queryCompanyBulletinNew"
        self.timeout_seconds = timeout_seconds

    def fetch(
        self,
        request: NewsFetchRequest,
        output: Callable = print,
    ) -> NewsFetchResult:
        """
        Fetch SSE official announcements.
        """
        try:
            payload = self.http_client(
                url=self.endpoint,
                method="GET",
                params=_official_query_params(request),
                timeout=self.timeout_seconds,
                headers={
                    "User-Agent": "Mozilla/5.0 vnpy-router",
                    "Referer": "https://www.sse.com.cn/",
                },
            )
        except Exception as exc:
            return NewsFetchResult(degraded_sources=[self.name], errors={self.name: str(exc)})

        items = []
        for row in _announcement_rows(payload):
            raw = _sse_row_to_raw(row, self.provider_version)
            if raw is None or not _published_in_window(raw, request.start, request.end):
                continue
            items.append(
                FetchedNews(
                    news=raw,
                    vt_symbol=_vt_symbol_from_payload(row),
                    event_type="announcement",
                )
            )
            if len(items) >= request.max_items_per_symbol * max(1, len(request.vt_symbols)):
                break

        return NewsFetchResult(items=items)


class GdeltGlobalNewsProvider:
    """
    GDELT public DOC API provider for macro/global news.
    """

    name: str = "gdelt_global_news"
    endpoint: str = "https://api.gdeltproject.org/api/v2/doc/doc"

    def __init__(
        self,
        query: str = "China economy OR China market OR tariff OR exports",
        http_client: Callable[..., Any] | None = None,
        provider_version: str = "",
        timeout_seconds: int = 30,
    ) -> None:
        """"""
        self.query = query
        self.http_client = http_client or _json_http_request
        self.provider_version = provider_version or "gdelt:doc-v2"
        self.timeout_seconds = timeout_seconds

    def fetch(
        self,
        request: NewsFetchRequest,
        output: Callable = print,
    ) -> NewsFetchResult:
        """
        Fetch global news without forcing symbol links.
        """
        try:
            payload = self.http_client(
                url=self.endpoint,
                method="GET",
                params={
                    "query": self.query,
                    "mode": "ArtList",
                    "format": "json",
                    "maxrecords": request.max_items_per_symbol,
                    "sort": "DateDesc",
                },
                timeout=self.timeout_seconds,
                headers={"User-Agent": "Mozilla/5.0 vnpy-router"},
            )
        except Exception as exc:
            return NewsFetchResult(degraded_sources=[self.name], errors={self.name: str(exc)})

        items = []
        rows = payload.get("articles", []) if isinstance(payload, dict) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            raw = _gdelt_row_to_raw(row, self.provider_version)
            if raw is None or not _published_in_window(raw, request.start, request.end):
                continue
            items.append(FetchedNews(news=raw, vt_symbol="", event_type="macro"))

        return NewsFetchResult(items=items)


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


def _cninfo_row_to_raw(row: dict[str, Any], provider_version: str) -> NewsRaw | None:
    """
    Convert one CNINFO announcement row into NewsRaw.
    """
    title = _first_text(row, "announcementTitle", "title", "公告标题")
    if not title:
        return None
    published_at = _parse_datetime(
        _first_text(row, "announcementTime", "publishTime", "公告时间", "date")
    )
    adjunct_url = _first_text(row, "adjunctUrl", "url", "announcementUrl")
    url = adjunct_url
    if adjunct_url and not adjunct_url.startswith(("http://", "https://")):
        url = f"https://static.cninfo.com.cn/{adjunct_url.lstrip('/')}"
    payload = dict(row)
    payload["provider_endpoint"] = "hisAnnouncement"
    return NewsRaw(
        source="cninfo",
        url=url,
        title=title,
        content=_first_text(row, "summary", "content", "announcementContent") or title,
        published_at=published_at,
        provider_name="cninfo_announcement",
        provider_version=provider_version,
        raw_payload=payload,
        source_quality="official_disclosure",
        trust_score=0.95,
        review_status="accepted",
    )


def _sse_row_to_raw(row: dict[str, Any], provider_version: str) -> NewsRaw | None:
    """
    Convert one SSE announcement row into NewsRaw.
    """
    title = _first_text(row, "TITLE", "title", "announcementTitle", "公告标题")
    if not title:
        return None
    url = _first_text(row, "URL", "url", "BULLETIN_URL")
    payload = dict(row)
    payload["provider_endpoint"] = "queryCompanyBulletinNew"
    return NewsRaw(
        source="sse",
        url=url,
        title=title,
        content=_first_text(row, "SUMMARY", "content", "summary") or title,
        published_at=_parse_datetime(_first_text(row, "SSEDATE", "date", "publishTime")),
        provider_name="sse_announcement",
        provider_version=provider_version,
        raw_payload=payload,
        source_quality="official_disclosure",
        trust_score=0.93,
        review_status="accepted",
    )


def _gdelt_row_to_raw(row: dict[str, Any], provider_version: str) -> NewsRaw | None:
    """
    Convert one GDELT article row into NewsRaw.
    """
    title = _first_text(row, "title", "headline")
    if not title:
        return None
    source = _first_text(row, "domain", "source", "sourcecountry") or "gdelt"
    payload = dict(row)
    payload["provider_endpoint"] = "doc-v2"
    return NewsRaw(
        source=source,
        url=_first_text(row, "url", "link"),
        title=title,
        content=_first_text(row, "summary", "content", "snippet") or title,
        published_at=_parse_datetime(_first_text(row, "seendate", "date", "published_at")),
        provider_name="gdelt_global_news",
        provider_version=provider_version,
        raw_payload=payload,
        source_quality="global_public_news",
        trust_score=0.65,
        review_status="pending",
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


def _announcement_rows(value: Any) -> list[dict[str, Any]]:
    """
    Extract announcement rows from common official JSON shapes.
    """
    if isinstance(value, list):
        return [dict(row) for row in value if isinstance(row, dict)]
    if not isinstance(value, dict):
        return []

    rows: list[dict[str, Any]] = []
    for key in ("announcements", "result", "data", "list"):
        child = value.get(key)
        if isinstance(child, list):
            rows.extend(dict(row) for row in child if isinstance(row, dict))

    classified = value.get("classifiedAnnouncements")
    if isinstance(classified, list):
        for group in classified:
            if isinstance(group, dict):
                rows.extend(_announcement_rows(group.get("announcements", [])))
            elif isinstance(group, list):
                rows.extend(dict(row) for row in group if isinstance(row, dict))
    return rows


def _official_query_params(request: NewsFetchRequest) -> dict[str, Any]:
    """
    Build a minimal date/code query usable by official providers.
    """
    symbols = ",".join(_symbol_without_exchange(symbol) for symbol in request.vt_symbols)
    return {
        "stock": symbols,
        "searchkey": "",
        "category": "",
        "pageNum": 1,
        "pageSize": request.max_items_per_symbol * max(1, len(request.vt_symbols)),
        "column": "sse",
        "tabName": "fulltext",
        "plate": "",
        "seDate": f"{request.start.date()}~{request.end.date()}",
        "beginDate": request.start.date().isoformat(),
        "endDate": request.end.date().isoformat(),
    }


def _cninfo_query_params(request: NewsFetchRequest, vt_symbol: str) -> dict[str, Any]:
    """
    Build CNINFO params. The official endpoint reliably honors symbol searchkey,
    while bare ``stock=code`` can return empty or unrelated rows.
    """
    return {
        "stock": "",
        "searchkey": _symbol_without_exchange(vt_symbol),
        "category": "",
        "pageNum": 1,
        "pageSize": request.max_items_per_symbol,
        "column": "szse",
        "tabName": "fulltext",
        "plate": "",
        "seDate": f"{request.start.date()}~{request.end.date()}",
        "beginDate": request.start.date().isoformat(),
        "endDate": request.end.date().isoformat(),
    }


def _vt_symbol_from_payload(row: dict[str, Any]) -> str:
    """
    Resolve vt_symbol from provider payload codes.
    """
    code = _first_text(row, "vt_symbol")
    if code and "." in code:
        return _normalize_vt_symbol(code)
    code = _first_text(row, "secCode", "securityCode", "SECURITY_CODE", "symbol", "code", "证券代码")
    if not code:
        return ""
    return f"{code}.{_exchange_from_symbol(code)}"


def _json_http_request(
    url: str,
    method: str = "GET",
    params: dict[str, Any] | None = None,
    timeout: int = 30,
    headers: dict[str, str] | None = None,
) -> Any:
    """
    Small stdlib JSON client used by production providers.
    """
    params = params or {}
    headers = headers or {}
    method = method.upper()
    data = None
    request_url = url
    if method == "GET" and params:
        request_url = f"{url}?{urlencode(params)}"
    elif params:
        data = urlencode(params).encode("utf-8")
        headers.setdefault("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8")

    req = Request(request_url, data=data, headers=headers, method=method)
    with urlopen(req, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw)


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


def _parse_datetime(value: Any) -> datetime | None:
    """
    Parse provider datetime text into a datetime.
    """
    if value is None or value == "":
        return None
    if isinstance(value, int | float):
        return _parse_epoch_datetime(float(value))
    text = str(value).strip()
    if text.isdigit():
        return _parse_epoch_datetime(float(text))
    if len(text) == 16 and text[8] == "T" and text.endswith("Z"):
        try:
            return datetime.strptime(text, "%Y%m%dT%H%M%SZ")
        except ValueError:
            pass
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime()


def _parse_epoch_datetime(value: float) -> datetime | None:
    """
    Parse provider epoch seconds/milliseconds into a naive China-market datetime.
    """
    if value <= 0:
        return None
    seconds = value / 1000 if value >= 10_000_000_000 else value
    try:
        return datetime.fromtimestamp(seconds, tz=ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
    except (OverflowError, OSError, ValueError):
        return None


def _symbol_without_exchange(vt_symbol: str) -> str:
    """
    Convert vt_symbol into provider symbol text.
    """
    return vt_symbol.split(".", 1)[0]


def _normalize_vt_symbol(vt_symbol: str) -> str:
    """
    Normalize common A-share suffixes to vn.py exchange names.
    """
    text = vt_symbol.strip().upper()
    if text.endswith(".SH"):
        return text[:-3] + ".SSE"
    if text.endswith(".SZ"):
        return text[:-3] + ".SZSE"
    if text.endswith(".BJ"):
        return text[:-3] + ".BSE"
    return text


def _exchange_from_symbol(symbol: str) -> str:
    """
    Guess exchange from A-share code.
    """
    text = symbol.strip()
    if text.startswith(("6", "9")):
        return "SSE"
    if text.startswith(("8", "4")):
        return "BSE"
    return "SZSE"


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
