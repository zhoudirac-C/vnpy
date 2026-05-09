from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from typing import Any, Protocol


FINANCIAL_SCHEMA: str = """
CREATE TABLE IF NOT EXISTS financial_statement_snapshot (
    vt_symbol TEXT NOT NULL,
    report_period TIMESTAMPTZ NOT NULL,
    statement_type TEXT NOT NULL,
    report_type TEXT NOT NULL,
    announcement_date TIMESTAMPTZ NOT NULL,
    provider_name TEXT NOT NULL,
    provider_version TEXT,
    currency TEXT NOT NULL DEFAULT 'CNY',
    unit TEXT NOT NULL DEFAULT 'yuan',
    payload JSONB NOT NULL,
    source_document_id TEXT,
    quality_status TEXT,
    quality_report JSONB,
    pulled_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (vt_symbol, report_period, statement_type, provider_name)
);

CREATE TABLE IF NOT EXISTS financial_indicator_snapshot (
    vt_symbol TEXT NOT NULL,
    report_period TIMESTAMPTZ NOT NULL,
    announcement_date TIMESTAMPTZ NOT NULL,
    provider_name TEXT NOT NULL,
    provider_version TEXT,
    payload JSONB NOT NULL,
    quality_status TEXT,
    quality_report JSONB,
    pulled_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (vt_symbol, report_period, provider_name)
);

CREATE TABLE IF NOT EXISTS financial_report_document (
    document_id TEXT PRIMARY KEY,
    vt_symbol TEXT NOT NULL,
    report_period TIMESTAMPTZ NOT NULL,
    report_type TEXT NOT NULL,
    announcement_date TIMESTAMPTZ NOT NULL,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    provider_name TEXT NOT NULL,
    url TEXT,
    pdf_url TEXT,
    file_hash TEXT,
    provider_version TEXT,
    raw_payload JSONB,
    pulled_at TIMESTAMPTZ DEFAULT now()
);
"""


UPSERT_FINANCIAL_STATEMENT_SQL: str = """
INSERT INTO financial_statement_snapshot (
    vt_symbol,
    report_period,
    statement_type,
    report_type,
    announcement_date,
    provider_name,
    provider_version,
    currency,
    unit,
    payload,
    source_document_id,
    quality_status,
    quality_report
) VALUES (
    %(vt_symbol)s,
    %(report_period)s,
    %(statement_type)s,
    %(report_type)s,
    %(announcement_date)s,
    %(provider_name)s,
    %(provider_version)s,
    %(currency)s,
    %(unit)s,
    %(payload)s,
    %(source_document_id)s,
    %(quality_status)s,
    %(quality_report)s
)
ON CONFLICT (vt_symbol, report_period, statement_type, provider_name)
DO UPDATE SET
    report_type = EXCLUDED.report_type,
    announcement_date = EXCLUDED.announcement_date,
    provider_version = EXCLUDED.provider_version,
    currency = EXCLUDED.currency,
    unit = EXCLUDED.unit,
    payload = EXCLUDED.payload,
    source_document_id = EXCLUDED.source_document_id,
    quality_status = EXCLUDED.quality_status,
    quality_report = EXCLUDED.quality_report,
    pulled_at = now();
"""


UPSERT_FINANCIAL_INDICATOR_SQL: str = """
INSERT INTO financial_indicator_snapshot (
    vt_symbol,
    report_period,
    announcement_date,
    provider_name,
    provider_version,
    payload,
    quality_status,
    quality_report
) VALUES (
    %(vt_symbol)s,
    %(report_period)s,
    %(announcement_date)s,
    %(provider_name)s,
    %(provider_version)s,
    %(payload)s,
    %(quality_status)s,
    %(quality_report)s
)
ON CONFLICT (vt_symbol, report_period, provider_name)
DO UPDATE SET
    announcement_date = EXCLUDED.announcement_date,
    provider_version = EXCLUDED.provider_version,
    payload = EXCLUDED.payload,
    quality_status = EXCLUDED.quality_status,
    quality_report = EXCLUDED.quality_report,
    pulled_at = now();
"""


UPSERT_FINANCIAL_REPORT_DOCUMENT_SQL: str = """
INSERT INTO financial_report_document (
    document_id,
    vt_symbol,
    report_period,
    report_type,
    announcement_date,
    title,
    source,
    provider_name,
    url,
    pdf_url,
    file_hash,
    provider_version,
    raw_payload
) VALUES (
    %(document_id)s,
    %(vt_symbol)s,
    %(report_period)s,
    %(report_type)s,
    %(announcement_date)s,
    %(title)s,
    %(source)s,
    %(provider_name)s,
    %(url)s,
    %(pdf_url)s,
    %(file_hash)s,
    %(provider_version)s,
    %(raw_payload)s
)
ON CONFLICT (document_id)
DO UPDATE SET
    vt_symbol = EXCLUDED.vt_symbol,
    report_period = EXCLUDED.report_period,
    report_type = EXCLUDED.report_type,
    announcement_date = EXCLUDED.announcement_date,
    title = EXCLUDED.title,
    source = EXCLUDED.source,
    provider_name = EXCLUDED.provider_name,
    url = EXCLUDED.url,
    pdf_url = EXCLUDED.pdf_url,
    file_hash = EXCLUDED.file_hash,
    provider_version = EXCLUDED.provider_version,
    raw_payload = EXCLUDED.raw_payload,
    pulled_at = now();
"""


SELECT_FINANCIAL_STATEMENTS_SQL: str = """
SELECT
    vt_symbol,
    report_period,
    statement_type,
    report_type,
    announcement_date,
    provider_name,
    provider_version,
    currency,
    unit,
    payload,
    source_document_id,
    quality_status,
    quality_report
FROM financial_statement_snapshot
WHERE vt_symbol = %(vt_symbol)s
  AND announcement_date <= %(as_of)s
ORDER BY report_period DESC, announcement_date DESC, pulled_at DESC
LIMIT %(limit)s;
"""

SELECT_FINANCIAL_INDICATORS_SQL: str = """
SELECT
    vt_symbol,
    report_period,
    announcement_date,
    provider_name,
    provider_version,
    payload,
    quality_status,
    quality_report
FROM financial_indicator_snapshot
WHERE vt_symbol = %(vt_symbol)s
  AND announcement_date <= %(as_of)s
ORDER BY report_period DESC, announcement_date DESC, pulled_at DESC
LIMIT %(limit)s;
"""


SELECT_FINANCIAL_DOCUMENTS_SQL: str = """
SELECT
    document_id,
    vt_symbol,
    report_period,
    report_type,
    announcement_date,
    title,
    source,
    provider_name,
    url,
    pdf_url,
    file_hash,
    provider_version,
    raw_payload
FROM financial_report_document
WHERE vt_symbol = %(vt_symbol)s
  AND announcement_date <= %(as_of)s
ORDER BY report_period DESC, announcement_date DESC, pulled_at DESC
LIMIT %(limit)s;
"""


class Cursor(Protocol):
    def execute(self, sql: str, params: dict[str, Any] | None = None) -> None:
        pass

    def fetchall(self) -> list[Mapping[str, Any]]:
        pass

    def close(self) -> None:
        pass


class Connection(Protocol):
    def cursor(self) -> Cursor:
        pass

    def commit(self) -> None:
        pass


@dataclass(frozen=True)
class FinancialStatementSnapshot:
    """
    One provider-traced structured financial statement.
    """

    vt_symbol: str
    report_period: datetime
    statement_type: str
    report_type: str
    announcement_date: datetime
    provider_name: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    provider_version: str = ""
    currency: str = "CNY"
    unit: str = "yuan"
    source_document_id: str = ""
    quality_status: str = "primary"
    quality_report: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FinancialIndicatorSnapshot:
    """
    Period-scoped financial indicators such as ROE and margins.
    """

    vt_symbol: str
    report_period: datetime
    announcement_date: datetime
    provider_name: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    provider_version: str = ""
    quality_status: str = "primary"
    quality_report: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FinancialReportDocument:
    """
    Official report/announcement document metadata.
    """

    document_id: str
    vt_symbol: str
    report_period: datetime
    report_type: str
    announcement_date: datetime
    title: str
    source: str
    provider_name: str
    url: str = ""
    pdf_url: str = ""
    file_hash: str = ""
    provider_version: str = ""
    raw_payload: Mapping[str, Any] = field(default_factory=dict)


class PostgresFinancialStorage:
    """
    PostgreSQL storage for structured financial reports.
    """

    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def create_schema(self) -> None:
        cursor = self.connection.cursor()
        try:
            cursor.execute(FINANCIAL_SCHEMA)
            self.connection.commit()
        finally:
            cursor.close()

    def save_statement_snapshot(self, snapshot: FinancialStatementSnapshot) -> None:
        cursor = self.connection.cursor()
        try:
            cursor.execute(UPSERT_FINANCIAL_STATEMENT_SQL, _statement_params(snapshot))
            self.connection.commit()
        finally:
            cursor.close()

    def save_indicator_snapshot(self, snapshot: FinancialIndicatorSnapshot) -> None:
        cursor = self.connection.cursor()
        try:
            cursor.execute(UPSERT_FINANCIAL_INDICATOR_SQL, _indicator_params(snapshot))
            self.connection.commit()
        finally:
            cursor.close()

    def save_report_document(self, document: FinancialReportDocument) -> None:
        cursor = self.connection.cursor()
        try:
            cursor.execute(UPSERT_FINANCIAL_REPORT_DOCUMENT_SQL, _document_params(document))
            self.connection.commit()
        finally:
            cursor.close()

    def load_financial_context(
        self,
        vt_symbol: str,
        as_of: datetime,
        max_periods: int = 4,
    ) -> dict[str, Any]:
        """
        Load latest announced statements for TradingAgents context.
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                SELECT_FINANCIAL_STATEMENTS_SQL,
                {
                    "vt_symbol": vt_symbol,
                    "as_of": as_of,
                    "limit": max(1, max_periods * 3),
                },
            )
            rows = cursor.fetchall()
            cursor.execute(
                SELECT_FINANCIAL_INDICATORS_SQL,
                {
                    "vt_symbol": vt_symbol,
                    "as_of": as_of,
                    "limit": max(1, max_periods),
                },
            )
            indicator_rows = cursor.fetchall()
            cursor.execute(
                SELECT_FINANCIAL_DOCUMENTS_SQL,
                {
                    "vt_symbol": vt_symbol,
                    "as_of": as_of,
                    "limit": max(1, max_periods),
                },
            )
            document_rows = cursor.fetchall()
        finally:
            cursor.close()

        statements: dict[str, dict[str, Any]] = {}
        for row in rows:
            snapshot = _statement_from_row(row)
            if snapshot.statement_type in statements:
                continue
            payload = dict(snapshot.payload)
            fields = payload.get("raw_fields", payload)
            statements[snapshot.statement_type] = {
                "report_period": snapshot.report_period.date().isoformat(),
                "announcement_date": snapshot.announcement_date.date().isoformat(),
                "provider_name": snapshot.provider_name,
                "quality_status": snapshot.quality_status,
                "fields": fields,
            }

        indicators: list[dict[str, Any]] = []
        for row in indicator_rows:
            indicator = _indicator_from_row(row)
            payload = dict(indicator.payload)
            fields = payload.get("raw_fields", payload)
            indicators.append(
                {
                    "report_period": indicator.report_period.date().isoformat(),
                    "announcement_date": indicator.announcement_date.date().isoformat(),
                    "provider_name": indicator.provider_name,
                    "quality_status": indicator.quality_status,
                    "fields": fields,
                }
            )

        documents: list[dict[str, Any]] = []
        for row in document_rows:
            document = _document_from_row(row)
            documents.append(
                {
                    "document_id": document.document_id,
                    "report_period": document.report_period.date().isoformat(),
                    "report_type": document.report_type,
                    "announcement_date": document.announcement_date.date().isoformat(),
                    "title": document.title,
                    "source": document.source,
                    "provider_name": document.provider_name,
                    "url": document.url,
                    "pdf_url": document.pdf_url,
                    "file_hash": document.file_hash,
                    "provider_version": document.provider_version,
                }
            )

        return {
            "statements": statements,
            "indicators": indicators,
            "documents": documents,
            "quality_status": _context_quality_status(statements, indicators, documents),
        }


def build_document_id(vt_symbol: str, report_period: datetime, title: str, source: str) -> str:
    """
    Build stable document id for official report metadata.
    """
    text = f"{vt_symbol}:{report_period.date().isoformat()}:{source}:{title}"
    return sha256(text.encode()).hexdigest()


def _statement_params(snapshot: FinancialStatementSnapshot) -> dict[str, Any]:
    return {
        "vt_symbol": snapshot.vt_symbol,
        "report_period": snapshot.report_period,
        "statement_type": snapshot.statement_type,
        "report_type": snapshot.report_type,
        "announcement_date": snapshot.announcement_date,
        "provider_name": snapshot.provider_name,
        "provider_version": snapshot.provider_version,
        "currency": snapshot.currency,
        "unit": snapshot.unit,
        "payload": _json(snapshot.payload),
        "source_document_id": snapshot.source_document_id,
        "quality_status": snapshot.quality_status,
        "quality_report": _json(snapshot.quality_report),
    }


def _indicator_params(snapshot: FinancialIndicatorSnapshot) -> dict[str, Any]:
    return {
        "vt_symbol": snapshot.vt_symbol,
        "report_period": snapshot.report_period,
        "announcement_date": snapshot.announcement_date,
        "provider_name": snapshot.provider_name,
        "provider_version": snapshot.provider_version,
        "payload": _json(snapshot.payload),
        "quality_status": snapshot.quality_status,
        "quality_report": _json(snapshot.quality_report),
    }


def _document_params(document: FinancialReportDocument) -> dict[str, Any]:
    return {
        "document_id": document.document_id,
        "vt_symbol": document.vt_symbol,
        "report_period": document.report_period,
        "report_type": document.report_type,
        "announcement_date": document.announcement_date,
        "title": document.title,
        "source": document.source,
        "provider_name": document.provider_name,
        "url": document.url,
        "pdf_url": document.pdf_url,
        "file_hash": document.file_hash,
        "provider_version": document.provider_version,
        "raw_payload": _json(document.raw_payload),
    }


def _statement_from_row(row: Mapping[str, Any]) -> FinancialStatementSnapshot:
    return FinancialStatementSnapshot(
        vt_symbol=str(row["vt_symbol"]),
        report_period=_as_datetime(row["report_period"]),
        statement_type=str(row["statement_type"]),
        report_type=str(row.get("report_type", "")),
        announcement_date=_as_datetime(row["announcement_date"]),
        provider_name=str(row["provider_name"]),
        provider_version=str(row.get("provider_version") or ""),
        currency=str(row.get("currency") or "CNY"),
        unit=str(row.get("unit") or "yuan"),
        payload=_mapping(row.get("payload")),
        source_document_id=str(row.get("source_document_id") or ""),
        quality_status=str(row.get("quality_status") or ""),
        quality_report=_mapping(row.get("quality_report")),
    )


def _indicator_from_row(row: Mapping[str, Any]) -> FinancialIndicatorSnapshot:
    return FinancialIndicatorSnapshot(
        vt_symbol=str(row["vt_symbol"]),
        report_period=_as_datetime(row["report_period"]),
        announcement_date=_as_datetime(row["announcement_date"]),
        provider_name=str(row["provider_name"]),
        provider_version=str(row.get("provider_version") or ""),
        payload=_mapping(row.get("payload")),
        quality_status=str(row.get("quality_status") or ""),
        quality_report=_mapping(row.get("quality_report")),
    )


def _document_from_row(row: Mapping[str, Any]) -> FinancialReportDocument:
    return FinancialReportDocument(
        document_id=str(row["document_id"]),
        vt_symbol=str(row["vt_symbol"]),
        report_period=_as_datetime(row["report_period"]),
        report_type=str(row.get("report_type") or ""),
        announcement_date=_as_datetime(row["announcement_date"]),
        title=str(row["title"]),
        source=str(row["source"]),
        provider_name=str(row["provider_name"]),
        url=str(row.get("url") or ""),
        pdf_url=str(row.get("pdf_url") or ""),
        file_hash=str(row.get("file_hash") or ""),
        provider_version=str(row.get("provider_version") or ""),
        raw_payload=_mapping(row.get("raw_payload")),
    )


def _context_quality_status(
    statements: Mapping[str, Any],
    indicators: list[Mapping[str, Any]],
    documents: list[Mapping[str, Any]],
) -> str:
    if not statements:
        return "missing"
    official_sources = {"cninfo", "sse", "szse", "bse", "exchange"}
    if indicators and any(document.get("source") in official_sources for document in documents):
        return "primary"
    return "degraded"


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str) and value:
        try:
            loaded = json.loads(value)
            if isinstance(loaded, Mapping):
                return dict(loaded)
        except json.JSONDecodeError:
            return {}
    return {}


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)


def _json(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, default=str)
