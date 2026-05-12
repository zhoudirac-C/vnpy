"""
P31 seven-rail Bollinger daily backtest validation helpers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import BarData
from vnpy_ctastrategy.backtesting import BacktestingEngine, BacktestingMode

from strategies.seven_boll_signal_strategy import SevenBollSignalStrategy


@dataclass(frozen=True)
class SevenBollBacktestValidationResult:
    """
    One deterministic daily backtest validation scenario.
    """

    scenario: str
    interval: str
    engine_name: str
    bar_count: int
    metrics: dict[str, float]
    notes: str


def run_seven_boll_backtest_validation() -> list[SevenBollBacktestValidationResult]:
    """
    Run three daily-bar scenarios through vn.py BacktestingEngine.
    """
    return [
        _run_scenario("trend_pullback", _trend_pullback_bars()),
        _run_scenario("squeeze_breakout", _squeeze_breakout_bars(), {"squeeze_percentile": 25}),
        _run_scenario("mean_reversion", _mean_reversion_bars()),
    ]


def render_validation_markdown(results: list[SevenBollBacktestValidationResult]) -> str:
    """
    Render validation results for docs/community/ops/validation_results.
    """
    lines = [
        "# P31 七轨布林线回测验证结果",
        "",
        "验证对象：`SevenBollSignalStrategy`，通过 `vnpy_ctastrategy.BacktestingEngine` 消费日线 `BarData`。",
        "",
        "> 本验证仅用于验证逻辑，不代表生产收益。",
        "",
        "固定口径：`interval=d`，不包含分时/日内短线数据。",
        "",
        "| 场景 | interval | K线数 | 交易次数 | 胜率 | 盈亏比 | 最大回撤 | 假突破率 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for result in results:
        metrics = result.metrics
        lines.append(
            "| {scenario} | interval={interval} | {bar_count} | {trade_count:.0f} | "
            "{win_rate:.2f}% | {profit_loss_ratio:.2f} | {max_drawdown:.2f} | "
            "{false_breakout_rate:.2f}% |".format(
                scenario=result.scenario,
                interval=result.interval,
                bar_count=result.bar_count,
                trade_count=metrics["trade_count"],
                win_rate=metrics["win_rate"],
                profit_loss_ratio=metrics["profit_loss_ratio"],
                max_drawdown=metrics["max_drawdown"],
                false_breakout_rate=metrics["false_breakout_rate"],
            )
        )

    lines.extend(
        [
            "",
            "说明：",
            "",
            "- `trend_pullback` 覆盖强趋势回踩二轨附近的波段观察逻辑。",
            "- `squeeze_breakout` 覆盖带宽收口后向上突破的观察逻辑。",
            "- `mean_reversion` 覆盖震荡区间低位均值回归观察逻辑。",
            "- 假突破率在当前轻量验证中按亏损交易占比估算，仅用于回归测试跟踪。",
            "- 全流程只使用日线 K 线，未请求或读取分钟线。",
            "",
        ]
    )
    return "\n".join(lines)


def write_validation_report(
    results: list[SevenBollBacktestValidationResult],
    output_path: Path,
) -> None:
    """
    Write the rendered Markdown report.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_validation_markdown(results), encoding="utf-8")


def _run_scenario(
    scenario: str,
    bars: list[BarData],
    setting_overrides: dict[str, Any] | None = None,
) -> SevenBollBacktestValidationResult:
    engine = BacktestingEngine()
    engine.output = lambda _msg: None
    engine.set_parameters(
        vt_symbol="600519.SSE",
        interval=Interval.DAILY,
        start=bars[0].datetime,
        end=bars[-1].datetime,
        rate=0,
        slippage=0,
        size=1,
        pricetick=0.01,
        capital=1_000_000,
        mode=BacktestingMode.BAR,
    )
    setting = {
        "fixed_size": 100,
        "enable_trend_pullback": True,
        "enable_squeeze_breakout": True,
        "enable_mean_reversion": True,
    }
    if setting_overrides:
        setting.update(setting_overrides)
    engine.add_strategy(SevenBollSignalStrategy, setting)
    engine.history_data = bars
    engine.run_backtesting()

    statistics: dict[str, Any] = {}
    try:
        result_df = engine.calculate_result()
        statistics = engine.calculate_statistics(result_df, output=False)
    except Exception:
        statistics = {}

    metrics = _metrics_from_engine(engine, statistics)
    return SevenBollBacktestValidationResult(
        scenario=scenario,
        interval=Interval.DAILY.value,
        engine_name="vnpy_ctastrategy.BacktestingEngine",
        bar_count=len(bars),
        metrics=metrics,
        notes="daily_fixture",
    )


def _metrics_from_engine(
    engine: BacktestingEngine,
    statistics: dict[str, Any],
) -> dict[str, float]:
    trades = list(engine.trades.values())
    trade_count = float(statistics.get("total_trade_count") or len(trades))
    win_rate = float(statistics.get("win_rate") or 0.0)
    profit_loss_ratio = float(statistics.get("profit_loss_ratio") or 0.0)
    max_drawdown = float(
        statistics.get("max_drawdown")
        or statistics.get("max_ddpercent")
        or statistics.get("max_ddpercent_abs")
        or 0.0
    )
    losing_count = float(statistics.get("losing_trade_count") or 0.0)
    false_breakout_rate = losing_count / trade_count * 100 if trade_count else 0.0
    return {
        "trade_count": trade_count,
        "win_rate": win_rate,
        "profit_loss_ratio": profit_loss_ratio,
        "max_drawdown": max_drawdown,
        "false_breakout_rate": false_breakout_rate,
    }


def _trend_pullback_bars() -> list[BarData]:
    closes: list[float] = []
    price = 80.0
    for index in range(70):
        price += 0.45
        if index in {35, 52, 60}:
            price -= 1.2
        closes.append(price)
    return _bars_from_closes(closes)


def _squeeze_breakout_bars() -> list[BarData]:
    closes: list[float] = []
    for index in range(45):
        closes.append(100.0 + (4.0 if index % 2 else -4.0))
    for index in range(35):
        closes.append(100.0 + (0.35 if index % 2 else -0.35))
    closes.extend([100.75, 101.0, 101.2, 101.1, 100.9, 101.4])
    return _bars_from_closes(closes, breakout_volume_from=80)


def _mean_reversion_bars() -> list[BarData]:
    closes: list[float] = []
    for index in range(80):
        closes.append(100.0 + (5.0 if index % 6 < 3 else -5.0))
    closes.extend([94.0, 91.0, 88.0, 90.0, 93.0, 96.0, 100.0])
    return _bars_from_closes(closes)


def _bars_from_closes(
    closes: list[float],
    breakout_volume_from: int | None = None,
) -> list[BarData]:
    start = datetime(2024, 1, 2)
    bars: list[BarData] = []
    for index, close in enumerate(closes):
        volume = 1000
        if breakout_volume_from is not None and index >= breakout_volume_from:
            volume = 2500
        bars.append(
            BarData(
                symbol="600519",
                exchange=Exchange.SSE,
                datetime=start + timedelta(days=index),
                interval=Interval.DAILY,
                open_price=close,
                high_price=close + 1,
                low_price=close - 1,
                close_price=close,
                volume=volume,
                turnover=close * volume,
                gateway_name="fixture",
            )
        )
    return bars
