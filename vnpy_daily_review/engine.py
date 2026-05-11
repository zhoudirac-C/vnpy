from dataclasses import dataclass, field
from datetime import date
from typing import Any

from vnpy.event import EventEngine
from vnpy.trader.engine import BaseEngine, MainEngine


APP_NAME: str = "DailyMarketReview"


@dataclass(frozen=True)
class DailyMarketReviewReportResult:
    """
    UI-friendly daily review report payload.
    """

    status: str
    trade_date: date
    title: str = ""
    markdown: str = ""
    watch_items: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    audit: list[dict[str, Any]] = field(default_factory=list)
    message: str = ""


@dataclass(frozen=True)
class DailyMarketReviewValidationResult:
    """
    UI-friendly next-day validation payload.
    """

    status: str
    trade_date: date
    validation_date: date
    results: list[dict[str, Any]] = field(default_factory=list)
    message: str = ""


class DailyMarketReviewEngine(BaseEngine):
    """
    Runtime boundary for daily market review.
    """

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine) -> None:
        """"""
        super().__init__(main_engine, event_engine, APP_NAME)
        self.review_service: Any | None = None

    def set_review_service(self, service: Any) -> None:
        """
        Attach a full daily-review service after the pipeline is wired.
        """
        self.review_service = service

    def load_latest_report(self) -> DailyMarketReviewReportResult:
        """
        Load the latest report, returning a safe empty boundary when unwired.
        """
        if self.review_service and hasattr(self.review_service, "load_latest_report"):
            return self.review_service.load_latest_report()

        return self._not_configured_report(date.today())

    def list_reports(self, limit: int = 50) -> list[DailyMarketReviewReportResult]:
        """
        List historical reports for the UI.
        """
        if self.review_service and hasattr(self.review_service, "list_reports"):
            return self.review_service.list_reports(limit=limit)
        return []

    def run_preview(
        self,
        trade_date: date,
        run_llm: bool = False,
    ) -> DailyMarketReviewReportResult:
        """
        Run one report preview.
        """
        if self.review_service and hasattr(self.review_service, "run_preview"):
            return self.review_service.run_preview(trade_date=trade_date, run_llm=run_llm)

        return self._not_configured_report(trade_date)

    def validate_next_day(
        self,
        trade_date: date,
        validation_date: date,
    ) -> DailyMarketReviewValidationResult:
        """
        Validate watch-plan items against the next trading day.
        """
        if self.review_service and hasattr(self.review_service, "validate_next_day"):
            return self.review_service.validate_next_day(
                trade_date=trade_date,
                validation_date=validation_date,
            )

        return DailyMarketReviewValidationResult(
            status="not_configured",
            trade_date=trade_date,
            validation_date=validation_date,
            message="每日市场复盘验证服务未接入；当前只提供 vn.py UI 入口和安全边界。",
        )

    def _not_configured_report(self, trade_date: date) -> DailyMarketReviewReportResult:
        """
        Build a stable not-configured report for UI display.
        """
        return DailyMarketReviewReportResult(
            status="not_configured",
            trade_date=trade_date,
            title="每日市场复盘服务未接入",
            markdown=(
                "## 每日市场复盘服务未接入\n\n"
                "当前版本已经提供独立 vn.py UI 入口和 Engine 边界，"
                "后续需要继续接入全市场行情、板块、涨停生态、龙虎榜、"
                "分时异动、新闻公告、财报证据、AI 编排和 PostgreSQL 报告落库。"
            ),
            message="每日市场复盘流水线未接入。",
        )
