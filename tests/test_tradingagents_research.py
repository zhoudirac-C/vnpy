from datetime import datetime

import pytest

from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import BarData
from vnpy_tradingagents.research import LongHorizonAgentJob, ResearchSnapshotBuilder
from vnpy_tradingagents.runtime import TradingAgentsMode, TradingAgentsRuntimeController
from vnpy_tradingagents.worker import TradingAgentsWorkerResponse


def test_research_snapshot_builder_compresses_multi_period_context():
    """ResearchSnapshotBuilder should compact daily/weekly/monthly bars into context."""
    builder = ResearchSnapshotBuilder(window_size=2)

    snapshot = builder.build(
        vt_symbol="600519.SSE",
        trade_date="2024-01-03",
        bar_groups={
            "daily": [
                make_bar("2024-01-02", Interval.DAILY, 10, 11, 9, 10, 100, 1_000),
                make_bar("2024-01-03", Interval.DAILY, 10, 12, 10, 12, 120, 1_440),
            ],
            "weekly": [
                make_bar("2024-01-01", Interval.WEEKLY, 9, 12, 8, 11, 500, 5_500),
            ],
        },
        fundamentals={"roe": 0.18},
        valuation={"pe": 28.5},
        industry={"name": "白酒"},
        benchmark={"name": "沪深300", "return_20d": 0.03},
        news_events=[{"title": "年报预告"}],
        portfolio_state={"current_weight": 0.08},
    )

    context = snapshot.to_context()

    assert snapshot.vt_symbol == "600519.SSE"
    assert context["research"]["trade_date"] == "2024-01-03"
    assert context["market"]["daily"]["latest_close"] == 12
    assert context["market"]["daily"]["ma_close"] == 11
    assert context["market"]["daily"]["window_volume"] == 220
    assert context["market"]["weekly"]["latest_close"] == 11
    assert context["fundamentals"]["roe"] == 0.18
    assert context["valuation"]["pe"] == 28.5
    assert context["industry"]["name"] == "白酒"
    assert context["benchmark"]["return_20d"] == 0.03
    assert context["news_events"][0]["title"] == "年报预告"
    assert context["portfolio_state"]["current_weight"] == 0.08


def test_research_snapshot_builder_requires_market_bars():
    """ResearchSnapshotBuilder should require at least one market bar."""
    builder = ResearchSnapshotBuilder()

    with pytest.raises(ValueError, match="bar_groups"):
        builder.build(vt_symbol="600519.SSE", trade_date="2024-01-03", bar_groups={})


def test_long_horizon_agent_job_runs_worker_and_persists_rating_and_intent():
    """LongHorizonAgentJob should persist long-term rating and portfolio intent."""
    runtime = TradingAgentsRuntimeController()
    runtime.enable(mode=TradingAgentsMode.REPORT_ONLY)
    worker = FakeWorker()
    storage = FakeAgentStorage()
    job = LongHorizonAgentJob(runtime=runtime, worker=worker, storage=storage)
    snapshot = ResearchSnapshotBuilder().build(
        vt_symbol="600519.SSE",
        trade_date="2024-01-03",
        bar_groups={
            "daily": [make_bar("2024-01-03", Interval.DAILY, 10, 12, 9, 11, 100, 1_100)]
        },
    )

    response = job.run(snapshot)

    assert response is not None
    assert response.rating == "Overweight"
    assert response.action == "buy"
    assert runtime.state.last_successful_run_id == "run-long-1"
    assert worker.requests[0].mode == "long_horizon"
    assert worker.requests[0].trade_date == "2024-01-03"
    assert worker.requests[0].context["market"]["daily"]["latest_close"] == 11
    assert storage.saved == [(worker.requests[0], response)]


def test_long_horizon_agent_job_skips_worker_when_runtime_disabled():
    """LongHorizonAgentJob should not run when the global switch is disabled."""
    runtime = TradingAgentsRuntimeController()
    worker = FakeWorker()
    storage = FakeAgentStorage()
    job = LongHorizonAgentJob(runtime=runtime, worker=worker, storage=storage)
    snapshot = ResearchSnapshotBuilder().build(
        vt_symbol="600519.SSE",
        trade_date="2024-01-03",
        bar_groups={
            "daily": [make_bar("2024-01-03", Interval.DAILY, 10, 12, 9, 11, 100, 1_100)]
        },
    )

    response = job.run(snapshot)

    assert response is None
    assert worker.requests == []
    assert storage.saved == []


def make_bar(
    day: str,
    interval: Interval,
    open_price: float,
    high_price: float,
    low_price: float,
    close_price: float,
    volume: float,
    turnover: float,
) -> BarData:
    """Create a bar fixture."""
    return BarData(
        symbol="600519",
        exchange=Exchange.SSE,
        datetime=datetime.fromisoformat(day),
        interval=interval,
        open_price=open_price,
        high_price=high_price,
        low_price=low_price,
        close_price=close_price,
        volume=volume,
        turnover=turnover,
        gateway_name="fake",
    )


class FakeWorker:
    """Fake TradingAgents worker for long-horizon job tests."""

    def __init__(self) -> None:
        self.requests = []

    def run(self, request):
        self.requests.append(request)
        return TradingAgentsWorkerResponse(
            run_id="run-long-1",
            vt_symbol=request.vt_symbol,
            rating="Overweight",
            confidence=0.81,
            report="长期研究报告",
            raw_state={"debate": "bullish"},
            action="buy",
            target_weight_hint=0.15,
            holding_period_hint="20d",
            risk_notes="估值回落风险",
        )


class FakeAgentStorage:
    """Fake storage that records worker result persistence."""

    def __init__(self) -> None:
        self.saved = []

    def save_worker_result(self, request, response):
        self.saved.append((request, response))
