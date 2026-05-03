from datetime import datetime

import pytest

from vnpy_tradingagents.research import ResearchSnapshot
from vnpy_tradingagents.runtime import TradingAgentsMode, TradingAgentsRuntimeController
from vnpy_tradingagents.signals import PortfolioIntent
from vnpy_tradingagents.worker import TradingAgentsWorkerResponse


def test_batch_long_horizon_job_continues_after_symbol_failure():
    """Batch job should keep successful symbols traceable when one symbol fails."""
    from vnpy_tradingagents.batch import BatchLongHorizonAgentJob

    runtime = TradingAgentsRuntimeController()
    runtime.enable(mode=TradingAgentsMode.REPORT_ONLY)
    worker = SelectiveWorker(failing_symbols={"000001.SZSE"})
    storage = FakeAgentStorage()
    reader = FakeResearchSnapshotReader()
    job = BatchLongHorizonAgentJob(
        runtime=runtime,
        worker=worker,
        storage=storage,
        snapshot_reader=reader,
        batch_id_factory=lambda: "batch-1",
    )

    summary = job.run(["600519.SSE", "000001.SZSE", "300750.SZSE"], "2024-01-03")

    assert summary.batch_run_id == "batch-1"
    assert summary.total == 3
    assert summary.succeeded == 2
    assert summary.failed == 1
    assert sorted(summary.failures) == ["000001.SZSE"]
    assert [rating.vt_symbol for rating in summary.ratings] == ["600519.SSE", "300750.SZSE"]
    assert [intent.vt_symbol for intent in summary.intents] == ["600519.SSE", "300750.SZSE"]
    assert worker.requests[0].run_id == "batch-1:2024-01-03:600519.SSE"
    assert worker.requests[0].context["batch"]["batch_run_id"] == "batch-1"
    assert storage.saved == [(request, response) for request, response in worker.saved_pairs]


def test_long_scheduler_is_idempotent_for_same_trade_date_slot():
    """Long scheduler should avoid duplicate active intents unless force rerun is requested."""
    from vnpy_tradingagents.batch import BatchRunSummary
    from vnpy_tradingagents.long_scheduler import (
        InMemoryLongRunRegistry,
        LongHorizonSchedule,
        LongHorizonScheduler,
    )

    job = CountingBatchJob()
    registry = InMemoryLongRunRegistry()
    scheduler = LongHorizonScheduler(job=job, registry=registry)

    assert LongHorizonSchedule.default().slot_names == ("pre_open", "after_close", "weekend")

    first = scheduler.run_slot("after_close", ["600519.SSE"], "2024-01-03")
    second = scheduler.run_slot("after_close", ["600519.SSE"], "2024-01-03")
    forced = scheduler.run_slot("after_close", ["600519.SSE"], "2024-01-03", force=True)

    assert isinstance(first.summary, BatchRunSummary)
    assert first.skipped is False
    assert second.skipped is True
    assert second.summary is first.summary
    assert forced.skipped is False
    assert job.calls == 2
    assert registry.active_intent_keys == {("600519.SSE", "2024-01-03")}


def test_portfolio_constraints_block_invalid_buys_and_keep_weight_intents_only():
    """Portfolio constraints should approve only target-weight intents within limits."""
    from vnpy_tradingagents.portfolio_constraints import (
        PortfolioConstraintConfig,
        PortfolioConstraintEngine,
        PortfolioState,
    )

    engine = PortfolioConstraintEngine(
        PortfolioConstraintConfig(
            max_single_weight=0.20,
            max_sector_weight=0.40,
            max_turnover_rate=0.30,
            min_cash_weight=0.05,
            max_drawdown=0.20,
        )
    )
    state = PortfolioState(
        current_weights={"600519.SSE": 0.05},
        sector_weights={"白酒": 0.35},
        symbol_sectors={"600519.SSE": "白酒", "300750.SZSE": "新能源"},
        cash_weight=0.20,
        turnover_rate=0.04,
        drawdown=0.10,
    )
    intents = [
        make_intent("600519.SSE", action="buy", target_weight_hint=0.25),
        make_intent("300750.SZSE", action="buy", target_weight_hint=0.10),
    ]

    result = engine.apply(intents, state)

    assert [intent.vt_symbol for intent in result.approved_intents] == ["300750.SZSE"]
    assert result.violations[0].vt_symbol == "600519.SSE"
    assert result.violations[0].rule == "max_single_weight"
    assert not hasattr(result.approved_intents[0], "price")
    assert result.approved_intents[0].target_weight_hint == 0.10


def test_performance_feedback_schema_storage_and_context_builder():
    """Feedback tables should persist performance/trades and rebuild next-run context."""
    from vnpy_tradingagents.performance_feedback import (
        FEEDBACK_SCHEMA,
        PerformanceFeedback,
        PostgresFeedbackStorage,
        TradeFeedback,
        build_feedback_context,
    )

    assert "CREATE TABLE IF NOT EXISTS agent_performance_feedback" in FEEDBACK_SCHEMA
    assert "CREATE TABLE IF NOT EXISTS agent_trade_feedback" in FEEDBACK_SCHEMA

    connection = FakeConnection()
    storage = PostgresFeedbackStorage(connection)
    performance = PerformanceFeedback(
        vt_symbol="600519.SSE",
        as_of=datetime(2024, 1, 4),
        portfolio_return=0.03,
        benchmark_return=0.01,
        alpha=0.02,
        turnover_rate=0.12,
        max_drawdown=0.04,
        payload={"benchmark": "沪深300"},
    )
    trade = TradeFeedback(
        run_id="batch-1:2024-01-03:600519.SSE",
        vt_symbol="600519.SSE",
        trade_date="2024-01-04",
        action="buy",
        filled_volume=100,
        avg_price=1650,
        slippage=0.001,
        pnl=230,
        payload={"order_id": "order-1"},
    )

    storage.save_performance_feedback(performance)
    storage.save_trade_feedback(trade)
    context = build_feedback_context([performance], [trade])

    executed_sql = "\n".join(sql for sql, _ in connection.cursor_obj.executed)
    assert "INSERT INTO agent_performance_feedback" in executed_sql
    assert "INSERT INTO agent_trade_feedback" in executed_sql
    assert connection.commits == 2
    assert context["performance"][0]["benchmark_alpha"] == 0.02
    assert context["trades"][0]["source_run_id"] == "batch-1:2024-01-03:600519.SSE"


def test_reflection_context_uses_ashare_benchmark_and_real_feedback():
    """Reflection inputs should use A-share benchmark alpha instead of SPY assumptions."""
    from vnpy_tradingagents.prompts import build_reflection_context, build_worker_system_prompt

    reflection = build_reflection_context(
        {
            "benchmark": {"name": "沪深300", "return": 0.01},
            "feedback": {
                "performance": [
                    {
                        "portfolio_return": 0.03,
                        "benchmark_return": 0.01,
                        "benchmark_alpha": 0.02,
                    }
                ],
                "trades": [{"source_run_id": "run-1", "pnl": 230}],
            },
        }
    )
    prompt = build_worker_system_prompt("long_horizon")

    assert reflection["benchmark"]["name"] == "沪深300"
    assert reflection["feedback"]["performance"][0]["benchmark_alpha"] == 0.02
    assert "A 股 benchmark alpha" in prompt
    assert "真实持仓绩效" in prompt
    assert "SPY" not in prompt


def test_portfolio_replay_summary_includes_enhanced_metrics():
    """Portfolio replay summary should expose turnover, exposure and drawdown metrics."""
    from vnpy_tradingagents.replay import PortfolioReplayEngine, PortfolioReplayStep
    from vnpy_tradingagents.risk import OrderIntent, PreOrderDecisionService, RiskRuleSet
    from vnpy_tradingagents.signals import RatingSignal

    engine = PortfolioReplayEngine(
        decision_service=PreOrderDecisionService(
            rules=RiskRuleSet(max_order_value=100_000),
            audit_storage=FakeAuditStorage(),
        )
    )
    steps = [
        PortfolioReplayStep(
            at=datetime(2024, 1, 3, 15, 30),
            rating=RatingSignal("600519.SSE", "Buy", 0.8, "rating-1"),
            intent=make_intent("600519.SSE", "buy", 0.15),
            order_intent=OrderIntent("600519.SSE", "buy", 100, 10),
            current_weight=0.05,
            sector="白酒",
            equity=1_000_000,
        ),
        PortfolioReplayStep(
            at=datetime(2024, 1, 4, 15, 30),
            rating=RatingSignal("300750.SZSE", "Buy", 0.7, "rating-2"),
            intent=make_intent("300750.SZSE", "buy", 0.10),
            order_intent=OrderIntent("300750.SZSE", "buy", 100, 10),
            current_weight=0.02,
            sector="新能源",
            equity=980_000,
        ),
    ]

    summary = engine.run(steps)

    assert summary.turnover_rate == pytest.approx(0.18)
    assert summary.target_weight_deviation == pytest.approx(0.09)
    assert summary.sector_exposure == {"白酒": 0.15, "新能源": 0.10}
    assert summary.max_drawdown == pytest.approx(0.02)


def make_intent(
    vt_symbol: str,
    action: str,
    target_weight_hint: float | None,
) -> PortfolioIntent:
    """Create a portfolio intent fixture."""
    return PortfolioIntent(
        vt_symbol=vt_symbol,
        trade_date="2024-01-03",
        action=action,
        target_weight_hint=target_weight_hint,
        holding_period_hint="20d",
        risk_notes="测试",
        source_run_id=f"run-{vt_symbol}",
    )


class SelectiveWorker:
    """Worker fake that can fail selected symbols."""

    def __init__(self, failing_symbols: set[str] | None = None) -> None:
        self.failing_symbols = failing_symbols or set()
        self.requests = []
        self.saved_pairs = []

    def run(self, request):
        self.requests.append(request)
        if request.vt_symbol in self.failing_symbols:
            raise RuntimeError("worker failed")

        response = TradingAgentsWorkerResponse(
            run_id=request.run_id,
            vt_symbol=request.vt_symbol,
            rating="Buy",
            confidence=0.8,
            report="batch report",
            raw_state={"batch_run_id": request.context["batch"]["batch_run_id"]},
            action="buy",
            target_weight_hint=0.10,
            holding_period_hint="20d",
            risk_notes="batch risk checked",
        )
        self.saved_pairs.append((request, response))
        return response


class FakeResearchSnapshotReader:
    """Research snapshot reader fake."""

    def load_snapshot(self, vt_symbol: str, trade_date: str) -> ResearchSnapshot:
        return ResearchSnapshot(
            vt_symbol=vt_symbol,
            trade_date=trade_date,
            market={"daily": {"latest_close": 10}},
            fundamentals={},
            valuation={},
            industry={},
            benchmark={"name": "沪深300"},
            news_events=[],
            portfolio_state={},
        )


class FakeAgentStorage:
    """Fake storage that records worker result persistence."""

    def __init__(self) -> None:
        self.saved = []

    def save_worker_result(self, request, response):
        self.saved.append((request, response))


class FakeAuditStorage:
    """Fake audit storage for replay tests."""

    def __init__(self) -> None:
        self.saved = []

    def save_decision(self, record):
        self.saved.append(record)


class CountingBatchJob:
    """Batch job fake used by the scheduler."""

    def __init__(self) -> None:
        self.calls = 0

    def run(self, symbols, trade_date, batch_run_id=None):
        from vnpy_tradingagents.batch import BatchRunSummary

        self.calls += 1
        run_id = batch_run_id or f"batch-{self.calls}"
        return BatchRunSummary(
            batch_run_id=run_id,
            trade_date=trade_date,
            total=len(symbols),
            succeeded=len(symbols),
            failed=0,
            ratings=[],
            intents=[make_intent(symbols[0], "buy", 0.10)] if symbols else [],
            failures={},
        )


class FakeCursor:
    """Tiny DB-API cursor fake."""

    def __init__(self) -> None:
        self.executed = []

    def execute(self, sql, params=None) -> None:
        self.executed.append((sql, params or {}))

    def close(self) -> None:
        return


class FakeConnection:
    """Tiny DB-API connection fake."""

    def __init__(self) -> None:
        self.cursor_obj = FakeCursor()
        self.commits = 0

    def cursor(self):
        return self.cursor_obj

    def commit(self) -> None:
        self.commits += 1
