from datetime import datetime

from vnpy_tradingagents import IntradayAdvice, PortfolioIntent
from vnpy_tradingagents.storage import PostgresAgentStorage, PostgresSignalReader, TRADINGAGENTS_SCHEMA


def test_schema_contains_intraday_advice_table():
    """TradingAgents schema should persist short-lived intraday advice."""
    assert "CREATE TABLE IF NOT EXISTS intraday_advice" in TRADINGAGENTS_SCHEMA


def test_agent_storage_saves_intraday_advice():
    """PostgresAgentStorage should persist intraday advice separately from long-term intent."""
    connection = FakeConnection()
    storage = PostgresAgentStorage(connection)
    advice = make_advice()

    storage.save_intraday_advice(advice)

    executed_sql = [sql for sql, _ in connection.cursor_obj.executed]
    executed_params = [params for _, params in connection.cursor_obj.executed]
    assert connection.committed
    assert any("INSERT INTO intraday_advice" in sql for sql in executed_sql)
    assert executed_params[0]["run_id"] == "run-2"
    assert executed_params[0]["action"] == "buy_on_pullback"


def test_signal_reader_loads_latest_valid_intraday_advice():
    """PostgresSignalReader should only query currently valid intraday advice."""
    valid_until = datetime(2024, 1, 3, 10, 15)
    connection = FakeConnection(
        fetchone_result={
            "vt_symbol": "600519.SSE",
            "action": "buy_on_pullback",
            "confidence": 0.7,
            "valid_until": valid_until,
            "run_id": "run-2",
        }
    )
    reader = PostgresSignalReader(connection)

    advice = reader.load_latest_intraday_advice(
        vt_symbol="600519.SSE",
        at=datetime(2024, 1, 3, 10, 10),
    )

    assert advice == make_advice(valid_until=valid_until)
    sql, params = connection.cursor_obj.executed[0]
    assert "valid_until >= %(at)s" in sql
    assert params["vt_symbol"] == "600519.SSE"


def test_signal_reader_loads_latest_rating_signal():
    """PostgresSignalReader should provide long-horizon ratings for strategy filtering."""
    connection = FakeConnection(
        fetchone_result={
            "vt_symbol": "600519.SSE",
            "rating": "Buy",
            "confidence": 0.82,
            "run_id": "run-1",
        }
    )
    reader = PostgresSignalReader(connection)

    rating = reader.load_latest_rating_signal(
        vt_symbol="600519.SSE",
        trade_date="2024-01-03",
    )

    assert rating.vt_symbol == "600519.SSE"
    assert rating.rating == "Buy"
    assert rating.source_run_id == "run-1"


def test_signal_reader_loads_portfolio_intents():
    """PostgresSignalReader should expose long-horizon portfolio intent rows."""
    connection = FakeConnection(
        fetchall_result=[
            {
                "vt_symbol": "600519.SSE",
                "trade_date": "2024-01-03",
                "action": "buy",
                "target_weight_hint": 0.15,
                "holding_period_hint": "20d",
                "risk_notes": "回撤风险",
                "run_id": "run-1",
            }
        ]
    )
    reader = PostgresSignalReader(connection)

    intents = reader.load_portfolio_intents(trade_date="2024-01-03")

    assert intents == [
        PortfolioIntent(
            vt_symbol="600519.SSE",
            trade_date="2024-01-03",
            action="buy",
            target_weight_hint=0.15,
            holding_period_hint="20d",
            risk_notes="回撤风险",
            source_run_id="run-1",
        )
    ]


def make_advice(valid_until: datetime | None = None) -> IntradayAdvice:
    """Create an intraday advice fixture."""
    return IntradayAdvice(
        vt_symbol="600519.SSE",
        action="buy_on_pullback",
        confidence=0.7,
        valid_until=valid_until or datetime(2024, 1, 3, 10, 15),
        source_run_id="run-2",
    )


class FakeCursor:
    """Tiny DB-API cursor fake for signal reader unit tests."""

    def __init__(
        self,
        fetchone_result: dict | None = None,
        fetchall_result: list[dict] | None = None,
    ) -> None:
        self.executed: list[tuple[str, dict]] = []
        self.fetchone_result: dict | None = fetchone_result
        self.fetchall_result: list[dict] = fetchall_result or []

    def execute(self, sql: str, params: dict | None = None) -> None:
        self.executed.append((sql, params or {}))

    def fetchone(self) -> dict | None:
        return self.fetchone_result

    def fetchall(self) -> list[dict]:
        return self.fetchall_result

    def close(self) -> None:
        return


class FakeConnection:
    """Tiny DB-API connection fake for signal reader unit tests."""

    def __init__(
        self,
        fetchone_result: dict | None = None,
        fetchall_result: list[dict] | None = None,
    ) -> None:
        self.cursor_obj = FakeCursor(fetchone_result, fetchall_result)
        self.committed = False

    def cursor(self) -> FakeCursor:
        return self.cursor_obj

    def commit(self) -> None:
        self.committed = True
