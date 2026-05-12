from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import BarData

from vnpy_seven_boll.indicator import SevenBollIndicatorConfig, SevenBollPoint
from vnpy_seven_boll.signals import SevenBollSignalResult, evaluate_seven_boll_signals


def test_signal_engine_emits_all_documented_daily_signal_types() -> None:
    cases = {
        "trend_pullback_long": _trend_pullback_case(),
        "squeeze_breakout_long": _squeeze_breakout_case(),
        "mean_reversion_long": _mean_reversion_case(),
        "trend_exit": _trend_exit_case(),
        "overheat_reduce": _overheat_reduce_case(),
    }

    for expected_type, (bars, points) in cases.items():
        result = evaluate_seven_boll_signals(bars, points, SevenBollIndicatorConfig())

        assert isinstance(result, SevenBollSignalResult)
        signal = _signal(result, expected_type)
        assert signal.signal_type == expected_type
        assert signal.side in {"buy", "sell"}
        assert signal.score > 0
        assert signal.reason
        assert signal.risk


def test_signal_engine_is_deterministic_for_same_daily_history() -> None:
    bars, points = _squeeze_breakout_case()

    first = evaluate_seven_boll_signals(bars, points, SevenBollIndicatorConfig())
    second = evaluate_seven_boll_signals(bars, points, SevenBollIndicatorConfig())

    assert first == second


def test_signal_engine_applies_risk_first_priority_when_buy_and_sell_conflict() -> None:
    bars, points = _conflict_case()

    result = evaluate_seven_boll_signals(bars, points, SevenBollIndicatorConfig())

    assert result is not None
    assert {signal.signal_type for signal in result.signals} >= {
        "squeeze_breakout_long",
        "overheat_reduce",
    }
    assert result.sell_score > 0
    assert result.action == "sell_watch"


def test_squeeze_breakout_is_not_reduced_before_top_or_overheat() -> None:
    bars, points = _moderate_squeeze_breakout_case()

    result = evaluate_seven_boll_signals(bars, points, SevenBollIndicatorConfig(squeeze_percentile=25))

    assert result is not None
    assert [signal.signal_type for signal in result.signals] == ["squeeze_breakout_long"]
    assert result.action == "buy_watch"


def _trend_pullback_case() -> tuple[list[BarData], list[SevenBollPoint | None]]:
    points = [_point(index=0, close=108, zscore=1.6, regime="trend_up", mid_slope=3)]
    points.append(
        _point(
            index=1,
            close=105.3,
            high=107,
            low=104.7,
            zscore=1.06,
            regime="trend_up",
            mid_slope=3,
            bandwidth_percentile=45,
            bandwidth_slope=-0.01,
        )
    )
    return _bars_for_points(points), points


def _squeeze_breakout_case() -> tuple[list[BarData], list[SevenBollPoint | None]]:
    points = [_point(index=0, close=101, bandwidth_percentile=5, bandwidth_slope=-0.01, regime="squeeze")]
    points.append(
        _point(
            index=1,
            close=112,
            high=113,
            low=104,
            zscore=2.4,
            bandwidth_percentile=5,
            bandwidth_slope=0.02,
            regime="squeeze",
            volume=3000,
        )
    )
    return _bars_for_points(points, latest_volume=3000), points


def _mean_reversion_case() -> tuple[list[BarData], list[SevenBollPoint | None]]:
    points = [_point(index=0, close=88, zscore=-2.4, regime="range")]
    points.append(_point(index=1, close=90, zscore=-2.0, regime="range"))
    return _bars_for_points(points), points


def _trend_exit_case() -> tuple[list[BarData], list[SevenBollPoint | None]]:
    points = [_point(index=0, close=103, zscore=0.6, regime="trend_up", mid_slope=3)]
    points.append(_point(index=1, close=98, zscore=-0.4, regime="trend_down", mid_slope=-1))
    return _bars_for_points(points), points


def _overheat_reduce_case() -> tuple[list[BarData], list[SevenBollPoint | None]]:
    points = [_point(index=0, close=108, zscore=1.6, regime="trend_up", mid_slope=2)]
    points.append(
        _point(
            index=1,
            close=116,
            open_price=118,
            high=121,
            low=112,
            zscore=3.2,
            regime="extreme_overbought",
            volume=3000,
        )
    )
    return _bars_for_points(points, latest_open=118, latest_volume=3000), points


def _conflict_case() -> tuple[list[BarData], list[SevenBollPoint | None]]:
    points = [_point(index=0, close=101, bandwidth_percentile=5, bandwidth_slope=-0.01, regime="squeeze")]
    points.append(
        _point(
            index=1,
            close=116,
            open_price=118,
            high=121,
            low=105,
            zscore=3.2,
            bandwidth_percentile=5,
            bandwidth_slope=0.03,
            regime="extreme_overbought",
            volume=3000,
        )
    )
    return _bars_for_points(points, latest_open=118, latest_volume=3000), points


def _moderate_squeeze_breakout_case() -> tuple[list[BarData], list[SevenBollPoint | None]]:
    points = [_point(index=0, close=100.2, bandwidth_percentile=8, bandwidth_slope=-0.01, regime="squeeze")]
    points.append(
        _point(
            index=1,
            close=100.75,
            high=100.85,
            low=100.55,
            mid=100,
            dev=0.35,
            zscore=2.14,
            bandwidth_percentile=20,
            bandwidth_slope=0.01,
            regime="squeeze",
            volume=3000,
        )
    )
    return _bars_for_points(points, latest_volume=3000), points


def _point(
    *,
    index: int,
    close: float,
    mid: float = 100,
    dev: float = 5,
    high: float | None = None,
    low: float | None = None,
    open_price: float | None = None,
    volume: float = 1000,
    zscore: float | None = None,
    bandwidth_percentile: float | None = 50,
    mid_slope: float | None = 0,
    bandwidth_slope: float | None = 0,
    regime: str = "range",
) -> SevenBollPoint:
    zscore = (close - mid) / dev if zscore is None else zscore
    return SevenBollPoint(
        index=index,
        datetime=datetime(2024, 1, 2) + timedelta(days=index),
        close=close,
        high=high if high is not None else max(close, open_price or close) + 1,
        low=low if low is not None else min(close, open_price or close) - 1,
        volume=volume,
        mid=mid,
        dev=dev,
        top_band=mid + 3 * dev,
        upper2_band=mid + 2 * dev,
        upper1_band=mid + dev,
        lower1_band=mid - dev,
        lower2_band=mid - 2 * dev,
        bottom_band=mid - 3 * dev,
        zscore=zscore,
        bandwidth7=(6 * dev) / mid,
        bandwidth_percentile=bandwidth_percentile,
        mid_slope=mid_slope,
        bandwidth_slope=bandwidth_slope,
        rail_zone=_rail_zone(zscore),
        regime=regime,
    )


def _bars_for_points(
    points: list[SevenBollPoint | None],
    *,
    latest_open: float | None = None,
    latest_volume: float | None = None,
) -> list[BarData]:
    bars: list[BarData] = []
    for index, point in enumerate(points):
        assert point is not None
        open_price = latest_open if index == len(points) - 1 and latest_open is not None else point.close
        volume = latest_volume if index == len(points) - 1 and latest_volume is not None else point.volume
        bars.append(
            BarData(
                symbol="600519",
                exchange=Exchange.SSE,
                datetime=point.datetime,
                interval=Interval.DAILY,
                open_price=open_price,
                high_price=point.high,
                low_price=point.low,
                close_price=point.close,
                volume=volume,
                turnover=point.close * volume,
                gateway_name="test",
            )
        )
    return bars


def _signal(result: SevenBollSignalResult, signal_type: str) -> Any:
    return next(signal for signal in result.signals if signal.signal_type == signal_type)


def _rail_zone(zscore: float) -> str:
    if zscore >= 3:
        return "above_top"
    if zscore >= 2:
        return "top_to_upper2"
    if zscore >= 1:
        return "upper2_to_upper1"
    if zscore >= 0:
        return "upper1_to_mid"
    if zscore >= -1:
        return "mid_to_lower1"
    if zscore >= -2:
        return "lower1_to_lower2"
    if zscore >= -3:
        return "lower2_to_bottom"
    return "below_bottom"
