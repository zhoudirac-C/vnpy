import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


FEEDBACK_SCHEMA: str = """
CREATE TABLE IF NOT EXISTS agent_performance_feedback (
    vt_symbol TEXT NOT NULL,
    as_of TIMESTAMPTZ NOT NULL,
    portfolio_return DOUBLE PRECISION NOT NULL,
    benchmark_return DOUBLE PRECISION NOT NULL,
    alpha DOUBLE PRECISION NOT NULL,
    turnover_rate DOUBLE PRECISION NOT NULL,
    max_drawdown DOUBLE PRECISION NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (vt_symbol, as_of)
);

CREATE TABLE IF NOT EXISTS agent_trade_feedback (
    run_id TEXT NOT NULL,
    vt_symbol TEXT NOT NULL,
    trade_date DATE NOT NULL,
    action TEXT NOT NULL,
    filled_volume DOUBLE PRECISION NOT NULL,
    avg_price DOUBLE PRECISION NOT NULL,
    slippage DOUBLE PRECISION NOT NULL,
    pnl DOUBLE PRECISION NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (run_id, vt_symbol, trade_date)
);
"""


INSERT_PERFORMANCE_FEEDBACK_SQL: str = """
INSERT INTO agent_performance_feedback (
    vt_symbol,
    as_of,
    portfolio_return,
    benchmark_return,
    alpha,
    turnover_rate,
    max_drawdown,
    payload
) VALUES (
    %(vt_symbol)s,
    %(as_of)s,
    %(portfolio_return)s,
    %(benchmark_return)s,
    %(alpha)s,
    %(turnover_rate)s,
    %(max_drawdown)s,
    %(payload)s
)
ON CONFLICT (vt_symbol, as_of)
DO UPDATE SET
    portfolio_return = EXCLUDED.portfolio_return,
    benchmark_return = EXCLUDED.benchmark_return,
    alpha = EXCLUDED.alpha,
    turnover_rate = EXCLUDED.turnover_rate,
    max_drawdown = EXCLUDED.max_drawdown,
    payload = EXCLUDED.payload;
"""


INSERT_TRADE_FEEDBACK_SQL: str = """
INSERT INTO agent_trade_feedback (
    run_id,
    vt_symbol,
    trade_date,
    action,
    filled_volume,
    avg_price,
    slippage,
    pnl,
    payload
) VALUES (
    %(run_id)s,
    %(vt_symbol)s,
    %(trade_date)s,
    %(action)s,
    %(filled_volume)s,
    %(avg_price)s,
    %(slippage)s,
    %(pnl)s,
    %(payload)s
)
ON CONFLICT (run_id, vt_symbol, trade_date)
DO UPDATE SET
    action = EXCLUDED.action,
    filled_volume = EXCLUDED.filled_volume,
    avg_price = EXCLUDED.avg_price,
    slippage = EXCLUDED.slippage,
    pnl = EXCLUDED.pnl,
    payload = EXCLUDED.payload;
"""


@dataclass(frozen=True)
class PerformanceFeedback:
    """
    Symbol-level performance feedback against an A-share benchmark.
    """

    vt_symbol: str
    as_of: datetime
    portfolio_return: float
    benchmark_return: float
    alpha: float
    turnover_rate: float
    max_drawdown: float
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TradeFeedback:
    """
    Executed trade feedback linked to a TradingAgents source run.
    """

    run_id: str
    vt_symbol: str
    trade_date: str
    action: str
    filled_volume: float
    avg_price: float
    slippage: float
    pnl: float
    payload: dict[str, Any] = field(default_factory=dict)


class Cursor(Protocol):
    """
    Minimal DB-API cursor protocol.
    """

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> None:
        pass

    def close(self) -> None:
        pass


class Connection(Protocol):
    """
    Minimal DB-API connection protocol.
    """

    def cursor(self) -> Cursor:
        pass

    def commit(self) -> None:
        pass


class PostgresFeedbackStorage:
    """
    PostgreSQL storage for agent performance and trade feedback.
    """

    def __init__(self, connection: Connection) -> None:
        """"""
        self.connection: Connection = connection

    def create_schema(self) -> None:
        """
        Create feedback tables.
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(FEEDBACK_SCHEMA)
            self.connection.commit()
        finally:
            cursor.close()

    def save_performance_feedback(self, feedback: PerformanceFeedback) -> None:
        """
        Persist one performance feedback snapshot.
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(INSERT_PERFORMANCE_FEEDBACK_SQL, _performance_params(feedback))
            self.connection.commit()
        finally:
            cursor.close()

    def save_trade_feedback(self, feedback: TradeFeedback) -> None:
        """
        Persist one executed trade feedback row.
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(INSERT_TRADE_FEEDBACK_SQL, _trade_params(feedback))
            self.connection.commit()
        finally:
            cursor.close()


def build_feedback_context(
    performance: list[PerformanceFeedback],
    trades: list[TradeFeedback],
) -> dict[str, Any]:
    """
    Build context for the next TradingAgents reflection run.
    """
    return {
        "performance": [_performance_to_context(item) for item in performance],
        "trades": [_trade_to_context(item) for item in trades],
    }


def _performance_params(feedback: PerformanceFeedback) -> dict[str, Any]:
    """"""
    return {
        "vt_symbol": feedback.vt_symbol,
        "as_of": feedback.as_of,
        "portfolio_return": feedback.portfolio_return,
        "benchmark_return": feedback.benchmark_return,
        "alpha": feedback.alpha,
        "turnover_rate": feedback.turnover_rate,
        "max_drawdown": feedback.max_drawdown,
        "payload": _json_dumps(feedback.payload),
    }


def _trade_params(feedback: TradeFeedback) -> dict[str, Any]:
    """"""
    return {
        "run_id": feedback.run_id,
        "vt_symbol": feedback.vt_symbol,
        "trade_date": feedback.trade_date,
        "action": feedback.action,
        "filled_volume": feedback.filled_volume,
        "avg_price": feedback.avg_price,
        "slippage": feedback.slippage,
        "pnl": feedback.pnl,
        "payload": _json_dumps(feedback.payload),
    }


def _performance_to_context(feedback: PerformanceFeedback) -> dict[str, Any]:
    """"""
    return {
        "vt_symbol": feedback.vt_symbol,
        "as_of": feedback.as_of.isoformat(),
        "portfolio_return": feedback.portfolio_return,
        "benchmark_return": feedback.benchmark_return,
        "benchmark_alpha": feedback.alpha,
        "turnover_rate": feedback.turnover_rate,
        "max_drawdown": feedback.max_drawdown,
        "payload": feedback.payload,
    }


def _trade_to_context(feedback: TradeFeedback) -> dict[str, Any]:
    """"""
    return {
        "source_run_id": feedback.run_id,
        "vt_symbol": feedback.vt_symbol,
        "trade_date": feedback.trade_date,
        "action": feedback.action,
        "filled_volume": feedback.filled_volume,
        "avg_price": feedback.avg_price,
        "slippage": feedback.slippage,
        "pnl": feedback.pnl,
        "payload": feedback.payload,
    }


def _json_dumps(data: Any) -> str:
    """"""
    return json.dumps(data, ensure_ascii=False, sort_keys=True)
