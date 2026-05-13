from __future__ import annotations

from datetime import datetime

import pytest

from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import BarData

from vnpy_seven_boll.indicator import SevenBollPoint
from vnpy_seven_boll.signals import SevenBollSignal, SevenBollSignalResult


def test_scan_request_rejects_non_daily_interval() -> None:
    from vnpy_seven_boll.scanner import SevenBollScanRequest

    with pytest.raises(ValueError, match="daily"):
        SevenBollScanRequest(interval=Interval.MINUTE)


def test_build_scan_request_from_settings_forces_daily_interval() -> None:
    from vnpy_seven_boll.scanner import build_scan_request_from_settings

    request = build_scan_request_from_settings({"seven_boll.scan.interval": "1m"})

    assert request.interval == Interval.DAILY


def test_scan_service_outputs_daily_candidate_fields(monkeypatch) -> None:
    from vnpy_seven_boll import scanner as module
    from vnpy_seven_boll.scanner import SevenBollScanRequest, SevenBollScanService

    monkeypatch.setattr(module, "calculate_seven_bollinger", lambda bars, config: [_point()])
    monkeypatch.setattr(module, "evaluate_seven_boll_signal", lambda bars, points, config: _signal_result())

    service = SevenBollScanService(FakeHistoryProvider(), run_id_factory=lambda: "scan-1")
    summary = service.scan(SevenBollScanRequest(symbols=("600519.SSE",), min_buy_score=65))

    assert summary.run_id == "scan-1"
    assert summary.scanned_symbols == 1
    assert summary.buy_candidates
    result = summary.buy_candidates[0]
    assert result.vt_symbol == "600519.SSE"
    assert result.name == "贵州茅台"
    assert result.concept == "白酒"
    assert result.action == "buy_watch"
    assert result.interval == "d"
    assert result.to_context()["interval"] == "d"
    assert result.to_context()["concept"] == "白酒"
    assert result.signal_types == ("trend_pullback_long",)


def test_scan_service_reports_progress_and_honors_cancel(monkeypatch) -> None:
    from vnpy_seven_boll import scanner as module
    from vnpy_seven_boll.scanner import (
        SevenBollScanProgress,
        SevenBollScanRequest,
        SevenBollScanService,
    )

    monkeypatch.setattr(module, "calculate_seven_bollinger", lambda bars, config: [_point()])
    monkeypatch.setattr(module, "evaluate_seven_boll_signal", lambda bars, points, config: _signal_result())

    progress_events: list[SevenBollScanProgress] = []

    service = SevenBollScanService(
        FakeHistoryProvider(["600519.SSE", "000001.SZSE"]),
        run_id_factory=lambda: "scan-progress",
    )
    summary = service.scan(
        SevenBollScanRequest(),
        progress_callback=progress_events.append,
        cancel_requested=lambda: len(progress_events) >= 2,
    )

    assert summary.status == "cancelled"
    assert summary.run_id == "scan-progress"
    assert summary.total_symbols == 2
    assert summary.scanned_symbols == 1
    assert summary.buy_candidates[0].vt_symbol == "600519.SSE"
    assert progress_events[0].status == "running"
    assert progress_events[0].total_symbols == 2
    assert progress_events[-1].status == "cancelled"
    assert progress_events[-1].buy_count == 1


def test_vnpy_provider_prefers_database_daily_bars() -> None:
    from vnpy_seven_boll.scanner import SevenBollScanRequest, VnpySevenBollHistoryProvider

    database = FakeDatabase([_bar()])
    datafeed = FailingDatafeed()
    provider = VnpySevenBollHistoryProvider(settings={"datafeed.name": "router"})
    provider._database = database
    provider._datafeed = datafeed

    bars = provider.load_bars("600519.SSE", SevenBollScanRequest())

    assert bars == database.bars
    assert database.calls[0]["interval"] == Interval.DAILY
    assert datafeed.requests == []


def test_vnpy_provider_falls_back_to_get_datafeed_daily_history(monkeypatch) -> None:
    from vnpy.trader import datafeed as datafeed_module
    from vnpy_seven_boll.scanner import SevenBollScanRequest, VnpySevenBollHistoryProvider

    datafeed = RecordingDatafeed([_bar()])
    monkeypatch.setattr(datafeed_module, "get_datafeed", lambda: datafeed)

    provider = VnpySevenBollHistoryProvider(settings={"datafeed.name": "router"})
    provider._database = FakeDatabase([])

    bars = provider.load_bars("600519.SSE", SevenBollScanRequest())

    assert bars == datafeed.bars
    assert datafeed.requests
    assert datafeed.requests[0].vt_symbol == "600519.SSE"
    assert datafeed.requests[0].interval == Interval.DAILY


def _signal_result() -> SevenBollSignalResult:
    signal = SevenBollSignal(
        signal_type="trend_pullback_long",
        side="buy",
        score=80,
        reason="test_reason",
        risk="test_risk",
    )
    return SevenBollSignalResult(
        point=_point(),
        action="buy_watch",
        buy_score=80,
        sell_score=0,
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


def _bar() -> BarData:
    return BarData(
        symbol="600519",
        exchange=Exchange.SSE,
        datetime=datetime(2024, 1, 2),
        interval=Interval.DAILY,
        open_price=100,
        high_price=101,
        low_price=99,
        close_price=100,
        volume=1000,
        turnover=100000,
        gateway_name="test",
    )


class FakeHistoryProvider:
    def __init__(self, symbols: list[str] | None = None) -> None:
        self.symbols = symbols or ["600519.SSE"]

    def load_symbols(self, request) -> list[str]:
        return self.symbols

    def load_bars(self, vt_symbol: str, request) -> list[BarData]:
        return [_bar()] * 25

    def load_name(self, vt_symbol: str) -> str:
        return {"600519.SSE": "贵州茅台", "000001.SZSE": "平安银行"}.get(vt_symbol, "")

    def load_concept(self, vt_symbol: str) -> str:
        return {"600519.SSE": "白酒", "000001.SZSE": "银行"}.get(vt_symbol, "")


class FakeDatabase:
    def __init__(self, bars: list[BarData]) -> None:
        self.bars = bars
        self.calls = []

    def load_bar_data(self, symbol, exchange, interval, start, end):
        self.calls.append(
            {
                "symbol": symbol,
                "exchange": exchange,
                "interval": interval,
                "start": start,
                "end": end,
            }
        )
        return self.bars


class RecordingDatafeed:
    def __init__(self, bars: list[BarData]) -> None:
        self.bars = bars
        self.requests = []
        self.inited = False

    def init(self, output=print):
        self.inited = True
        return True

    def query_bar_history(self, req, output=print):
        self.requests.append(req)
        return self.bars


class FailingDatafeed(RecordingDatafeed):
    def __init__(self) -> None:
        super().__init__([])

    def query_bar_history(self, req, output=print):
        raise AssertionError("datafeed should not be used when database has daily bars")
