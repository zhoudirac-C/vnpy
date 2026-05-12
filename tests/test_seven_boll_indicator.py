from __future__ import annotations

from datetime import datetime, timedelta
from math import isclose, sqrt

from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import BarData

from vnpy_seven_boll.indicator import (
    SevenBollIndicatorConfig,
    SevenBollPoint,
    calculate_seven_bollinger,
)


def test_indicator_calculates_documented_daily_rails() -> None:
    bars = _daily_bars([float(price) for price in range(10, 50)])
    points = calculate_seven_bollinger(bars)

    assert points[:23] == [None] * 23
    point = points[-1]
    assert isinstance(point, SevenBollPoint)

    closes = [bar.close_price for bar in bars]
    expected_mid = sum(closes[-20:]) / 20
    expected_std0 = [_population_std(closes[index - 19 : index + 1]) for index in range(19, len(closes))]
    expected_dev = sum(expected_std0[-5:]) / 5

    assert point.datetime == bars[-1].datetime
    assert point.mid == expected_mid
    assert point.dev == expected_dev
    assert point.top_band == expected_mid + 3 * expected_dev
    assert point.upper2_band == expected_mid + 2 * expected_dev
    assert point.upper1_band == expected_mid + expected_dev
    assert point.lower1_band == expected_mid - expected_dev
    assert point.lower2_band == expected_mid - 2 * expected_dev
    assert point.bottom_band == expected_mid - 3 * expected_dev
    assert point.bandwidth7 == (point.top_band - point.bottom_band) / point.mid
    assert point.zscore == (point.close - point.mid) / point.dev
    assert point.mid_slope is not None and point.mid_slope > 0
    assert point.rail_zone == "upper2_to_upper1"
    assert point.regime == "trend_up"


def test_indicator_classifies_range_extremes_and_squeeze_with_daily_bars() -> None:
    range_points = calculate_seven_bollinger(_daily_bars([100.0 + (1 if i % 2 else -1) for i in range(80)]))
    range_point = _last_point(range_points)
    assert isclose(range_point.mid_slope or 0, 0, abs_tol=1e-12)
    assert range_point.regime == "range"

    overbought_points = calculate_seven_bollinger(_daily_bars([100.0] * 39 + [130.0]))
    overbought = _last_point(overbought_points)
    assert overbought.rail_zone == "above_top"
    assert overbought.regime == "extreme_overbought"

    oversold_points = calculate_seven_bollinger(_daily_bars([100.0] * 39 + [70.0]))
    oversold = _last_point(oversold_points)
    assert oversold.rail_zone == "below_bottom"
    assert oversold.regime == "extreme_oversold"

    squeeze_closes: list[float] = []
    for index in range(90):
        squeeze_closes.append(100.0 + (8.0 if index % 2 else -8.0))
    for index in range(90):
        squeeze_closes.append(100.0 + (0.4 if index % 2 else -0.4))

    squeeze_points = calculate_seven_bollinger(
        _daily_bars(squeeze_closes),
        SevenBollIndicatorConfig(squeeze_lookback=120, squeeze_percentile=15),
    )
    squeeze = _last_point(squeeze_points)
    assert squeeze.bandwidth_percentile is not None
    assert squeeze.bandwidth_percentile <= 15
    assert squeeze.regime == "squeeze"


def _daily_bars(closes: list[float]) -> list[BarData]:
    start = datetime(2024, 1, 2)
    bars: list[BarData] = []
    for index, close in enumerate(closes):
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
                volume=1000,
                turnover=close * 1000,
                gateway_name="test",
            )
        )
    return bars


def _population_std(values: list[float]) -> float:
    mean = sum(values) / len(values)
    return sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def _last_point(points: list[SevenBollPoint | None]) -> SevenBollPoint:
    point = next(point for point in reversed(points) if point is not None)
    assert isinstance(point, SevenBollPoint)
    return point
