"""
vn.py service layer for daily market review.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Protocol

from .domain import (
    DailyEventCatalyst,
    DailyIntradayAnomaly,
    DailyLhbSnapshot,
    DailyLimitUpSnapshot,
    DailySectorSnapshot,
    DailyStockSnapshot,
)
from .engine import DailyMarketReviewReportResult, DailyMarketReviewValidationResult
from .evidence import EvidencePack, EvidencePackBuilder
from .signals import (
    LeaderScore,
    LeaderScoringEngine,
    LhbCapitalEngine,
    LimitUpEmotionEngine,
    MarketBreadthEngine,
    SectorRotationEngine,
)


@dataclass(frozen=True)
class DailyReviewDataBundle:
    """
    All inputs needed to build a daily review.
    """

    trade_date: date
    stocks: list[DailyStockSnapshot] = field(default_factory=list)
    sectors: list[DailySectorSnapshot] = field(default_factory=list)
    limit_ups: list[DailyLimitUpSnapshot] = field(default_factory=list)
    lhb: list[DailyLhbSnapshot] = field(default_factory=list)
    intraday_anomalies: list[DailyIntradayAnomaly] = field(default_factory=list)
    events: list[DailyEventCatalyst] = field(default_factory=list)
    provider_records: list[dict[str, Any]] = field(default_factory=list)
    quality_warnings: list[str] = field(default_factory=list)


class DailyReviewDataProvider(Protocol):
    """
    Data provider protocol for the review service.
    """

    def load_data_bundle(self, trade_date: date) -> DailyReviewDataBundle:
        """
        Load one trading day's review inputs.
        """


class DailyReviewService:
    """
    Daily market review pipeline running inside vn.py.
    """

    def __init__(self, data_provider: DailyReviewDataProvider) -> None:
        self._data_provider = data_provider
        self._last_result: DailyMarketReviewReportResult | None = None

    def load_latest_report(self) -> DailyMarketReviewReportResult:
        """
        Return the latest in-process report result.
        """
        if self._last_result is not None:
            return self._last_result
        return DailyMarketReviewReportResult(
            status="no_data",
            trade_date=date.today(),
            title="每日市场复盘尚未运行",
            markdown=(
                "## 每日市场复盘尚未运行\n\n"
                "请点击“运行预览”从 vn.py/AKShare provider 读取数据并生成报告。"
            ),
            message="no_latest_report",
        )

    def run_preview(
        self,
        trade_date: date,
        run_llm: bool = False,
    ) -> DailyMarketReviewReportResult:
        """
        Run one deterministic daily review preview.
        """
        bundle = self._data_provider.load_data_bundle(trade_date)
        if not bundle.stocks:
            result = _no_data_result(bundle)
            self._last_result = result
            return result

        market_signal = MarketBreadthEngine().calculate(bundle.stocks)
        sector_signals = SectorRotationEngine().calculate(
            sectors=bundle.sectors,
            stocks=bundle.stocks,
        )
        limit_signal = LimitUpEmotionEngine().calculate(bundle.limit_ups)
        lhb_signal = LhbCapitalEngine().calculate(bundle.lhb)
        leaders = LeaderScoringEngine().calculate(
            stock_snapshots=bundle.stocks,
            sector_signals=sector_signals,
            limit_up_snapshots=bundle.limit_ups,
            lhb_snapshots=bundle.lhb,
            intraday_anomalies=bundle.intraday_anomalies,
            event_catalysts=bundle.events,
        )[:20]
        pack = EvidencePackBuilder().build(
            trade_date=trade_date,
            market_signal=market_signal,
            sector_signals=sector_signals[:12],
            leader_candidates=leaders,
            news_catalysts=bundle.events,
            data_quality=bundle.quality_warnings,
        )
        markdown = DailyReviewMarkdownComposer().compose(
            pack=pack,
            leaders=leaders,
            limit_signal=limit_signal,
            lhb_net_buy_amount=lhb_signal.net_buy_amount,
            run_llm=run_llm,
        )
        result = DailyMarketReviewReportResult(
            status="completed",
            trade_date=trade_date,
            title=f"{trade_date.isoformat()} 每日市场复盘",
            markdown=markdown,
            watch_items=[_leader_to_watch_item(leader, pack) for leader in leaders[:10]],
            evidence=[item.to_llm_dict() for item in pack.evidence],
            audit=[
                {
                    "mode": "deterministic",
                    "run_llm_requested": run_llm,
                    "provider_records": bundle.provider_records,
                    "stock_count": len(bundle.stocks),
                    "sector_count": len(sector_signals),
                    "leader_count": len(leaders),
                    "data_quality": list(pack.data_quality),
                }
            ],
            message="completed",
        )
        self._last_result = result
        return result

    def validate_next_day(
        self,
        trade_date: date,
        validation_date: date,
    ) -> DailyMarketReviewValidationResult:
        """
        Validate the latest watch plan with another trading day's snapshots.
        """
        if self._last_result is None or self._last_result.trade_date != trade_date:
            return DailyMarketReviewValidationResult(
                status="no_plan",
                trade_date=trade_date,
                validation_date=validation_date,
                message="请先生成对应交易日的每日复盘和明日观察计划。",
            )

        bundle = self._data_provider.load_data_bundle(validation_date)
        by_symbol = {stock.symbol: stock for stock in bundle.stocks}
        results: list[dict[str, Any]] = []
        for item in self._last_result.watch_items:
            symbol = str(item.get("symbol", ""))
            stock = by_symbol.get(symbol)
            if stock is None:
                results.append(
                    {
                        "symbol": symbol,
                        "status": "missed",
                        "reason": "validation_snapshot_missing",
                    }
                )
                continue
            triggered = stock.pct_change > Decimal("0")
            results.append(
                {
                    "symbol": symbol,
                    "name": item.get("name", ""),
                    "status": "triggered" if triggered else "missed",
                    "close_return": str(stock.pct_change),
                    "reason": "positive_close" if triggered else "non_positive_close",
                }
            )

        return DailyMarketReviewValidationResult(
            status="completed",
            trade_date=trade_date,
            validation_date=validation_date,
            results=results,
            message=f"validated {len(results)} watch items",
        )


class DailyReviewMarkdownComposer:
    """
    Deterministic markdown composer used before a full LLM chain is enabled.
    """

    def compose(
        self,
        pack: EvidencePack,
        leaders: list[LeaderScore],
        limit_signal: Any,
        lhb_net_buy_amount: Decimal,
        run_llm: bool,
    ) -> str:
        """
        Compose a readable report from structured signals.
        """
        summary = pack.market_summary
        themes = pack.themes[:6]
        leader_lines = [
            (
                f"- **{leader.name}（{leader.symbol}）**：{_role_label(leader.role)}，"
                f"评分 {leader.score}；操作：{_action_label(leader.watch_action)}；"
                f"条件：{leader.entry_condition}；放弃：{leader.avoid_condition}。"
            )
            for leader in leaders[:10]
        ]
        theme_lines = [
            (
                f"- **{theme['theme']}**：状态 `{theme['status']}`，"
                f"强度 {theme['score']}，核心标的 "
                f"{', '.join(theme['leader_symbols']) or '暂无'}。"
            )
            for theme in themes
        ]
        quality_lines = [f"- {warning}" for warning in pack.data_quality] or ["- 未发现严重数据质量告警"]
        llm_note = (
            "\n\n> 已勾选 AI 编排，但当前 vn.py 迁移版先使用确定性复盘模板；"
            "后续会在 Evidence Pack 之上接入可审计 LLM 编排。"
            if run_llm
            else ""
        )
        return "\n".join(
            [
                "## 核心市场信号",
                (
                    f"- 上涨 {summary['advance_count']} 家，下跌 {summary['decline_count']} 家，"
                    f"平盘 {summary['flat_count']} 家。"
                ),
                (
                    f"- 涨停 {summary['limit_up_count']} 家，跌停 {summary['limit_down_count']} 家，"
                    f"市场宽度 {summary['breadth_score']}，情绪分 {summary['emotion_score']}。"
                ),
                (
                    f"- 涨停生态：封板 {limit_signal.sealed_count} 家，"
                    f"最高连板 {limit_signal.max_board_count}，炸板率 {limit_signal.broken_board_rate}。"
                ),
                f"- 龙虎榜净买合计：{lhb_net_buy_amount}。",
                "",
                "## 主线和板块",
                *(theme_lines or ["- 暂无可用板块数据，已从个股快照中尝试推断。"]),
                "",
                "## 明日观察计划",
                *(leader_lines or ["- 暂无可执行观察标的。"]),
                "",
                "## 操作纪律",
                "- 复盘只生成观察计划，不自动下单。",
                "- 高开加速、量能背离或板块内部明显分化时放弃追高。",
                "- 优先观察回踩承接和分歧换手，不把报告结论直接等同于交易指令。",
                "",
                "## 数据质量",
                *quality_lines,
                llm_note,
            ]
        ).strip()


def _no_data_result(bundle: DailyReviewDataBundle) -> DailyMarketReviewReportResult:
    return DailyMarketReviewReportResult(
        status="no_data",
        trade_date=bundle.trade_date,
        title=f"{bundle.trade_date.isoformat()} 每日市场复盘暂无数据",
        markdown=(
            "## 暂无可用行情数据\n\n"
            "已尝试从 vn.py 当前行情和 AKShare provider 读取全市场快照，"
            "但没有得到可用于复盘的个股数据。\n\n"
            "### provider 记录\n\n"
            + "\n".join(f"- {record}" for record in bundle.provider_records)
        ),
        evidence=[],
        audit=[{"mode": "deterministic", "provider_records": bundle.provider_records}],
        message="no_stock_snapshots",
    )


def _leader_to_watch_item(leader: LeaderScore, pack: EvidencePack) -> dict[str, Any]:
    evidence_ids = [
        item.evidence_id
        for item in pack.evidence
        if leader.symbol in item.content
    ][:5]
    return {
        "symbol": leader.symbol,
        "name": leader.name,
        "role": leader.role,
        "watch_action": leader.watch_action,
        "entry_condition": leader.entry_condition,
        "avoid_condition": leader.avoid_condition,
        "position_rule": leader.position_rule,
        "evidence_ids": evidence_ids,
    }


def _role_label(role: str) -> str:
    labels = {
        "sector_anchor": "板块锚点",
        "limit_up_height": "连板高度",
        "trend_core": "趋势核心",
        "risk_watch": "风险观察",
    }
    return labels.get(role, role)


def _action_label(action: str) -> str:
    labels = {
        "avoid": "规避",
        "observe_divergence": "分歧换手观察",
        "wait_pullback": "回踩承接观察",
        "low_level_rotation": "低位轮动观察",
    }
    return labels.get(action, action)


def next_calendar_day(value: date) -> date:
    """
    Return a simple next-day value for UI defaults and validation helpers.
    """
    return value + timedelta(days=1)
