from datetime import datetime, timedelta

import pytest

from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import BarData
from vnpy_tradingagents.intraday import IntradayAgentJob, IntradaySnapshotBuilder
from vnpy_tradingagents.runtime import TradingAgentsMode, TradingAgentsRuntimeController
from vnpy_tradingagents.worker import TradingAgentsWorkerResponse


def test_intraday_snapshot_builder_compresses_minute_bars():
    """IntradaySnapshotBuilder should compress raw bars into a compact AI context."""
    builder = IntradaySnapshotBuilder(window_size=3)

    snapshot = builder.build(
        vt_symbol="600519.SSE",
        bars=[
            make_bar("09:31", 10, 11, 9, 10, 100, 1_000),
            make_bar("09:32", 10, 12, 10, 11, 200, 2_200),
            make_bar("09:33", 11, 13, 11, 12, 300, 3_600),
        ],
        position={"volume": 100},
        trading_rules={"max_buy_volume": 50},
        news_events=[{"title": "盘中公告"}],
    )

    context = snapshot.to_context()

    assert snapshot.vt_symbol == "600519.SSE"
    assert snapshot.generated_at == datetime(2024, 1, 3, 9, 33)
    assert context["intraday"]["interval"] == "1m"
    assert context["intraday"]["last_price"] == 12
    assert context["intraday"]["ma_close"] == 11
    assert context["intraday"]["vwap"] == pytest.approx(11.3333333333)
    assert context["intraday"]["window_volume"] == 600
    assert len(context["intraday"]["bars"]) == 3
    assert context["position"]["volume"] == 100
    assert context["trading_rules"]["max_buy_volume"] == 50
    assert context["news_events"][0]["title"] == "盘中公告"


def test_intraday_snapshot_builder_rejects_empty_bars():
    """IntradaySnapshotBuilder should require at least one bar."""
    builder = IntradaySnapshotBuilder()

    with pytest.raises(ValueError, match="bars"):
        builder.build(vt_symbol="600519.SSE", bars=[])


def test_intraday_agent_job_runs_worker_and_persists_advice():
    """IntradayAgentJob should convert worker output into short-lived advice."""
    runtime = TradingAgentsRuntimeController()
    runtime.enable(mode=TradingAgentsMode.PAPER_ONLY)
    worker = FakeWorker()
    storage = FakeIntradayStorage()
    job = IntradayAgentJob(
        runtime=runtime,
        worker=worker,
        storage=storage,
        valid_for=timedelta(minutes=15),
    )
    snapshot = IntradaySnapshotBuilder().build(
        vt_symbol="600519.SSE",
        bars=[make_bar("10:10", 10, 11, 9, 10.5, 100, 1_050)],
    )

    advice = job.run(snapshot)

    assert advice is not None
    assert advice.vt_symbol == "600519.SSE"
    assert advice.action == "buy_on_pullback"
    assert advice.valid_until == datetime(2024, 1, 3, 10, 25)
    assert storage.saved == [advice]
    assert runtime.state.last_successful_run_id == "run-intraday-1"
    assert worker.requests[0].mode == "intraday_advice"
    assert worker.requests[0].trade_date == "2024-01-03"
    assert worker.requests[0].context["intraday"]["last_price"] == 10.5


def test_intraday_agent_job_skips_worker_when_runtime_disabled():
    """IntradayAgentJob should degrade to no advice when TradingAgents is disabled."""
    runtime = TradingAgentsRuntimeController()
    worker = FakeWorker()
    storage = FakeIntradayStorage()
    job = IntradayAgentJob(runtime=runtime, worker=worker, storage=storage)
    snapshot = IntradaySnapshotBuilder().build(
        vt_symbol="600519.SSE",
        bars=[make_bar("10:10", 10, 11, 9, 10.5, 100, 1_050)],
    )

    advice = job.run(snapshot)

    assert advice is None
    assert worker.requests == []
    assert storage.saved == []


def make_bar(
    minute: str,
    open_price: float,
    high_price: float,
    low_price: float,
    close_price: float,
    volume: float,
    turnover: float,
) -> BarData:
    """Create a 1-minute bar fixture."""
    hour, second = minute.split(":")
    return BarData(
        symbol="600519",
        exchange=Exchange.SSE,
        datetime=datetime(2024, 1, 3, int(hour), int(second)),
        interval=Interval.MINUTE,
        open_price=open_price,
        high_price=high_price,
        low_price=low_price,
        close_price=close_price,
        volume=volume,
        turnover=turnover,
        gateway_name="fake",
    )


class FakeWorker:
    """Fake TradingAgents worker for intraday job tests."""

    def __init__(self) -> None:
        self.requests = []

    def run(self, request):
        self.requests.append(request)
        return TradingAgentsWorkerResponse(
            run_id="run-intraday-1",
            vt_symbol=request.vt_symbol,
            rating="Hold",
            confidence=0.72,
            report="日内建议",
            raw_state={"reason": "pullback"},
            action="buy_on_pullback",
            risk_notes="只在规则信号确认后使用",
        )


class FakeIntradayStorage:
    """Fake storage that records intraday advice rows."""

    def __init__(self) -> None:
        self.saved = []

    def save_intraday_advice(self, advice):
        self.saved.append(advice)
