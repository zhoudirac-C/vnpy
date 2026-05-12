"""
Deterministic seven-rail Bollinger daily signal rules.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from .indicator import SevenBollIndicatorConfig, SevenBollPoint, _bar_float


@dataclass(frozen=True)
class SevenBollSignal:
    """
    A deterministic seven-rail signal with evidence for UI and AI context.
    """

    signal_type: str
    side: str
    score: float
    reason: str
    risk: str


@dataclass(frozen=True)
class SevenBollSignalResult:
    """
    Latest seven-rail signal assessment for one symbol.
    """

    point: SevenBollPoint
    action: str
    buy_score: float = 0.0
    sell_score: float = 0.0
    signals: list[SevenBollSignal] = field(default_factory=list)


def evaluate_seven_boll_signals(
    bars: Sequence[Any],
    points: Sequence[SevenBollPoint | None],
    config: SevenBollIndicatorConfig | None = None,
) -> SevenBollSignalResult | None:
    """
    Evaluate the latest daily point and return buy/sell watch signals.
    """
    cfg = config or SevenBollIndicatorConfig()
    latest = _latest_point(points)
    if latest is None:
        return None

    prev = _previous_point(points, latest.index)
    recent_points = [point for point in points[max(0, latest.index - 20) : latest.index + 1] if point]
    volume_ma20 = _average(
        [_bar_float(bar, "volume") for bar in bars[max(0, latest.index - 19) : latest.index + 1]]
    )
    volume_ratio = latest.volume / volume_ma20 if volume_ma20 > 0 else 1.0
    signals: list[SevenBollSignal] = []

    if _is_trend_pullback(latest, recent_points, cfg):
        score = _bounded_score(
            62
            + _positive(latest.mid_slope, scale=latest.close * 0.002)
            + _score_close_to(latest.close, latest.upper1_band, cfg.pullback_tolerance)
            + max(0, 12 - min(volume_ratio, 2.0) * 4),
        )
        signals.append(
            SevenBollSignal(
                signal_type="trend_pullback_long",
                side="buy",
                score=score,
                reason="uptrend_mid_slope_and_pullback_to_upper1",
                risk="close_below_mid_or_high_volume_breakdown",
            )
        )

    if _is_squeeze_breakout(latest, prev, volume_ratio, cfg):
        score = _bounded_score(
            64
            + max(0, 15 - float(latest.bandwidth_percentile or 100) * 0.8)
            + min(15, max(0, (volume_ratio - 1.0) * 10))
        )
        signals.append(
            SevenBollSignal(
                signal_type="squeeze_breakout_long",
                side="buy",
                score=score,
                reason="low_bandwidth_percentile_and_break_above_upper2",
                risk="close_back_below_mid_or_breakout_bar_low",
            )
        )

    if _is_mean_reversion_long(latest, prev):
        score = _bounded_score(58 + min(22, abs(latest.zscore) * 6))
        signals.append(
            SevenBollSignal(
                signal_type="mean_reversion_long",
                side="buy",
                score=score,
                reason="range_or_oversold_reclaim_from_lower2",
                risk="continuous_close_below_bottom_band",
            )
        )

    if _is_trend_exit(latest, prev):
        score = _bounded_score(65 + min(20, abs(latest.zscore) * 6))
        signals.append(
            SevenBollSignal(
                signal_type="trend_exit",
                side="sell",
                score=score,
                reason="close_below_mid_after_trend_structure",
                risk="trend_structure_broken",
            )
        )

    if latest.index < len(bars) and _is_overheat_reduce(latest, bars[latest.index], volume_ratio, cfg):
        score = _bounded_score(62 + min(22, (latest.zscore - 2.0) * 10) + min(12, volume_ratio * 3))
        signals.append(
            SevenBollSignal(
                signal_type="overheat_reduce",
                side="sell",
                score=score,
                reason="close_near_top_band_with_overheat_or_long_upper_shadow",
                risk="avoid_chasing_high",
            )
        )

    buy_score = max((signal.score for signal in signals if signal.side == "buy"), default=0.0)
    sell_score = max((signal.score for signal in signals if signal.side == "sell"), default=0.0)
    action = _resolve_action(signals, buy_score, sell_score)

    return SevenBollSignalResult(
        point=latest,
        action=action,
        buy_score=buy_score,
        sell_score=sell_score,
        signals=signals,
    )


def evaluate_seven_boll_signal(
    bars: Sequence[Any],
    points: Sequence[SevenBollPoint | None],
    config: SevenBollIndicatorConfig | None = None,
) -> SevenBollSignalResult | None:
    """
    Backward-compatible singular alias used by early scanner drafts.
    """
    return evaluate_seven_boll_signals(bars, points, config)


def _resolve_action(
    signals: Sequence[SevenBollSignal],
    buy_score: float,
    sell_score: float,
) -> str:
    if not signals:
        return "hold"

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


def _latest_point(points: Sequence[SevenBollPoint | None]) -> SevenBollPoint | None:
    for point in reversed(points):
        if point is not None:
            return point
    return None


def _previous_point(
    points: Sequence[SevenBollPoint | None],
    index: int,
) -> SevenBollPoint | None:
    for point in reversed(points[:index]):
        if point is not None:
            return point
    return None


def _is_trend_pullback(
    latest: SevenBollPoint,
    recent_points: Sequence[SevenBollPoint],
    cfg: SevenBollIndicatorConfig,
) -> bool:
    if latest.regime not in {"trend_up", "expansion_up"}:
        return False
    if latest.mid_slope is None or latest.mid_slope <= 0:
        return False
    if latest.close < latest.mid:
        return False
    touched_upper1 = latest.low <= latest.upper1_band * (1 + cfg.pullback_tolerance)
    reclaimed_upper1 = latest.close >= latest.upper1_band * (1 - cfg.pullback_tolerance)
    had_strength = any(point.zscore >= 1.35 for point in recent_points[-10:])
    return touched_upper1 and reclaimed_upper1 and had_strength


def _is_squeeze_breakout(
    latest: SevenBollPoint,
    prev: SevenBollPoint | None,
    volume_ratio: float,
    cfg: SevenBollIndicatorConfig,
) -> bool:
    if latest.bandwidth_percentile is None:
        return False
    if latest.bandwidth_percentile > cfg.squeeze_percentile:
        return False
    if latest.close <= latest.upper2_band:
        return False
    if volume_ratio < cfg.volume_breakout_ratio:
        return False
    if prev is None:
        return True
    return latest.bandwidth_slope is None or latest.bandwidth_slope >= 0 or latest.close > prev.close


def _is_mean_reversion_long(
    latest: SevenBollPoint,
    prev: SevenBollPoint | None,
) -> bool:
    if latest.regime not in {"range", "extreme_oversold"}:
        return False
    if latest.zscore > -2:
        return False
    if prev is None:
        return False
    return latest.close > prev.close or latest.close > latest.bottom_band


def _is_trend_exit(
    latest: SevenBollPoint,
    prev: SevenBollPoint | None,
) -> bool:
    if prev is None:
        return latest.regime == "trend_down" and latest.close < latest.mid
    crossed_mid = prev.close >= prev.mid and latest.close < latest.mid
    return crossed_mid or (latest.regime in {"trend_down", "expansion_down"} and latest.zscore < -0.4)


def _is_overheat_reduce(
    latest: SevenBollPoint,
    bar: Any,
    volume_ratio: float,
    cfg: SevenBollIndicatorConfig,
) -> bool:
    open_price = _bar_float(bar, "open_price", "open")
    upper_shadow = latest.high - max(open_price, latest.close)
    body = abs(latest.close - open_price)
    long_upper_shadow = upper_shadow > max(body, latest.dev * 0.3)
    near_top = latest.close >= latest.top_band * (1 - cfg.pullback_tolerance)
    overheated = latest.zscore >= 2.6
    volume_hot = volume_ratio >= cfg.volume_breakout_ratio
    return (near_top or overheated) and (long_upper_shadow or volume_hot)


def _average(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _bounded_score(value: float) -> float:
    return max(0.0, min(100.0, round(value, 2)))


def _positive(value: float | None, scale: float) -> float:
    if value is None or scale <= 0 or value <= 0:
        return 0.0
    return min(12.0, value / scale * 4.0)


def _score_close_to(close: float, target: float, tolerance: float) -> float:
    if target <= 0:
        return 0.0
    distance = abs(close - target) / target
    limit = max(tolerance, 0.0001) * 2
    if distance > limit:
        return 0.0
    return max(0.0, 12.0 * (1 - distance / limit))
