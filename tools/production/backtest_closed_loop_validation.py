from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import BarData
from vnpy.trader.utility import extract_vt_symbol
from vnpy_ctastrategy import CtaTemplate
from vnpy_ctastrategy.backtesting import BacktestingEngine, BacktestingMode

from vnpy_tradingagents.backtesting_app_bridge import (
    BacktestingAppBridge,
    BacktestingDecisionPoint,
)
from vnpy_tradingagents.fusion import RuleSignal, SignalFusionService
from vnpy_tradingagents.policy import AiSignalPolicy
from vnpy_tradingagents.risk import (
    DecisionAuditRecord,
    OrderIntent,
    PreOrderDecisionService,
    RiskRuleSet,
)
from vnpy_tradingagents.runtime import TradingAgentsMode, TradingAgentsRuntimeController
from vnpy_tradingagents.signals import IntradayAdvice, PortfolioIntent, RatingSignal


@dataclass(frozen=True)
class BacktestClosedLoopConfig:
    """
    Configuration for one deterministic P19 validation run.
    """

    vt_symbol: str = "600519.SSE"
    fixture_path: Path = Path("tests/fixtures/e2e/600519.SSE_d.csv")
    output_path: Path | None = None
    json_output_path: Path | None = None
    capital: int = 1_000_000
    rate: float = 0.0003
    slippage: float = 0.2
    size: float = 1
    pricetick: float = 0.01
    volume: float = 1
    max_order_value: float = 1_000_000


@dataclass(frozen=True)
class BacktestClosedLoopResult:
    """
    Auditable result for one P19 validation run.
    """

    success: bool
    vt_symbol: str
    fixture_path: str
    engine_name: str
    bar_count: int
    trade_count: int
    audit_count: int
    live_gateway_touched: bool
    statistics: dict[str, Any]
    audit_records: list[dict[str, Any]]
    trades: list[dict[str, Any]]
    notes: list[str]


class AiBacktestValidationStrategy(CtaTemplate):
    """
    Minimal CTA strategy used only by the P19 validation harness.
    """

    author = "vnpy_tradingagents"
    parameters = ["ai_bridge", "volume"]
    variables = []

    ai_bridge: BacktestingAppBridge | None = None
    volume: float = 1

    def on_init(self) -> None:
        return

    def on_bar(self, bar: BarData) -> None:
        if self.ai_bridge is None or self.pos:
            return

        trade_date = bar.datetime.strftime("%Y-%m-%d")
        result = self.ai_bridge.evaluate_decision(
            BacktestingDecisionPoint(
                vt_symbol=self.vt_symbol,
                trade_date=trade_date,
                at=bar.datetime,
                rule_signal=RuleSignal(action="buy", confidence=0.9, reason="p19_fixture_rule"),
                order_intent=OrderIntent(
                    vt_symbol=self.vt_symbol,
                    action="buy",
                    price=bar.close_price,
                    volume=self.volume,
                    current_position=self.pos,
                ),
            )
        )

        if result.decision.submit_allowed and result.fused_signal.action == "buy":
            self.buy(bar.close_price * 2, self.volume)


class FixtureSignalReader:
    """
    Deterministic AI signal reader for local fixture backtests.
    """

    def load_latest_rating_signal(self, vt_symbol: str, trade_date: str) -> RatingSignal:
        return RatingSignal(vt_symbol, "Buy", 0.82, "p19-rating-fixture")

    def load_latest_intraday_advice(self, vt_symbol: str, at: datetime) -> IntradayAdvice:
        return IntradayAdvice(vt_symbol, "buy", 0.76, at + timedelta(days=1), "p19-advice-fixture")

    def load_portfolio_intents(self, trade_date: str) -> list[PortfolioIntent]:
        return [
            PortfolioIntent(
                "600519.SSE",
                trade_date,
                "buy",
                0.05,
                "fixture",
                "p19 validation fixture",
                "p19-portfolio-fixture",
            )
        ]


class RecordingAuditStorage:
    """
    In-memory audit storage for validation evidence.
    """

    def __init__(self) -> None:
        self.records: list[DecisionAuditRecord] = []

    def save_decision(self, record: DecisionAuditRecord) -> None:
        self.records.append(record)


def run_backtest_closed_loop(config: BacktestClosedLoopConfig) -> BacktestClosedLoopResult:
    """
    Run a deterministic vn.py backtest through the AI signal bridge.
    """
    bars = load_fixture_bars(config.fixture_path, config.vt_symbol)
    if not bars:
        return BacktestClosedLoopResult(
            success=False,
            vt_symbol=config.vt_symbol,
            fixture_path=str(config.fixture_path),
            engine_name="vnpy_ctastrategy.BacktestingEngine",
            bar_count=0,
            trade_count=0,
            audit_count=0,
            live_gateway_touched=False,
            statistics={},
            audit_records=[],
            trades=[],
            notes=["fixture has no bars"],
        )

    audit_storage = RecordingAuditStorage()
    runtime = TradingAgentsRuntimeController()
    runtime.enable(mode=TradingAgentsMode.PAPER_ONLY)
    ai_bridge = BacktestingAppBridge(
        signal_reader=FixtureSignalReader(),
        fusion_service=SignalFusionService(policy=AiSignalPolicy(runtime)),
        decision_service=PreOrderDecisionService(
            rules=RiskRuleSet(max_order_value=config.max_order_value),
            audit_storage=audit_storage,
            decision_id_factory=_decision_id_factory("p19-decision"),
            clock=lambda: bars[0].datetime,
        ),
    )

    engine = BacktestingEngine()
    engine.output = lambda msg: None
    engine.set_parameters(
        vt_symbol=config.vt_symbol,
        interval=Interval.DAILY,
        start=bars[0].datetime,
        end=bars[-1].datetime,
        rate=config.rate,
        slippage=config.slippage,
        size=config.size,
        pricetick=config.pricetick,
        capital=config.capital,
        mode=BacktestingMode.BAR,
    )
    engine.add_strategy(
        AiBacktestValidationStrategy,
        {
            "ai_bridge": ai_bridge,
            "volume": config.volume,
        },
    )
    engine.history_data = bars
    engine.run_backtesting()
    result_df = engine.calculate_result()
    statistics = _jsonable(engine.calculate_statistics(result_df, output=False))

    trade_records = [_trade_to_dict(trade) for trade in engine.trades.values()]
    audit_records = [_audit_to_dict(record) for record in audit_storage.records]
    success = bool(bars and trade_records and audit_records)

    return BacktestClosedLoopResult(
        success=success,
        vt_symbol=config.vt_symbol,
        fixture_path=str(config.fixture_path),
        engine_name="vnpy_ctastrategy.BacktestingEngine",
        bar_count=len(bars),
        trade_count=len(trade_records),
        audit_count=len(audit_records),
        live_gateway_touched=False,
        statistics=statistics,
        audit_records=audit_records,
        trades=trade_records,
        notes=[
            "fixture backtest; not a broker, QMT, XTP or TORA run",
            "未触碰真实 Gateway/MainEngine",
        ],
    )


def load_fixture_bars(path: Path, vt_symbol: str) -> list[BarData]:
    """
    Load local CSV bars into vn.py BarData objects.
    """
    symbol, exchange = extract_vt_symbol(vt_symbol)
    bars: list[BarData] = []
    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            bars.append(
                BarData(
                    symbol=symbol,
                    exchange=Exchange(exchange),
                    datetime=datetime.fromisoformat(row["datetime"]),
                    interval=Interval.DAILY,
                    volume=float(row.get("volume") or 0),
                    turnover=float(row.get("turnover") or 0),
                    open_interest=float(row.get("open_interest") or 0),
                    open_price=float(row["open"]),
                    high_price=float(row["high"]),
                    low_price=float(row["low"]),
                    close_price=float(row["close"]),
                    gateway_name="P19_FIXTURE",
                )
            )
    return bars


def render_markdown(result: BacktestClosedLoopResult) -> str:
    """
    Render human-readable P19 validation evidence.
    """
    status = "通过" if result.success else "失败"
    statistics = result.statistics
    lines = [
        "# P19 回测闭环验证结果",
        "",
        f"- 结果：`{status}`",
        f"- 标的：`{result.vt_symbol}`",
        f"- 数据：`fixture:{result.fixture_path}`",
        f"- 引擎：`{result.engine_name}`",
        f"- K 线数量：`{result.bar_count}`",
        f"- 回测成交数：`{result.trade_count}`",
        f"- AI 审计数：`{result.audit_count}`",
        f"- live_gateway_touched：`{str(result.live_gateway_touched).lower()}`",
        "",
        "## 关键统计",
        "",
        "| 指标 | 值 |",
        "| --- | --- |",
        f"| total_trade_count | `{statistics.get('total_trade_count', 0)}` |",
        f"| total_return | `{statistics.get('total_return', 0)}` |",
        f"| max_drawdown | `{statistics.get('max_drawdown', 0)}` |",
        f"| sharpe_ratio | `{statistics.get('sharpe_ratio', 0)}` |",
        "",
        "## 审计摘要",
        "",
        "| decision_id | action | ai_used | risk_decision | source_run_ids |",
        "| --- | --- | --- | --- | --- |",
    ]

    for record in result.audit_records:
        source_ids = ",".join(record.get("ai_source_run_ids", []))
        lines.append(
            "| {decision_id} | `{action}` | `{ai_used}` | `{risk_decision}` | `{source}` |".format(
                decision_id=record.get("decision_id", ""),
                action=record.get("action", ""),
                ai_used=str(record.get("ai_used", "")).lower(),
                risk_decision=record.get("risk_decision", ""),
                source=source_ids,
            )
        )

    lines.extend(
        [
            "",
            "## 备注",
            "",
        ]
    )
    for note in result.notes:
        lines.append(f"- {note}")

    return "\n".join(lines) + "\n"


def write_result_files(result: BacktestClosedLoopResult, config: BacktestClosedLoopConfig) -> None:
    """
    Write Markdown and JSON evidence when paths are configured.
    """
    if config.output_path:
        config.output_path.parent.mkdir(parents=True, exist_ok=True)
        config.output_path.write_text(render_markdown(result), encoding="utf-8")

    if config.json_output_path:
        config.json_output_path.parent.mkdir(parents=True, exist_ok=True)
        config.json_output_path.write_text(
            json.dumps(_jsonable(asdict(result)), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> int:
    """
    CLI entrypoint for P19 validation.
    """
    parser = argparse.ArgumentParser(description="Run P19 backtest closed-loop validation.")
    parser.add_argument("--vt-symbol", default="600519.SSE")
    parser.add_argument("--fixture", type=Path, default=Path("tests/fixtures/e2e/600519.SSE_d.csv"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    config = BacktestClosedLoopConfig(
        vt_symbol=args.vt_symbol,
        fixture_path=args.fixture,
        output_path=args.output,
        json_output_path=args.json_output,
    )
    result = run_backtest_closed_loop(config)
    write_result_files(result, config)
    if not config.output_path:
        print(render_markdown(result))
    return 0 if result.success else 1


def _decision_id_factory(prefix: str):
    counter = {"value": 0}

    def next_id() -> str:
        counter["value"] += 1
        return f"{prefix}-{counter['value']}"

    return next_id


def _audit_to_dict(record: DecisionAuditRecord) -> dict[str, Any]:
    data = asdict(record)
    data["created_at"] = record.created_at.isoformat()
    data["risk_decision"] = record.risk_decision.value
    return data


def _trade_to_dict(trade: Any) -> dict[str, Any]:
    return {
        "vt_tradeid": trade.vt_tradeid,
        "vt_symbol": trade.vt_symbol,
        "direction": trade.direction.value if trade.direction else "",
        "offset": trade.offset.value,
        "price": trade.price,
        "volume": trade.volume,
        "datetime": trade.datetime.isoformat() if trade.datetime else "",
    }


def _jsonable(value: Any) -> Any:
    """
    Convert pandas/numpy/date values into JSON-native values.
    """
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, datetime | date):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


if __name__ == "__main__":
    raise SystemExit(main())
