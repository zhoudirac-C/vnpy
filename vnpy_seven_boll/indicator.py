"""
Pure seven-rail Bollinger Band calculation for daily bars.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import sqrt
from typing import Any


@dataclass(frozen=True)
class SevenBollIndicatorConfig:
    """
    Parameters for the seven-rail Bollinger indicator.
    """

    window: int = 20
    std_ma_window: int = 5
    squeeze_lookback: int = 120
    trend_slope_window: int = 5
    pullback_tolerance: float = 0.01
    squeeze_percentile: float = 10.0
    volume_breakout_ratio: float = 1.5


@dataclass(frozen=True)
class SevenBollPoint:
    """
    One calculated seven-rail Bollinger point.
    """

    index: int
    datetime: Any
    close: float
    high: float
    low: float
    volume: float
    mid: float
    dev: float
    top_band: float
    upper2_band: float
    upper1_band: float
    lower1_band: float
    lower2_band: float
    bottom_band: float
    zscore: float
    bandwidth7: float
    bandwidth_percentile: float | None
    mid_slope: float | None
    bandwidth_slope: float | None
    rail_zone: str
    regime: str


def calculate_seven_bollinger(
    bars: Sequence[Any],
    config: SevenBollIndicatorConfig | None = None,
) -> list[SevenBollPoint | None]:
    """
    Calculate seven-rail Bollinger values for a bar sequence.
    """
    cfg = config or SevenBollIndicatorConfig()
    closes = [_bar_float(bar, "close_price", "close") for bar in bars]
    highs = [_bar_float(bar, "high_price", "high") for bar in bars]
    lows = [_bar_float(bar, "low_price", "low") for bar in bars]
    volumes = [_bar_float(bar, "volume") for bar in bars]
    datetimes = [getattr(bar, "datetime", None) for bar in bars]

    mids = _rolling_mean(closes, cfg.window)
    std0 = _rolling_std(closes, cfg.window)
    devs = _rolling_mean_nullable(std0, cfg.std_ma_window)
    bandwidths: list[float | None] = []
    raw_points: list[SevenBollPoint | None] = []

    for index, close in enumerate(closes):
        mid = mids[index]
        dev = devs[index]
        if mid is None or dev is None or dev <= 0:
            raw_points.append(None)
            bandwidths.append(None)
            continue

        top = mid + 3 * dev
        upper2 = mid + 2 * dev
        upper1 = mid + dev
        lower1 = mid - dev
        lower2 = mid - 2 * dev
        bottom = mid - 3 * dev
        zscore = (close - mid) / dev
        bandwidth = ((top - bottom) / mid) if mid else 0.0
        bandwidths.append(bandwidth)

        bandwidth_percentile = _rolling_percentile(
            bandwidths,
            index,
            cfg.squeeze_lookback,
        )
        mid_slope = _slope(mids, index, cfg.trend_slope_window)
        bandwidth_slope = _slope(bandwidths, index, cfg.trend_slope_window)
        rail_zone = _rail_zone(zscore)
        regime = _regime(zscore, mid_slope, bandwidth_percentile, bandwidth_slope, cfg)

        raw_points.append(
            SevenBollPoint(
                index=index,
                datetime=datetimes[index],
                close=close,
                high=highs[index],
                low=lows[index],
                volume=volumes[index],
                mid=mid,
                dev=dev,
                top_band=top,
                upper2_band=upper2,
                upper1_band=upper1,
                lower1_band=lower1,
                lower2_band=lower2,
                bottom_band=bottom,
                zscore=zscore,
                bandwidth7=bandwidth,
                bandwidth_percentile=bandwidth_percentile,
                mid_slope=mid_slope,
                bandwidth_slope=bandwidth_slope,
                rail_zone=rail_zone,
                regime=regime,
            )
        )

    return raw_points


def _rolling_mean(values: Sequence[float], window: int) -> list[float | None]:
    result: list[float | None] = []
    total = 0.0
    for index, value in enumerate(values):
        total += value
        if index >= window:
            total -= values[index - window]
        if index + 1 >= window:
            result.append(total / window)
        else:
            result.append(None)
    return result


def _rolling_std(values: Sequence[float], window: int) -> list[float | None]:
    result: list[float | None] = []
    for index in range(len(values)):
        if index + 1 < window:
            result.append(None)
            continue
        chunk = values[index + 1 - window: index + 1]
        mean = sum(chunk) / window
        variance = sum((value - mean) ** 2 for value in chunk) / window
        result.append(sqrt(variance))
    return result


def _rolling_mean_nullable(values: Sequence[float | None], window: int) -> list[float | None]:
    result: list[float | None] = []
    for index in range(len(values)):
        if index + 1 < window:
            result.append(None)
            continue
        chunk = values[index + 1 - window: index + 1]
        if any(value is None for value in chunk):
            result.append(None)
            continue
        result.append(sum(float(value) for value in chunk) / window)
    return result


def _rolling_percentile(
    values: Sequence[float | None],
    index: int,
    lookback: int,
) -> float | None:
    current = values[index]
    if current is None:
        return None
    chunk = [value for value in values[max(0, index + 1 - lookback): index + 1] if value is not None]
    if len(chunk) < max(10, min(lookback, 20)):
        return None
    if max(chunk) - min(chunk) <= max(abs(current), 1.0) * 1e-12:
        return 50.0
    below = sum(1 for value in chunk if value < current)
    return below / len(chunk) * 100


def _slope(values: Sequence[float | None], index: int, window: int) -> float | None:
    if index - window < 0:
        return None
    current = values[index]
    previous = values[index - window]
    if current is None or previous is None:
        return None
    return float(current) - float(previous)


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


def _regime(
    zscore: float,
    mid_slope: float | None,
    bandwidth_percentile: float | None,
    bandwidth_slope: float | None,
    cfg: SevenBollIndicatorConfig,
) -> str:
    if zscore >= 3:
        return "extreme_overbought"
    if zscore <= -3:
        return "extreme_oversold"
    if bandwidth_percentile is not None and bandwidth_percentile <= cfg.squeeze_percentile:
        return "squeeze"
    if mid_slope is not None and mid_slope > 0:
        if bandwidth_slope is not None and bandwidth_slope > 0 and zscore > 1:
            return "expansion_up"
        return "trend_up"
    if mid_slope is not None and mid_slope < 0:
        if bandwidth_slope is not None and bandwidth_slope > 0 and zscore < -1:
            return "expansion_down"
        return "trend_down"
    return "range"


def _bar_float(bar: Any, *names: str) -> float:
    for name in names:
        value = getattr(bar, name, None)
        if value is None and isinstance(bar, dict):
            value = bar.get(name)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0.0
    return 0.0
