import json
from collections.abc import Mapping
from typing import Any, Protocol

from .output_validation import validate_worker_response
from .signals import IntradayAdvice, PortfolioIntent, RatingSignal
from .worker import TradingAgentsWorkerRequest, TradingAgentsWorkerResponse


TRADINGAGENTS_SCHEMA: str = """
CREATE TABLE IF NOT EXISTS agent_run (
    run_id TEXT PRIMARY KEY,
    vt_symbol TEXT NOT NULL,
    trade_date DATE NOT NULL,
    mode TEXT NOT NULL,
    model_provider TEXT,
    model_name TEXT,
    prompt_version TEXT,
    snapshot_ids JSONB,
    context JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_report (
    run_id TEXT PRIMARY KEY,
    vt_symbol TEXT NOT NULL,
    report TEXT NOT NULL,
    raw_state JSONB NOT NULL,
    error_message TEXT,
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

CREATE TABLE IF NOT EXISTS intraday_advice (
    run_id TEXT PRIMARY KEY,
    vt_symbol TEXT NOT NULL,
    action TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    valid_until TIMESTAMPTZ NOT NULL,
    generated_at TIMESTAMPTZ DEFAULT now()
);
"""


INSERT_AGENT_RUN_SQL: str = """
INSERT INTO agent_run (
    run_id,
    vt_symbol,
    trade_date,
    mode,
    model_provider,
    model_name,
    prompt_version,
    snapshot_ids,
    context
) VALUES (
    %(run_id)s,
    %(vt_symbol)s,
    %(trade_date)s,
    %(mode)s,
    %(model_provider)s,
    %(model_name)s,
    %(prompt_version)s,
    %(snapshot_ids)s,
    %(context)s
)
ON CONFLICT (run_id)
DO UPDATE SET
    vt_symbol = EXCLUDED.vt_symbol,
    trade_date = EXCLUDED.trade_date,
    mode = EXCLUDED.mode,
    model_provider = EXCLUDED.model_provider,
    model_name = EXCLUDED.model_name,
    prompt_version = EXCLUDED.prompt_version,
    snapshot_ids = EXCLUDED.snapshot_ids,
    context = EXCLUDED.context;
"""


INSERT_AGENT_REPORT_SQL: str = """
INSERT INTO agent_report (
    run_id,
    vt_symbol,
    report,
    raw_state,
    error_message
) VALUES (
    %(run_id)s,
    %(vt_symbol)s,
    %(report)s,
    %(raw_state)s,
    %(error_message)s
)
ON CONFLICT (run_id)
DO UPDATE SET
    vt_symbol = EXCLUDED.vt_symbol,
    report = EXCLUDED.report,
    raw_state = EXCLUDED.raw_state,
    error_message = EXCLUDED.error_message;
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


INSERT_INTRADAY_ADVICE_SQL: str = """
INSERT INTO intraday_advice (
    run_id,
    vt_symbol,
    action,
    confidence,
    valid_until
) VALUES (
    %(run_id)s,
    %(vt_symbol)s,
    %(action)s,
    %(confidence)s,
    %(valid_until)s
)
ON CONFLICT (run_id)
DO UPDATE SET
    vt_symbol = EXCLUDED.vt_symbol,
    action = EXCLUDED.action,
    confidence = EXCLUDED.confidence,
    valid_until = EXCLUDED.valid_until;
"""


SELECT_LATEST_INTRADAY_ADVICE_SQL: str = """
SELECT
    vt_symbol,
    action,
    confidence,
    valid_until,
    run_id
FROM intraday_advice
WHERE vt_symbol = %(vt_symbol)s
  AND valid_until >= %(at)s
ORDER BY generated_at DESC
LIMIT 1;
"""


SELECT_LATEST_RATING_SIGNAL_SQL: str = """
SELECT
    vt_symbol,
    rating,
    confidence,
    run_id
FROM rating_signal
WHERE vt_symbol = %(vt_symbol)s
  AND trade_date <= %(trade_date)s
ORDER BY trade_date DESC, created_at DESC
LIMIT 1;
"""


SELECT_PORTFOLIO_INTENTS_SQL: str = """
SELECT DISTINCT ON (vt_symbol)
    vt_symbol,
    trade_date,
    action,
    target_weight_hint,
    holding_period_hint,
    risk_notes,
    run_id
FROM trade_intent
WHERE trade_date = %(trade_date)s
ORDER BY vt_symbol, created_at DESC;
"""


class Cursor(Protocol):
    """
    Minimal DB-API cursor protocol.
    """

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> None:
        pass

    def fetchone(self) -> Mapping[str, Any] | None:
        pass

    def fetchall(self) -> list[Mapping[str, Any]]:
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
        response = validate_worker_response(response)
        cursor = self.connection.cursor()
        try:
            cursor.execute(INSERT_AGENT_RUN_SQL, _agent_run_params(request, response))
            cursor.execute(INSERT_AGENT_REPORT_SQL, _agent_report_params(response))
            cursor.execute(INSERT_RATING_SIGNAL_SQL, _rating_signal_params(request, response))
            cursor.execute(INSERT_TRADE_INTENT_SQL, _trade_intent_params(request, response))
            self.connection.commit()
        finally:
            cursor.close()

    def save_intraday_advice(self, advice: IntradayAdvice) -> None:
        """
        Persist short-lived intraday advice for strategy-side reads.
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(INSERT_INTRADAY_ADVICE_SQL, _intraday_advice_params(advice))
            self.connection.commit()
        finally:
            cursor.close()


class PostgresSignalReader:
    """
    PostgreSQL reader for TradingAgents signals consumed by strategies.
    """

    def __init__(self, connection: Connection) -> None:
        """"""
        self.connection: Connection = connection

    def load_latest_intraday_advice(
        self,
        vt_symbol: str,
        at: Any,
    ) -> IntradayAdvice | None:
        """
        Load the latest not-yet-expired intraday advice for a symbol.
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                SELECT_LATEST_INTRADAY_ADVICE_SQL,
                {
                    "vt_symbol": vt_symbol,
                    "at": at,
                },
            )
            row = cursor.fetchone()
            if not row:
                return None

            return _intraday_advice_from_row(row)
        finally:
            cursor.close()

    def load_latest_rating_signal(
        self,
        vt_symbol: str,
        trade_date: str,
    ) -> RatingSignal | None:
        """
        Load the latest long-horizon rating signal at or before trade_date.
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                SELECT_LATEST_RATING_SIGNAL_SQL,
                {
                    "vt_symbol": vt_symbol,
                    "trade_date": trade_date,
                },
            )
            row = cursor.fetchone()
            if not row:
                return None

            return _rating_signal_from_row(row)
        finally:
            cursor.close()

    def load_portfolio_intents(self, trade_date: str) -> list[PortfolioIntent]:
        """
        Load portfolio intents generated for a trade date.
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                SELECT_PORTFOLIO_INTENTS_SQL,
                {
                    "trade_date": trade_date,
                },
            )
            return [_portfolio_intent_from_row(row) for row in cursor.fetchall()]
        finally:
            cursor.close()


def _json_dumps(data: Any) -> str:
    """
    Serialize JSON payloads in a stable, readable format.
    """
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def _agent_run_params(
    request: TradingAgentsWorkerRequest,
    response: TradingAgentsWorkerResponse,
) -> dict[str, Any]:
    """"""
    metadata: dict[str, Any] = _worker_metadata(request, response)
    return {
        "run_id": request.run_id,
        "vt_symbol": request.vt_symbol,
        "trade_date": request.trade_date,
        "mode": request.mode,
        "model_provider": metadata["model_provider"],
        "model_name": metadata["model_name"],
        "prompt_version": metadata["prompt_version"],
        "snapshot_ids": _json_dumps(metadata["snapshot_ids"]),
        "context": _json_dumps(request.context),
    }


def _agent_report_params(response: TradingAgentsWorkerResponse) -> dict[str, Any]:
    """"""
    return {
        "run_id": response.run_id,
        "vt_symbol": response.vt_symbol,
        "report": response.report,
        "raw_state": _json_dumps(response.raw_state),
        "error_message": response.raw_state.get("error_message"),
    }


def _worker_metadata(
    request: TradingAgentsWorkerRequest,
    response: TradingAgentsWorkerResponse,
) -> dict[str, Any]:
    """
    Extract model/prompt/snapshot metadata for reproducible worker runs.
    """
    raw_state: dict[str, Any] = response.raw_state
    snapshot_ids: Any = raw_state.get("snapshot_ids") or request.context.get("snapshot_ids") or []
    if not isinstance(snapshot_ids, list):
        snapshot_ids = [snapshot_ids]

    return {
        "model_provider": raw_state.get("model_provider"),
        "model_name": raw_state.get("model_name"),
        "prompt_version": raw_state.get("prompt_version"),
        "snapshot_ids": snapshot_ids,
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


def _intraday_advice_params(advice: IntradayAdvice) -> dict[str, Any]:
    """"""
    return {
        "run_id": advice.source_run_id,
        "vt_symbol": advice.vt_symbol,
        "action": advice.action,
        "confidence": advice.confidence,
        "valid_until": advice.valid_until,
    }


def _intraday_advice_from_row(row: Mapping[str, Any]) -> IntradayAdvice:
    """"""
    return IntradayAdvice(
        vt_symbol=row["vt_symbol"],
        action=row["action"],
        confidence=row["confidence"],
        valid_until=row["valid_until"],
        source_run_id=row["run_id"],
    )


def _rating_signal_from_row(row: Mapping[str, Any]) -> RatingSignal:
    """"""
    return RatingSignal(
        vt_symbol=row["vt_symbol"],
        rating=row["rating"],
        confidence=row["confidence"],
        source_run_id=row["run_id"],
    )


def _portfolio_intent_from_row(row: Mapping[str, Any]) -> PortfolioIntent:
    """"""
    return PortfolioIntent(
        vt_symbol=row["vt_symbol"],
        trade_date=str(row["trade_date"]),
        action=row["action"],
        target_weight_hint=row["target_weight_hint"],
        holding_period_hint=row["holding_period_hint"],
        risk_notes=row["risk_notes"],
        source_run_id=row["run_id"],
    )
