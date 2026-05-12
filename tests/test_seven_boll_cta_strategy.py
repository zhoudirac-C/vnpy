from __future__ import annotations

from datetime import datetime
from pathlib import Path

from vnpy.trader.constant import Direction, Exchange, Interval, Offset
from vnpy.trader.object import BarData
from vnpy_ctastrategy import CtaTemplate

from vnpy_seven_boll.indicator import SevenBollPoint
from vnpy_seven_boll.signals import SevenBollSignal, SevenBollSignalResult


def test_seven_boll_signal_strategy_is_visible_to_cta_loader() -> None:
    from strategies.seven_boll_signal_strategy import SevenBollSignalStrategy

    assert issubclass(SevenBollSignalStrategy, CtaTemplate)
    assert "window" in SevenBollSignalStrategy.parameters
    assert "std_ma_window" in SevenBollSignalStrategy.parameters
    assert "squeeze_lookback" in SevenBollSignalStrategy.parameters
    assert "fixed_size" in SevenBollSignalStrategy.parameters
    assert "enable_trend_pullback" in SevenBollSignalStrategy.parameters


def test_vnpy_cta_engine_scans_seven_boll_signal_strategy() -> None:
    from vnpy_ctastrategy.engine import CtaEngine

    logs = []
    cta_engine = object.__new__(CtaEngine)
    cta_engine.classes = {}
    cta_engine.write_log = logs.append

    cta_engine.load_strategy_class_from_folder(Path("strategies"), "strategies")

    assert "SevenBollSignalStrategy" in cta_engine.classes
    assert logs == []


def test_seven_boll_signal_strategy_ignores_non_daily_bars() -> None:
    from strategies.seven_boll_signal_strategy import SevenBollSignalStrategy

    cta_engine = FakeCtaEngine()
    strategy = SevenBollSignalStrategy(
        cta_engine=cta_engine,
        strategy_name="seven",
        vt_symbol="600519.SSE",
        setting={"fixed_size": 100},
    )
    strategy.inited = True
    strategy.trading = True

    strategy.on_bar(_bar(interval=Interval.MINUTE, close=100))

    assert cta_engine.orders == []
    assert strategy.last_reason == "non_daily_bar"


def test_seven_boll_signal_strategy_opens_long_from_buy_watch(monkeypatch) -> None:
    from strategies import seven_boll_signal_strategy as module
    from strategies.seven_boll_signal_strategy import SevenBollSignalStrategy

    monkeypatch.setattr(module, "calculate_seven_bollinger", lambda bars, config: [_point()])
    monkeypatch.setattr(module, "evaluate_seven_boll_signals", lambda bars, points, config: _result("buy_watch"))

    cta_engine = FakeCtaEngine()
    strategy = SevenBollSignalStrategy(
        cta_engine=cta_engine,
        strategy_name="seven",
        vt_symbol="600519.SSE",
        setting={"fixed_size": 100},
    )
    strategy.inited = True
    strategy.trading = True

    strategy.on_bar(_bar(interval=Interval.DAILY, close=100))

    assert cta_engine.orders == [
        {
            "direction": Direction.LONG,
            "offset": Offset.OPEN,
            "price": 100,
            "volume": 100,
            "stop": False,
        }
    ]
    assert strategy.last_action == "buy_watch"
    assert strategy.last_signal_types == "trend_pullback_long"


def test_seven_boll_signal_strategy_closes_existing_long_from_sell_watch(monkeypatch) -> None:
    from strategies import seven_boll_signal_strategy as module
    from strategies.seven_boll_signal_strategy import SevenBollSignalStrategy

    monkeypatch.setattr(module, "calculate_seven_bollinger", lambda bars, config: [_point()])
    monkeypatch.setattr(module, "evaluate_seven_boll_signals", lambda bars, points, config: _result("sell_watch"))

    cta_engine = FakeCtaEngine()
    strategy = SevenBollSignalStrategy(
        cta_engine=cta_engine,
        strategy_name="seven",
        vt_symbol="600519.SSE",
        setting={"fixed_size": 100},
    )
    strategy.inited = True
    strategy.trading = True
    strategy.pos = 60

    strategy.on_bar(_bar(interval=Interval.DAILY, close=100))

    assert cta_engine.orders == [
        {
            "direction": Direction.SHORT,
            "offset": Offset.CLOSE,
            "price": 100,
            "volume": 60,
            "stop": False,
        }
    ]
    assert strategy.last_action == "sell_watch"


def _result(action: str) -> SevenBollSignalResult:
    side = "buy" if action == "buy_watch" else "sell"
    signal_type = "trend_pullback_long" if side == "buy" else "trend_exit"
    signal = SevenBollSignal(
        signal_type=signal_type,
        side=side,
        score=80,
        reason="test_reason",
        risk="test_risk",
    )
    return SevenBollSignalResult(
        point=_point(),
        action=action,
        buy_score=80 if side == "buy" else 0,
        sell_score=80 if side == "sell" else 0,
        signals=[signal],
    )


def _point() -> SevenBollPoint:
    return SevenBollPoint(
        index=0,
        datetime=datetime(2024, 1, 2),
        close=100,
        high=101,
        low=99,
        volume=1000,
        mid=95,
        dev=5,
        top_band=110,
        upper2_band=105,
        upper1_band=100,
        lower1_band=90,
        lower2_band=85,
        bottom_band=80,
        zscore=1,
        bandwidth7=30 / 95,
        bandwidth_percentile=20,
        mid_slope=1,
        bandwidth_slope=0,
        rail_zone="upper2_to_upper1",
        regime="trend_up",
    )


def _bar(interval: Interval, close: float) -> BarData:
    return BarData(
        symbol="600519",
        exchange=Exchange.SSE,
        datetime=datetime(2024, 1, 2),
        interval=interval,
        open_price=close,
        high_price=close + 1,
        low_price=close - 1,
        close_price=close,
        volume=1000,
        turnover=close * 1000,
        gateway_name="test",
    )


class FakeCtaEngine:
    def __init__(self) -> None:
        self.orders = []
        self.logs = []

    def send_order(self, strategy, direction, offset, price, volume, stop, lock, net):
        self.orders.append(
            {
                "direction": direction,
                "offset": offset,
                "price": price,
                "volume": volume,
                "stop": stop,
            }
        )
        return ["seven.1"]

    def write_log(self, msg, strategy) -> None:
        self.logs.append((strategy.strategy_name, msg))

    def put_strategy_event(self, strategy) -> None:
        pass
