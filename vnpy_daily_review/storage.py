"""
Persistence for daily market review reports.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, Protocol

from .engine import DailyMarketReviewReportResult
from .models import build_daily_review_extension_models


class DailyReviewRepository(Protocol):
    """
    Repository protocol used by DailyReviewService.
    """

    def save_report_result(self, result: DailyMarketReviewReportResult) -> None:
        """
        Save one report result.
        """

    def load_latest_report(self) -> DailyMarketReviewReportResult | None:
        """
        Load the newest report result.
        """

    def list_reports(self, limit: int = 50) -> list[DailyMarketReviewReportResult]:
        """
        List newest report results.
        """


class PeeweeDailyReviewRepository:
    """
    PostgreSQL/Peewee implementation reusing vn.py database.* settings.
    """

    def __init__(self, database: Any) -> None:
        self.database = database
        models = build_daily_review_extension_models(database)
        self.report_model = models[0]
        self.evidence_model = models[1]
        self.plan_model = models[2]
        self.plan_item_model = models[3]
        self.audit_model = models[4]

    def create_schema(self) -> None:
        """
        Create tables idempotently.
        """
        self.database.connect(reuse_if_open=True)
        self.database.create_tables(
            [
                self.report_model,
                self.evidence_model,
                self.plan_model,
                self.plan_item_model,
                self.audit_model,
            ],
            safe=True,
        )

    def save_report_result(self, result: DailyMarketReviewReportResult) -> None:
        """
        Save report, evidence, watch plan, and audit payloads.
        """
        self.database.connect(reuse_if_open=True)
        report_id = _report_id(result)
        created_at = datetime.now(UTC)

        self.report_model.replace(
            report_id=report_id,
            trade_date=result.trade_date,
            status=result.status,
            title=result.title,
            markdown=result.markdown,
            structured={
                "watch_items": result.watch_items,
                "message": result.message,
            },
            evidence_ids=[
                str(item.get("evidence_id", ""))
                for item in result.evidence
                if item.get("evidence_id")
            ],
            model_name=str(result.audit[0].get("mode", "deterministic")) if result.audit else "",
            created_at=created_at,
        ).execute()

        for evidence in result.evidence:
            evidence_id = str(evidence.get("evidence_id", ""))
            if not evidence_id:
                continue
            self.evidence_model.replace(
                evidence_id=evidence_id,
                trade_date=result.trade_date,
                source=str(evidence.get("source", "")),
                source_type=str(evidence.get("source_type", "")),
                content=str(evidence.get("content", "")),
                trust_score=str(evidence.get("trust_score", "")),
                data_time=_parse_datetime(evidence.get("data_time")),
                content_hash=str(evidence.get("content_hash", "")),
                metadata=dict(evidence.get("metadata", {}) or {}),
                created_at=created_at,
            ).execute()

        plan_id = f"PLAN-{result.trade_date:%Y%m%d}-{report_id[:10]}"
        summary = _watch_summary(result.watch_items)
        self.plan_model.replace(
            plan_id=plan_id,
            trade_date=result.trade_date,
            source_report_id=report_id,
            status="draft",
            summary=summary,
            created_at=created_at,
        ).execute()
        self.plan_item_model.delete().where(self.plan_item_model.plan_id == plan_id).execute()
        for index, item in enumerate(result.watch_items, start=1):
            self.plan_item_model.insert(
                item_id=f"{plan_id}-{index:03d}",
                plan_id=plan_id,
                symbol=str(item.get("symbol", "")),
                name=str(item.get("name", "")),
                role=str(item.get("role", "")),
                watch_action=str(item.get("watch_action", "")),
                entry_condition=str(item.get("entry_condition", "")),
                avoid_condition=str(item.get("avoid_condition", "")),
                position_rule=str(item.get("position_rule", "")),
                evidence_ids=list(item.get("evidence_ids", []) or []),
                created_at=created_at,
            ).execute()

        for index, audit in enumerate(result.audit, start=1):
            self.audit_model.replace(
                audit_id=_audit_id(report_id, index, audit),
                report_id=report_id,
                trade_date=result.trade_date,
                stage=str(audit.get("stage", audit.get("mode", "daily_review"))),
                provider=str(audit.get("provider", "vnpy_daily_review")),
                model_name=str(audit.get("model_name", audit.get("mode", "deterministic"))),
                status=str(audit.get("status", result.status)),
                payload=dict(audit),
                created_at=created_at,
            ).execute()

    def load_latest_report(self) -> DailyMarketReviewReportResult | None:
        """
        Load the latest report.
        """
        self.database.connect(reuse_if_open=True)
        row = (
            self.report_model.select()
            .order_by(self.report_model.created_at.desc())
            .first()
        )
        if row is None:
            return None
        return self._row_to_result(row)

    def list_reports(self, limit: int = 50) -> list[DailyMarketReviewReportResult]:
        """
        List newest reports.
        """
        self.database.connect(reuse_if_open=True)
        rows = (
            self.report_model.select()
            .order_by(self.report_model.created_at.desc())
            .limit(max(1, min(int(limit), 500)))
        )
        return [self._row_to_result(row) for row in rows]

    def _row_to_result(self, row: Any) -> DailyMarketReviewReportResult:
        structured = dict(row.structured or {})
        report_id = str(row.report_id)
        plan = (
            self.plan_model.select()
            .where(self.plan_model.source_report_id == report_id)
            .order_by(self.plan_model.created_at.desc())
            .first()
        )
        watch_items: list[dict[str, Any]] = []
        if plan is not None:
            item_rows = (
                self.plan_item_model.select()
                .where(self.plan_item_model.plan_id == plan.plan_id)
                .order_by(self.plan_item_model.item_id)
            )
            watch_items = [_watch_item_from_row(item) for item in item_rows]
        if not watch_items:
            watch_items = list(structured.get("watch_items", []) or [])

        evidence_rows = (
            self.evidence_model.select()
            .where(self.evidence_model.evidence_id.in_(list(row.evidence_ids or [])))
            .order_by(self.evidence_model.evidence_id)
        )
        audit_rows = (
            self.audit_model.select()
            .where(self.audit_model.report_id == report_id)
            .order_by(self.audit_model.created_at)
        )
        return DailyMarketReviewReportResult(
            status=str(row.status),
            trade_date=row.trade_date,
            title=str(row.title),
            markdown=str(row.markdown),
            watch_items=watch_items,
            evidence=[_evidence_from_row(evidence) for evidence in evidence_rows],
            audit=[dict(audit.payload or {}) for audit in audit_rows],
            message=str(structured.get("message", "")),
        )


class InMemoryDailyReviewRepository:
    """
    Small repository used when PostgreSQL is not configured.
    """

    def __init__(self) -> None:
        self._items: list[DailyMarketReviewReportResult] = []

    def save_report_result(self, result: DailyMarketReviewReportResult) -> None:
        self._items.append(result)

    def load_latest_report(self) -> DailyMarketReviewReportResult | None:
        return self._items[-1] if self._items else None

    def list_reports(self, limit: int = 50) -> list[DailyMarketReviewReportResult]:
        return list(reversed(self._items[-limit:]))


def with_storage_warning(
    result: DailyMarketReviewReportResult,
    message: str,
) -> DailyMarketReviewReportResult:
    """
    Return a copy of result with a storage warning audit entry.
    """
    return replace(
        result,
        audit=[
            *result.audit,
            {
                "mode": "storage",
                "status": "failed",
                "error_message": message,
            },
        ],
    )


def _report_id(result: DailyMarketReviewReportResult) -> str:
    raw = "|".join(
        [
            result.trade_date.isoformat(),
            result.title,
            result.status,
            result.markdown,
        ]
    )
    return "DRR-" + sha256(raw.encode("utf-8")).hexdigest()[:32]


def _audit_id(report_id: str, index: int, audit: dict[str, Any]) -> str:
    raw = f"{report_id}|{index}|{audit}"
    return "DRA-" + sha256(raw.encode("utf-8")).hexdigest()[:32]


def _watch_summary(items: list[dict[str, Any]]) -> str:
    if not items:
        return "暂无明日观察标的"
    symbols = ", ".join(str(item.get("symbol", "")) for item in items[:10])
    return f"明日观察：{symbols}"


def _watch_item_from_row(row: Any) -> dict[str, Any]:
    return {
        "symbol": row.symbol,
        "name": row.name,
        "role": row.role,
        "watch_action": row.watch_action,
        "entry_condition": row.entry_condition,
        "avoid_condition": row.avoid_condition,
        "position_rule": row.position_rule,
        "evidence_ids": list(row.evidence_ids or []),
    }


def _evidence_from_row(row: Any) -> dict[str, Any]:
    return {
        "evidence_id": row.evidence_id,
        "source": row.source,
        "source_type": row.source_type,
        "content": row.content,
        "trust_score": row.trust_score,
        "data_time": row.data_time.isoformat(),
        "content_hash": row.content_hash,
        "metadata": dict(row.metadata or {}),
    }


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if value:
        try:
            parsed = datetime.fromisoformat(str(value))
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
            return parsed
        except ValueError:
            pass
    return datetime.now(UTC)
