from datetime import datetime

from vnpy_tradingagents.risk import RiskRuleSet
from vnpy_tradingagents.runtime import TradingAgentsMode, TradingAgentsRuntimeController
from vnpy_tradingagents.signals import PortfolioIntent
from vnpy_tradingagents.worker import TradingAgentsWorkerRequest, TradingAgentsWorkerResponse


def test_historical_ai_signal_job_generates_point_in_time_signals():
    """Historical signal generation should call LLM before backtest, not inside bars."""
    from vnpy_tradingagents.backtesting import (
        HistoricalAiSignalJob,
        HistoricalAiSignalRequest,
    )

    runtime = TradingAgentsRuntimeController()
    runtime.enable(mode=TradingAgentsMode.PAPER_ONLY)
    toolkit = FakeToolkit()
    worker = FakeWorker()
    storage = FakeAgentStorage()
    job = HistoricalAiSignalJob(
        runtime=runtime,
        toolkit=toolkit,
        worker=worker,
        storage=storage,
        run_id_factory=lambda request: f"hist-{request.vt_symbol}-{request.trade_time.date()}",
    )
    signal_request = HistoricalAiSignalRequest(
        vt_symbol="600519.SSE",
        trade_time=datetime(2024, 1, 3, 10),
        start=datetime(2024, 1, 1),
        end=datetime(2024, 1, 3, 10),
    )

    result = job.run([signal_request])

    assert result.total == 1
    assert result.succeeded == 1
    assert result.failed == 0
    assert worker.requests[0].mode == "backtest_signal"
    assert worker.requests[0].run_id == "hist-600519.SSE-2024-01-03"
    assert worker.requests[0].context["point_in_time"]["trade_time"] == "2024-01-03T10:00:00"
    assert storage.saved == [(worker.requests[0], worker.responses[0])]


def test_historical_ai_signal_job_is_disabled_without_calling_worker():
    """Disabled TradingAgents should not generate historical AI signals."""
    from vnpy_tradingagents.backtesting import (
        HistoricalAiSignalJob,
        HistoricalAiSignalRequest,
    )

    worker = FakeWorker()
    job = HistoricalAiSignalJob(
        runtime=TradingAgentsRuntimeController(),
        toolkit=FakeToolkit(),
        worker=worker,
        storage=FakeAgentStorage(),
    )

    result = job.run(
        [
            HistoricalAiSignalRequest(
                vt_symbol="600519.SSE",
                trade_time=datetime(2024, 1, 3, 10),
                start=datetime(2024, 1, 1),
                end=datetime(2024, 1, 3, 10),
            )
        ]
    )

    assert result.total == 1
    assert result.succeeded == 0
    assert result.failed == 0
    assert result.skipped == 1
    assert worker.requests == []


def test_backtest_strategy_reads_stored_ai_signals_without_worker():
    """AI backtest strategy should be deterministic over stored signals."""
    from vnpy_tradingagents.backtesting import (
        AiBacktestDecisionContext,
        TradingAgentsBacktestStrategy,
    )

    audit_storage = FakeAuditStorage()
    strategy = TradingAgentsBacktestStrategy(
        signal_reader=FakeSignalReader(make_intent("buy")),
        rules=RiskRuleSet(max_order_value=100_000),
        audit_storage=audit_storage,
        decision_id_factory=lambda: "backtest-decision-1",
        clock=lambda: datetime(2024, 1, 3, 10),
    )

    result = strategy.evaluate(
        AiBacktestDecisionContext(
            vt_symbol="600519.SSE",
            trade_time=datetime(2024, 1, 3, 10),
            price=100,
            volume=10,
        )
    )

    assert result.ignored_reason == ""
    assert result.trade_intent is not None
    assert result.decision is not None
    assert result.decision.submit_allowed
    assert audit_storage.saved == [result.decision.audit_record]


def test_backtest_strategy_reports_no_signal_without_error():
    """Missing historical AI signals should produce a stable no-signal result."""
    from vnpy_tradingagents.backtesting import (
        AiBacktestDecisionContext,
        TradingAgentsBacktestStrategy,
    )

    strategy = TradingAgentsBacktestStrategy(
        signal_reader=FakeSignalReader(None),
        rules=RiskRuleSet(),
        audit_storage=FakeAuditStorage(),
    )

    result = strategy.evaluate(
        AiBacktestDecisionContext(
            vt_symbol="600519.SSE",
            trade_time=datetime(2024, 1, 3, 10),
            price=100,
            volume=10,
        )
    )

    assert result.ignored_reason == "no_ai_signal"
    assert result.decision is None


class FakeToolkit:
    """Fake context toolkit for point-in-time generation."""

    def __init__(self) -> None:
        self.queries = []

    def build_context(self, query):
        self.queries.append(query)
        return {"market": {"bars": [{"close": 100}]}}


class FakeWorker:
    """Fake worker collecting historical requests."""

    def __init__(self) -> None:
        self.requests = []
        self.responses = []

    def run(self, request: TradingAgentsWorkerRequest) -> TradingAgentsWorkerResponse:
        self.requests.append(request)
        response = TradingAgentsWorkerResponse(
            run_id=request.run_id,
            vt_symbol=request.vt_symbol,
            rating="Buy",
            confidence=0.8,
            report="历史AI信号",
            raw_state={"status": "ok"},
            action="buy",
            target_weight_hint=0.15,
            holding_period_hint="20d",
            risk_notes="回撤风险",
        )
        self.responses.append(response)
        return response


class FakeAgentStorage:
    """Fake storage recording generated signal outputs."""

    def __init__(self) -> None:
        self.saved = []

    def save_worker_result(self, request, response) -> None:
        self.saved.append((request, response))


class FakeSignalReader:
    """Fake historical signal reader."""

    def __init__(self, intent: PortfolioIntent | None) -> None:
        self.intent = intent
        self.calls = []

    def load_latest_trade_intent(self, vt_symbol: str, trade_date: str):
        self.calls.append((vt_symbol, trade_date))
        return self.intent


class FakeAuditStorage:
    """Audit storage fake recording decisions."""

    def __init__(self) -> None:
        self.saved = []

    def save_decision(self, record) -> None:
        self.saved.append(record)


def make_intent(action: str) -> PortfolioIntent:
    """Create a stored trade intent fixture."""
    return PortfolioIntent(
        vt_symbol="600519.SSE",
        trade_date="2024-01-03",
        action=action,
        target_weight_hint=0.15,
        holding_period_hint="20d",
        risk_notes="回撤风险",
        source_run_id="run-ai",
    )
