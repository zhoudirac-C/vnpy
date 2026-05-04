from datetime import datetime

from vnpy_tradingagents.toolkit import MarketDataToolkit, SnapshotQuery
from vnpy_tradingagents.worker import TradingAgentsWorkerRequest


def test_market_data_toolkit_builds_context_from_snapshot_reader_only():
    """MarketDataToolkit should build agent context from snapshot reader data."""
    reader = FakeSnapshotReader()
    toolkit = MarketDataToolkit(reader)
    query = SnapshotQuery(
        vt_symbol="600519.SSE",
        start=datetime(2024, 1, 1),
        end=datetime(2024, 1, 3),
    )

    context = toolkit.build_context(query)

    assert reader.calls == [
        ("bars", "600519.SSE"),
        ("snapshot", "fundamentals", "600519.SSE"),
        ("snapshot", "valuation", "600519.SSE"),
        ("snapshot", "industry", "600519.SSE"),
        ("snapshot", "benchmark", "600519.SSE"),
        ("snapshot", "portfolio", "600519.SSE"),
        ("snapshot", "alpha_factor", "600519.SSE"),
        ("snapshot", "news", "600519.SSE"),
        ("snapshot", "sentiment", "600519.SSE"),
    ]
    assert context["vt_symbol"] == "600519.SSE"
    assert context["market"]["bars"][0]["close"] == 1688
    assert context["market"]["indicators"]["latest_close"] == 1688
    assert context["fundamentals"]["pe"] == 25.2
    assert context["valuation"]["pb"] == 8.1
    assert context["industry"]["name"] == "白酒"
    assert context["benchmark"]["name"] == "沪深300"
    assert context["alpha_factors"]["alpha101_001"] == 0.32
    assert "news" in context["degraded_sources"]


def test_worker_request_keeps_context_separate_from_runtime_mode():
    """Worker request should carry context and runtime mode without provider details."""
    request = TradingAgentsWorkerRequest(
        run_id="run-1",
        vt_symbol="600519.SSE",
        trade_date="2024-01-03",
        mode="report_only",
        context={"market": {"bars": []}},
    )

    assert request.run_id == "run-1"
    assert request.mode == "report_only"
    assert "provider" not in request.context


class FakeSnapshotReader:
    """Snapshot reader fake that records calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str] | tuple[str, str, str]] = []

    def load_bar_snapshots(
        self,
        vt_symbol: str,
        start: datetime,
        end: datetime,
    ) -> list[dict]:
        self.calls.append(("bars", vt_symbol))
        return [{"datetime": "2024-01-03", "close": 1688}]

    def load_latest_snapshot(
        self,
        snapshot_type: str,
        vt_symbol: str,
        as_of: datetime,
    ) -> dict | None:
        self.calls.append(("snapshot", snapshot_type, vt_symbol))
        snapshots = {
            "fundamentals": {"pe": 25.2},
            "valuation": {"pb": 8.1},
            "industry": {"name": "白酒"},
            "news": None,
            "sentiment": {"score": 0.1},
            "benchmark": {"name": "沪深300"},
            "portfolio": {"position": 0},
            "alpha_factor": {"alpha101_001": 0.32},
        }
        return snapshots[snapshot_type]
