from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from importlib import import_module
from typing import Any, Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import pandas as pd

from vnpy_router.financial_storage import (
    FinancialIndicatorSnapshot,
    FinancialReportDocument,
    FinancialStatementSnapshot,
    build_document_id,
)


@dataclass(frozen=True)
class FinancialFetchRequest:
    """
    Request window for financial report providers.
    """

    vt_symbols: Sequence[str]
    start: datetime
    end: datetime
    lookback_years: int = 5
    max_periods_per_symbol: int = 20


@dataclass(frozen=True)
class FinancialFetchResult:
    """
    Provider-neutral financial fetch result.
    """

    statements: list[FinancialStatementSnapshot] = field(default_factory=list)
    indicators: list[FinancialIndicatorSnapshot] = field(default_factory=list)
    documents: list[FinancialReportDocument] = field(default_factory=list)
    degraded_sources: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)


class FinancialProvider(Protocol):
    """
    Protocol for structured financial report providers.
    """

    name: str

    def fetch(self, request: FinancialFetchRequest, output: Callable = print) -> FinancialFetchResult:
        pass


class FinancialProviderChain:
    """
    Sequential provider chain for financial statements and indicators.
    """

    def __init__(self, providers: Sequence[FinancialProvider]) -> None:
        self.providers = tuple(providers)

    def fetch(self, request: FinancialFetchRequest, output: Callable = print) -> FinancialFetchResult:
        statements: list[FinancialStatementSnapshot] = []
        indicators: list[FinancialIndicatorSnapshot] = []
        documents: list[FinancialReportDocument] = []
        degraded_sources: list[str] = []
        errors: dict[str, str] = {}

        for provider in self.providers:
            try:
                result = provider.fetch(request, output=output)
            except Exception as exc:
                name = getattr(provider, "name", provider.__class__.__name__)
                degraded_sources.append(name)
                errors[name] = str(exc)
                continue
            statements.extend(result.statements)
            indicators.extend(result.indicators)
            documents.extend(result.documents)
            degraded_sources.extend(result.degraded_sources)
            errors.update(result.errors)

        return FinancialFetchResult(
            statements=statements,
            indicators=indicators,
            documents=documents,
            degraded_sources=_dedup_text(degraded_sources),
            errors=errors,
        )


class AkshareSinaStatementProvider:
    """
    AKShare wrapper for Sina balance/profit/cash-flow statement APIs.
    """

    name = "akshare_sina"

    statement_symbols: Mapping[str, str] = {
        "balance_sheet": "资产负债表",
        "income_statement": "利润表",
        "cash_flow": "现金流量表",
    }

    def __init__(self, provider_version: str = "") -> None:
        self.provider_version = provider_version or "akshare:stock_financial_report_sina"

    def fetch(self, request: FinancialFetchRequest, output: Callable = print) -> FinancialFetchResult:
        try:
            akshare = import_module("akshare")
        except ModuleNotFoundError as exc:
            return FinancialFetchResult(
                degraded_sources=[self.name],
                errors={self.name: str(exc)},
            )

        statements: list[FinancialStatementSnapshot] = []
        degraded_sources: list[str] = []
        errors: dict[str, str] = {}
        for vt_symbol in request.vt_symbols:
            stock = _akshare_prefixed_symbol(vt_symbol)
            for statement_type, symbol in self.statement_symbols.items():
                try:
                    frame = akshare.stock_financial_report_sina(stock=stock, symbol=symbol)
                except Exception as exc:
                    degraded_sources.append(self.name)
                    errors[f"{self.name}:{vt_symbol}:{statement_type}"] = str(exc)
                    continue
                statements.extend(
                    _frame_to_statements(
                        frame=frame,
                        vt_symbol=vt_symbol,
                        statement_type=statement_type,
                        provider_name=self.name,
                        provider_version=self.provider_version,
                        max_periods=request.max_periods_per_symbol,
                    )
                )

        return FinancialFetchResult(
            statements=statements,
            degraded_sources=_dedup_text(degraded_sources),
            errors=errors,
        )


class AkshareEastmoneyStatementProvider:
    """
    AKShare wrapper for Eastmoney by-report financial statement APIs.
    """

    name = "akshare_eastmoney"

    endpoints: Mapping[str, tuple[str, ...]] = {
        "balance_sheet": ("stock_balance_sheet_by_report_em", "stock_balance_sheet_by_yearly_em"),
        "income_statement": ("stock_profit_sheet_by_report_em", "stock_profit_sheet_by_yearly_em"),
        "cash_flow": ("stock_cash_flow_sheet_by_report_em", "stock_cash_flow_sheet_by_yearly_em"),
    }

    def __init__(self, provider_version: str = "") -> None:
        self.provider_version = provider_version or "akshare:eastmoney_by_report"

    def fetch(self, request: FinancialFetchRequest, output: Callable = print) -> FinancialFetchResult:
        try:
            akshare = import_module("akshare")
        except ModuleNotFoundError as exc:
            return FinancialFetchResult(
                degraded_sources=[self.name],
                errors={self.name: str(exc)},
            )

        statements: list[FinancialStatementSnapshot] = []
        degraded_sources: list[str] = []
        errors: dict[str, str] = {}
        symbol = ""
        for vt_symbol in request.vt_symbols:
            symbol = _akshare_market_symbol(vt_symbol)
            for statement_type, endpoint_names in self.endpoints.items():
                try:
                    frame = _call_first_endpoint(akshare, endpoint_names, symbol)
                except Exception as exc:
                    degraded_sources.append(self.name)
                    errors[f"{self.name}:{vt_symbol}:{statement_type}"] = str(exc)
                    continue
                statements.extend(
                    _frame_to_statements(
                        frame=frame,
                        vt_symbol=vt_symbol,
                        statement_type=statement_type,
                        provider_name=self.name,
                        provider_version=self.provider_version,
                        max_periods=request.max_periods_per_symbol,
                    )
                )

        return FinancialFetchResult(
            statements=statements,
            degraded_sources=_dedup_text(degraded_sources),
            errors=errors,
        )


class AkshareFinancialIndicatorProvider:
    """
    AKShare financial analysis indicator provider.
    """

    name = "akshare_indicator"

    def __init__(self, provider_version: str = "") -> None:
        self.provider_version = provider_version or "akshare:stock_financial_analysis_indicator"

    def fetch(self, request: FinancialFetchRequest, output: Callable = print) -> FinancialFetchResult:
        try:
            akshare = import_module("akshare")
        except ModuleNotFoundError as exc:
            return FinancialFetchResult(
                degraded_sources=[self.name],
                errors={self.name: str(exc)},
            )

        indicators: list[FinancialIndicatorSnapshot] = []
        degraded_sources: list[str] = []
        errors: dict[str, str] = {}
        for vt_symbol in request.vt_symbols:
            try:
                frame = _fetch_indicator_frame(akshare, vt_symbol)
            except Exception as exc:
                degraded_sources.append(self.name)
                errors[f"{self.name}:{vt_symbol}"] = str(exc)
                continue
            indicators.extend(
                _frame_to_indicators(
                    frame=frame,
                    vt_symbol=vt_symbol,
                    provider_name=self.name,
                    provider_version=self.provider_version,
                    max_periods=request.max_periods_per_symbol,
                )
            )

        return FinancialFetchResult(
            indicators=indicators,
            degraded_sources=_dedup_text(degraded_sources),
            errors=errors,
        )


class CninfoReportProvider:
    """
    CNINFO official financial report document provider.
    """

    name = "cninfo_report"
    endpoint = "https://www.cninfo.com.cn/new/hisAnnouncement/query"

    def __init__(
        self,
        http_client: Callable[..., Any] | None = None,
        provider_version: str = "",
        timeout_seconds: int = 30,
    ) -> None:
        self.http_client = http_client or _json_http_request
        self.provider_version = provider_version or "cninfo:hisAnnouncement"
        self.timeout_seconds = timeout_seconds

    def fetch(self, request: FinancialFetchRequest, output: Callable = print) -> FinancialFetchResult:
        documents: list[FinancialReportDocument] = []
        degraded_sources: list[str] = []
        errors: dict[str, str] = {}
        seen_ids: set[str] = set()

        for vt_symbol in request.vt_symbols:
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

            for row in _announcement_rows(payload):
                row_vt_symbol = _vt_symbol_from_payload(row) or vt_symbol
                if row_vt_symbol != vt_symbol:
                    continue
                document = document_from_announcement_row(
                    row=row,
                    vt_symbol=vt_symbol,
                    provider_name=self.name,
                    source="cninfo",
                    provider_version=self.provider_version,
                )
                if document is None or not _is_financial_report_title(document.title):
                    continue
                if not _document_in_window(document, request.start, request.end):
                    continue
                if document.document_id in seen_ids:
                    continue
                seen_ids.add(document.document_id)
                documents.append(document)
                if len(documents) >= request.max_periods_per_symbol * len(request.vt_symbols):
                    break

        return FinancialFetchResult(
            documents=documents,
            degraded_sources=_dedup_text(degraded_sources),
            errors=errors,
        )


class ExchangeReportProvider:
    """
    Official exchange report document provider.

    The first implementation uses the SSE disclosure endpoint. SZSE/BSE can be
    added behind the same provider name without changing TradingAgents callers.
    """

    name = "exchange_report"
    endpoint = "https://query.sse.com.cn/security/stock/queryCompanyBulletinNew.do"

    def __init__(
        self,
        http_client: Callable[..., Any] | None = None,
        provider_version: str = "",
        timeout_seconds: int = 30,
    ) -> None:
        self.http_client = http_client or _json_http_request
        self.provider_version = provider_version or "sse:queryCompanyBulletinNew"
        self.timeout_seconds = timeout_seconds

    def fetch(self, request: FinancialFetchRequest, output: Callable = print) -> FinancialFetchResult:
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
            return FinancialFetchResult(degraded_sources=[self.name], errors={self.name: str(exc)})

        documents: list[FinancialReportDocument] = []
        seen_ids: set[str] = set()
        requested_symbols = set(request.vt_symbols)
        for row in _announcement_rows(payload):
            vt_symbol = _vt_symbol_from_payload(row)
            if requested_symbols and vt_symbol not in requested_symbols:
                continue
            document = document_from_announcement_row(
                row=row,
                vt_symbol=vt_symbol,
                provider_name=self.name,
                source=_source_from_vt_symbol(vt_symbol),
                provider_version=self.provider_version,
            )
            if document is None or not _is_financial_report_title(document.title):
                continue
            if not _document_in_window(document, request.start, request.end):
                continue
            if document.document_id in seen_ids:
                continue
            seen_ids.add(document.document_id)
            documents.append(document)
            if len(documents) >= request.max_periods_per_symbol * max(1, len(request.vt_symbols)):
                break

        return FinancialFetchResult(documents=documents)


def _frame_to_statements(
    *,
    frame: Any,
    vt_symbol: str,
    statement_type: str,
    provider_name: str,
    provider_version: str,
    max_periods: int,
) -> list[FinancialStatementSnapshot]:
    rows = _dataframe_rows(frame)
    snapshots: list[FinancialStatementSnapshot] = []
    for row in rows[:max_periods]:
        report_period = _report_period(row)
        announcement_date = _announcement_date(row, report_period)
        snapshots.append(
            FinancialStatementSnapshot(
                vt_symbol=vt_symbol,
                report_period=report_period,
                statement_type=statement_type,
                report_type=_report_type(report_period),
                announcement_date=announcement_date,
                provider_name=provider_name,
                provider_version=provider_version,
                payload={"raw_fields": _clean_row(row)},
                quality_status="primary",
            )
        )
    return snapshots


def _frame_to_indicators(
    *,
    frame: Any,
    vt_symbol: str,
    provider_name: str,
    provider_version: str,
    max_periods: int,
) -> list[FinancialIndicatorSnapshot]:
    rows = _dataframe_rows(frame)
    snapshots: list[FinancialIndicatorSnapshot] = []
    for row in rows[:max_periods]:
        report_period = _report_period(row)
        announcement_date = _announcement_date(row, report_period)
        snapshots.append(
            FinancialIndicatorSnapshot(
                vt_symbol=vt_symbol,
                report_period=report_period,
                announcement_date=announcement_date,
                provider_name=provider_name,
                provider_version=provider_version,
                payload={"raw_fields": _clean_row(row)},
                quality_status="primary",
            )
        )
    return snapshots


def document_from_announcement_row(
    row: Mapping[str, Any],
    vt_symbol: str,
    provider_name: str,
    source: str,
    provider_version: str = "",
) -> FinancialReportDocument | None:
    """
    Convert an official report announcement row into metadata.
    """
    title = str(_first_value(row, ("title", "公告标题", "announcementTitle", "TITLE")) or "")
    if not title:
        return None
    report_period = _report_period(row)
    announcement_date = _announcement_date(row, report_period)
    raw_url = str(_first_value(row, ("url", "链接", "adjunctUrl", "announcementUrl", "URL")) or "")
    pdf_url = str(_first_value(row, ("pdf_url", "PDF链接", "adjunctUrl", "announcementUrl", "URL")) or "")
    url = _normalize_document_url(raw_url, source)
    pdf_url = _normalize_document_url(pdf_url or raw_url, source)
    return FinancialReportDocument(
        document_id=build_document_id(vt_symbol, report_period, title, source),
        vt_symbol=vt_symbol,
        report_period=report_period,
        report_type=_report_type_from_title(title, report_period),
        announcement_date=announcement_date,
        title=title,
        source=source,
        provider_name=provider_name,
        url=url,
        pdf_url=pdf_url,
        provider_version=provider_version,
        raw_payload=dict(row),
    )


def _call_first_endpoint(akshare: Any, endpoint_names: Sequence[str], symbol: str) -> Any:
    for endpoint_name in endpoint_names:
        endpoint = getattr(akshare, endpoint_name, None)
        if callable(endpoint):
            return endpoint(symbol=symbol)
    raise AttributeError(",".join(endpoint_names))


def _fetch_indicator_frame(akshare: Any, vt_symbol: str) -> Any:
    endpoint = getattr(akshare, "stock_financial_analysis_indicator", None)
    if callable(endpoint):
        frame = endpoint(symbol=_plain_symbol(vt_symbol))
        if not _empty_frame(frame):
            return frame

    endpoint = getattr(akshare, "stock_financial_analysis_indicator_em", None)
    if callable(endpoint):
        frame = endpoint(symbol=_akshare_em_symbol(vt_symbol), indicator="按报告期")
        if not _empty_frame(frame):
            return frame

    raise AttributeError("stock_financial_analysis_indicator,stock_financial_analysis_indicator_em")


def _dataframe_rows(frame: Any) -> list[dict[str, Any]]:
    if isinstance(frame, pd.DataFrame):
        rows = frame.to_dict(orient="records")
    elif isinstance(frame, Sequence) and not isinstance(frame, (str, bytes, bytearray)):
        rows = list(frame)
    else:
        rows = []
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def _empty_frame(frame: Any) -> bool:
    if isinstance(frame, pd.DataFrame):
        return frame.empty
    if isinstance(frame, Sequence) and not isinstance(frame, (str, bytes, bytearray)):
        return len(frame) == 0
    return True


def _report_period(row: Mapping[str, Any]) -> datetime:
    value = _first_value(
        row,
        (
            "报告日期",
            "报告日",
            "报告期",
            "日期",
            "REPORT_DATE",
            "report_date",
            "report_period",
        ),
    )
    if parsed := _parse_datetime(value):
        return parsed
    title = str(_first_value(row, ("title", "公告标题", "announcementTitle", "TITLE")) or "")
    return _infer_report_period_from_title(title) or datetime(1970, 1, 1)


def _announcement_date(row: Mapping[str, Any], fallback: datetime) -> datetime:
    value = _first_value(
        row,
        (
            "公告日期",
            "披露日期",
            "ANNOUNCE_DATE",
            "NOTICE_DATE",
            "UPDATE_DATE",
            "announcement_date",
            "announcementTime",
            "publishTime",
            "SSEDATE",
        ),
    )
    return _parse_datetime(value) or fallback


def _first_value(row: Mapping[str, Any], names: Sequence[str]) -> Any:
    for name in names:
        if name in row and row[name] not in {None, ""}:
            return row[name]
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, int | float):
        return _parse_epoch_datetime(float(value))
    text = str(value).strip()
    if match := re.fullmatch(r"(19|20)\d{6}", text):
        try:
            return datetime.strptime(match.group(0), "%Y%m%d")
        except ValueError:
            return None
    if text.isdigit():
        return _parse_epoch_datetime(float(text))
    try:
        return pd.to_datetime(value).to_pydatetime().replace(tzinfo=None)
    except Exception:
        return None


def _parse_epoch_datetime(value: float) -> datetime | None:
    if value <= 0:
        return None
    seconds = value / 1000 if value >= 10_000_000_000 else value
    try:
        return datetime.fromtimestamp(seconds, tz=ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
    except (OverflowError, OSError, ValueError):
        return None


def _report_type(report_period: datetime) -> str:
    month_day = (report_period.month, report_period.day)
    if month_day == (12, 31):
        return "annual"
    if month_day == (6, 30):
        return "half_year"
    if month_day == (3, 31):
        return "q1"
    if month_day == (9, 30):
        return "q3"
    return "quarterly"


def _report_type_from_title(title: str, report_period: datetime) -> str:
    if "年度" in title or "年报" in title:
        return "annual"
    if "半年度" in title or "半年报" in title:
        return "half_year"
    if "一季度" in title:
        return "q1"
    if "三季度" in title:
        return "q3"
    return _report_type(report_period)


def _infer_report_period_from_title(title: str) -> datetime | None:
    match = re.search(r"(20\d{2})\s*年", title)
    if not match:
        return None
    year = int(match.group(1))
    text = title.replace(" ", "")
    if "一季度" in text or "第一季度" in text:
        return datetime(year, 3, 31)
    if "半年度" in text or "半年报" in text:
        return datetime(year, 6, 30)
    if "三季度" in text or "第三季度" in text:
        return datetime(year, 9, 30)
    if "年度" in text or "年报" in text:
        return datetime(year, 12, 31)
    return None


def _is_financial_report_title(title: str) -> bool:
    text = title.replace(" ", "")
    if not text:
        return False
    positive_keywords = (
        "年度报告",
        "年报",
        "半年度报告",
        "半年报",
        "季度报告",
        "一季度报告",
        "三季度报告",
        "财务报告",
    )
    negative_keywords = (
        "摘要更正",
        "取消",
        "董事会决议",
        "监事会决议",
        "审计报告",
        "社会责任报告",
        "环境、社会及治理",
        "募集资金",
    )
    return any(keyword in text for keyword in positive_keywords) and not any(
        keyword in text for keyword in negative_keywords
    )


def _document_in_window(
    document: FinancialReportDocument,
    start: datetime,
    end: datetime,
) -> bool:
    return start <= document.announcement_date <= end or start <= document.report_period <= end


def _announcement_rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [dict(row) for row in value if isinstance(row, Mapping)]
    if not isinstance(value, Mapping):
        return []

    rows: list[dict[str, Any]] = []
    for key in ("announcements", "result", "data", "list"):
        child = value.get(key)
        if isinstance(child, list):
            rows.extend(dict(row) for row in child if isinstance(row, Mapping))

    classified = value.get("classifiedAnnouncements")
    if isinstance(classified, list):
        for group in classified:
            if isinstance(group, Mapping):
                rows.extend(_announcement_rows(group.get("announcements", [])))
            elif isinstance(group, list):
                rows.extend(dict(row) for row in group if isinstance(row, Mapping))
    return rows


def _cninfo_query_params(request: FinancialFetchRequest, vt_symbol: str) -> dict[str, Any]:
    return {
        "stock": "",
        "searchkey": _plain_symbol(vt_symbol),
        "category": "category_ndbg_szsh;category_bndbg_szsh;category_yjdbg_szsh",
        "pageNum": 1,
        "pageSize": request.max_periods_per_symbol,
        "column": "szse",
        "tabName": "fulltext",
        "plate": "",
        "seDate": f"{request.start.date()}~{request.end.date()}",
        "beginDate": request.start.date().isoformat(),
        "endDate": request.end.date().isoformat(),
    }


def _official_query_params(request: FinancialFetchRequest) -> dict[str, Any]:
    symbols = ",".join(_plain_symbol(symbol) for symbol in request.vt_symbols)
    return {
        "stock": symbols,
        "searchkey": "",
        "category": "",
        "pageNum": 1,
        "pageSize": request.max_periods_per_symbol * max(1, len(request.vt_symbols)),
        "column": "sse",
        "tabName": "fulltext",
        "plate": "",
        "seDate": f"{request.start.date()}~{request.end.date()}",
        "beginDate": request.start.date().isoformat(),
        "endDate": request.end.date().isoformat(),
    }


def _json_http_request(
    url: str,
    method: str = "GET",
    params: dict[str, Any] | None = None,
    timeout: int = 30,
    headers: dict[str, str] | None = None,
) -> Any:
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


def _vt_symbol_from_payload(row: Mapping[str, Any]) -> str:
    vt_symbol = str(_first_value(row, ("vt_symbol",)) or "")
    if "." in vt_symbol:
        return _normalize_vt_symbol(vt_symbol)
    code = str(
        _first_value(
            row,
            ("secCode", "securityCode", "SECURITY_CODE", "symbol", "code", "证券代码"),
        )
        or ""
    ).strip()
    if not code:
        return ""
    return f"{code}.{_exchange_from_symbol(code)}"


def _normalize_vt_symbol(vt_symbol: str) -> str:
    text = vt_symbol.strip().upper()
    if text.endswith(".SH"):
        return text[:-3] + ".SSE"
    if text.endswith(".SZ"):
        return text[:-3] + ".SZSE"
    if text.endswith(".BJ"):
        return text[:-3] + ".BSE"
    return text


def _exchange_from_symbol(symbol: str) -> str:
    text = symbol.strip()
    if text.startswith(("6", "9")):
        return "SSE"
    if text.startswith(("8", "4")):
        return "BSE"
    return "SZSE"


def _source_from_vt_symbol(vt_symbol: str) -> str:
    exchange = vt_symbol.split(".", 1)[1].upper() if "." in vt_symbol else ""
    if exchange == "SSE":
        return "sse"
    if exchange == "SZSE":
        return "szse"
    if exchange == "BSE":
        return "bse"
    return "exchange"


def _normalize_document_url(url: str, source: str) -> str:
    if not url:
        return ""
    if url.startswith(("http://", "https://")):
        return url
    if source == "cninfo":
        return f"https://static.cninfo.com.cn/{url.lstrip('/')}"
    if source == "sse":
        return f"https://www.sse.com.cn/{url.lstrip('/')}"
    return url


def _clean_row(row: Mapping[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in row.items():
        if value is None:
            continue
        if isinstance(value, float) and pd.isna(value):
            continue
        cleaned[str(key)] = _clean_value(value)
    return cleaned


def _clean_value(value: Any) -> Any:
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime().date().isoformat()
    return value


def _plain_symbol(vt_symbol: str) -> str:
    return vt_symbol.split(".", 1)[0]


def _akshare_prefixed_symbol(vt_symbol: str) -> str:
    symbol = _plain_symbol(vt_symbol)
    exchange = vt_symbol.split(".", 1)[1].upper() if "." in vt_symbol else ""
    if exchange == "SSE":
        return f"sh{symbol}"
    if exchange == "SZSE":
        return f"sz{symbol}"
    return symbol


def _akshare_market_symbol(vt_symbol: str) -> str:
    symbol = _plain_symbol(vt_symbol)
    exchange = vt_symbol.split(".", 1)[1].upper() if "." in vt_symbol else ""
    if exchange == "SSE":
        return f"SH{symbol}"
    if exchange == "SZSE":
        return f"SZ{symbol}"
    return symbol


def _akshare_em_symbol(vt_symbol: str) -> str:
    symbol = _plain_symbol(vt_symbol)
    exchange = vt_symbol.split(".", 1)[1].upper() if "." in vt_symbol else ""
    if exchange == "SSE":
        return f"{symbol}.SH"
    if exchange == "SZSE":
        return f"{symbol}.SZ"
    return vt_symbol


def _dedup_text(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result
