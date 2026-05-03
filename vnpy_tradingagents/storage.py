import json
from typing import Any, Protocol

from .worker import TradingAgentsWorkerRequest, TradingAgentsWorkerResponse


TRADINGAGENTS_SCHEMA: str = """
CREATE TABLE IF NOT EXISTS agent_run (
    run_id TEXT PRIMARY KEY,
    vt_symbol TEXT NOT NULL,
    trade_date DATE NOT NULL,
    mode TEXT NOT NULL,
    context JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_report (
    run_id TEXT PRIMARY KEY,
    vt_symbol TEXT NOT NULL,
    report TEXT NOT NULL,
    raw_state JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rating_signal (
    run_id TEXT PRIMARY KEY,
    vt_symbol TEXT NOT NULL,
    trade_date DATE NOT NULL,
    rating TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS trade_intent (
    run_id TEXT PRIMARY KEY,
    vt_symbol TEXT NOT NULL,
    trade_date DATE NOT NULL,
    action TEXT NOT NULL,
    target_weight_hint DOUBLE PRECISION,
    holding_period_hint TEXT,
    risk_notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);
"""


INSERT_AGENT_RUN_SQL: str = """
INSERT INTO agent_run (
    run_id,
    vt_symbol,
    trade_date,
    mode,
    context
) VALUES (
    %(run_id)s,
    %(vt_symbol)s,
    %(trade_date)s,
    %(mode)s,
    %(context)s
)
ON CONFLICT (run_id)
DO UPDATE SET
    vt_symbol = EXCLUDED.vt_symbol,
    trade_date = EXCLUDED.trade_date,
    mode = EXCLUDED.mode,
    context = EXCLUDED.context;
"""


INSERT_AGENT_REPORT_SQL: str = """
INSERT INTO agent_report (
    run_id,
    vt_symbol,
    report,
    raw_state
) VALUES (
    %(run_id)s,
    %(vt_symbol)s,
    %(report)s,
    %(raw_state)s
)
ON CONFLICT (run_id)
DO UPDATE SET
    vt_symbol = EXCLUDED.vt_symbol,
    report = EXCLUDED.report,
    raw_state = EXCLUDED.raw_state;
"""


INSERT_RATING_SIGNAL_SQL: str = """
INSERT INTO rating_signal (
    run_id,
    vt_symbol,
    trade_date,
    rating,
    confidence
) VALUES (
    %(run_id)s,
    %(vt_symbol)s,
    %(trade_date)s,
    %(rating)s,
    %(confidence)s
)
ON CONFLICT (run_id)
DO UPDATE SET
    vt_symbol = EXCLUDED.vt_symbol,
    trade_date = EXCLUDED.trade_date,
    rating = EXCLUDED.rating,
    confidence = EXCLUDED.confidence;
"""


INSERT_TRADE_INTENT_SQL: str = """
INSERT INTO trade_intent (
    run_id,
    vt_symbol,
    trade_date,
    action,
    target_weight_hint,
    holding_period_hint,
    risk_notes
) VALUES (
    %(run_id)s,
    %(vt_symbol)s,
    %(trade_date)s,
    %(action)s,
    %(target_weight_hint)s,
    %(holding_period_hint)s,
    %(risk_notes)s
)
ON CONFLICT (run_id)
DO UPDATE SET
    vt_symbol = EXCLUDED.vt_symbol,
    trade_date = EXCLUDED.trade_date,
    action = EXCLUDED.action,
    target_weight_hint = EXCLUDED.target_weight_hint,
    holding_period_hint = EXCLUDED.holding_period_hint,
    risk_notes = EXCLUDED.risk_notes;
"""


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


class PostgresAgentStorage:
    """
    PostgreSQL storage for TradingAgents run outputs.
    """

    def __init__(self, connection: Connection) -> None:
        """"""
        self.connection: Connection = connection

    def create_schema(self) -> None:
        """
        Create TradingAgents output tables.
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(TRADINGAGENTS_SCHEMA)
            self.connection.commit()
        finally:
            cursor.close()

    def save_worker_result(
        self,
        request: TradingAgentsWorkerRequest,
        response: TradingAgentsWorkerResponse,
    ) -> None:
        """
        Persist a worker response into auditable signal tables.
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(INSERT_AGENT_RUN_SQL, _agent_run_params(request))
            cursor.execute(INSERT_AGENT_REPORT_SQL, _agent_report_params(response))
            cursor.execute(INSERT_RATING_SIGNAL_SQL, _rating_signal_params(request, response))
            cursor.execute(INSERT_TRADE_INTENT_SQL, _trade_intent_params(request, response))
            self.connection.commit()
        finally:
            cursor.close()


def _json_dumps(data: dict[str, Any]) -> str:
    """
    Serialize JSON payloads in a stable, readable format.
    """
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def _agent_run_params(request: TradingAgentsWorkerRequest) -> dict[str, Any]:
    """"""
    return {
        "run_id": request.run_id,
        "vt_symbol": request.vt_symbol,
        "trade_date": request.trade_date,
        "mode": request.mode,
        "context": _json_dumps(request.context),
    }


def _agent_report_params(response: TradingAgentsWorkerResponse) -> dict[str, Any]:
    """"""
    return {
        "run_id": response.run_id,
        "vt_symbol": response.vt_symbol,
        "report": response.report,
        "raw_state": _json_dumps(response.raw_state),
    }


def _rating_signal_params(
    request: TradingAgentsWorkerRequest,
    response: TradingAgentsWorkerResponse,
) -> dict[str, Any]:
    """"""
    return {
        "run_id": response.run_id,
        "vt_symbol": response.vt_symbol,
        "trade_date": request.trade_date,
        "rating": response.rating,
        "confidence": response.confidence,
    }


def _trade_intent_params(
    request: TradingAgentsWorkerRequest,
    response: TradingAgentsWorkerResponse,
) -> dict[str, Any]:
    """"""
    return {
        "run_id": response.run_id,
        "vt_symbol": response.vt_symbol,
        "trade_date": request.trade_date,
        "action": response.action,
        "target_weight_hint": response.target_weight_hint,
        "holding_period_hint": response.holding_period_hint,
        "risk_notes": response.risk_notes,
    }
