"""
CTA-visible seven-rail Bollinger daily signal strategy.
"""

from __future__ import annotations

from collections.abc import Sequence

from vnpy.trader.constant import Interval
from vnpy_ctastrategy import BarData, CtaTemplate

from vnpy_seven_boll.indicator import (
    SevenBollIndicatorConfig,
    calculate_seven_bollinger,
)
from vnpy_seven_boll.signals import SevenBollSignal, evaluate_seven_boll_signals


BUY_SIGNAL_TYPES: frozenset[str] = frozenset(
    {
        "trend_pullback_long",
        "squeeze_breakout_long",
        "mean_reversion_long",
    }
)
SELL_SIGNAL_TYPES: frozenset[str] = frozenset(
    {
        "trend_exit",
        "overheat_reduce",
    }
)


class SevenBollSignalStrategy(CtaTemplate):
    """
    Daily CTA strategy that consumes deterministic seven-rail Bollinger signals.
    """

    author = "vn.py SevenBoll"

    window: int = 20
    std_ma_window: int = 5
    squeeze_lookback: int = 120
    squeeze_percentile: float = 10.0
    pullback_tolerance: float = 0.01
    fixed_size: float = 100
    stop_loss_pct: float = 0.05
    enable_trend_pullback: bool = True
    enable_squeeze_breakout: bool = True
    enable_mean_reversion: bool = True

    last_action: str = ""
    last_reason: str = ""
    last_signal_types: str = ""
    last_score: float = 0.0
    last_regime: str = ""
    daily_bar_count: int = 0

    parameters = [
        "window",
        "std_ma_window",
        "squeeze_lookback",
        "squeeze_percentile",
        "pullback_tolerance",
        "fixed_size",
        "stop_loss_pct",
        "enable_trend_pullback",
        "enable_squeeze_breakout",
        "enable_mean_reversion",
    ]
    variables = [
        "last_action",
        "last_reason",
        "last_signal_types",
        "last_score",
        "last_regime",
        "daily_bar_count",
    ]

    def __init__(
        self,
        cta_engine,
        strategy_name: str,
        vt_symbol: str,
        setting: dict,
    ) -> None:
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)
        self.daily_bars: list[BarData] = []

    def on_init(self) -> None:
        """
        Initialize from daily historical bars only.
        """
        self.write_log("七轨布林线日线策略初始化")
        self.load_bar(250, Interval.DAILY)
        self.put_event()

    def on_start(self) -> None:
        """
        Start daily seven-rail Bollinger signal consumption.
        """
        self.write_log("七轨布林线日线策略启动")
        self.put_event()

    def on_stop(self) -> None:
        """
        Stop the strategy.
        """
        self.write_log("七轨布林线日线策略停止")
        self.put_event()

    def on_bar(self, bar: BarData) -> None:
        """
        Evaluate one completed daily bar.
        """
        if bar.interval != Interval.DAILY:
            self._ignore("non_daily_bar")
            return

        self.daily_bars.append(bar)
        self.daily_bar_count = len(self.daily_bars)

        config = self._indicator_config()
        points = calculate_seven_bollinger(self.daily_bars, config)
        result = evaluate_seven_boll_signals(self.daily_bars, points, config)
        if result is None:
            self._ignore("no_indicator_point")
            return

        signals = self._enabled_signals(result.signals)
        if not signals:
            self._record_signal("hold", "no_enabled_signal", "", 0.0, result.point.regime)
            self.put_event()
            return

        buy_score = max((signal.score for signal in signals if signal.side == "buy"), default=0.0)
        sell_score = max((signal.score for signal in signals if signal.side == "sell"), default=0.0)
        action = self._resolve_action(signals, buy_score, sell_score)
        signal_types = ",".join(signal.signal_type for signal in signals)
        self._record_signal(action, "signal_evaluated", signal_types, max(buy_score, sell_score), result.point.regime)

        if action == "buy_watch":
            self._open_long(bar.close_price)
        elif action == "sell_watch":
            self._close_long(bar.close_price)
        else:
            self.last_reason = "hold"

        self.put_event()

    def _indicator_config(self) -> SevenBollIndicatorConfig:
        return SevenBollIndicatorConfig(
            window=int(self.window),
            std_ma_window=int(self.std_ma_window),
            squeeze_lookback=int(self.squeeze_lookback),
            squeeze_percentile=float(self.squeeze_percentile),
            pullback_tolerance=float(self.pullback_tolerance),
        )

    def _enabled_signals(self, signals: Sequence[SevenBollSignal]) -> list[SevenBollSignal]:
        enabled_buy_types: set[str] = set()
        if self.enable_trend_pullback:
            enabled_buy_types.add("trend_pullback_long")
        if self.enable_squeeze_breakout:
            enabled_buy_types.add("squeeze_breakout_long")
        if self.enable_mean_reversion:
            enabled_buy_types.add("mean_reversion_long")

        return [
            signal
            for signal in signals
            if signal.signal_type in SELL_SIGNAL_TYPES or signal.signal_type in enabled_buy_types
        ]

    def _resolve_action(
        self,
        signals: Sequence[SevenBollSignal],
        buy_score: float,
        sell_score: float,
    ) -> str:
        priority = {
            "trend_exit": 0,
            "overheat_reduce": 1,
            "squeeze_breakout_long": 2,
            "trend_pullback_long": 3,
            "mean_reversion_long": 4,
        }
        dominant = min(signals, key=lambda signal: (priority.get(signal.signal_type, 99), -signal.score))
        if dominant.side == "sell" and sell_score > 0:
            return "sell_watch"
        if dominant.side == "buy" and buy_score > 0:
            return "buy_watch"
        return "hold"

    def _open_long(self, price: float) -> None:
        if price <= 0:
            self._ignore("invalid_daily_close")
            return
        if self.pos > 0:
            self._ignore("already_long")
            return
        orderids = self.buy(price, float(self.fixed_size))
        self.last_reason = "submitted" if orderids else "submit_skipped"

    def _close_long(self, price: float) -> None:
        if price <= 0:
            self._ignore("invalid_daily_close")
            return
        volume = min(max(float(self.pos), 0.0), float(self.fixed_size))
        if volume <= 0:
            self._ignore("no_long_position")
            return
        orderids = self.sell(price, volume)
        self.last_reason = "submitted" if orderids else "submit_skipped"

    def _record_signal(
        self,
        action: str,
        reason: str,
        signal_types: str,
        score: float,
        regime: str,
    ) -> None:
        self.last_action = action
        self.last_reason = reason
        self.last_signal_types = signal_types
        self.last_score = score
        self.last_regime = regime

    def _ignore(self, reason: str) -> None:
        self.last_reason = reason
        self.put_event()
