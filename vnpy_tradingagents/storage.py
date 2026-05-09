import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from .output_validation import validate_worker_response
from .runtime import SignalStatus, TradingAgentsMode, TradingAgentsRuntimeState
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

CREATE TABLE IF NOT EXISTS ai_runtime_state (
    state_id TEXT PRIMARY KEY,
    enabled BOOLEAN NOT NULL,
    mode TEXT NOT NULL,
    live_enabled BOOLEAN NOT NULL,
    manual_takeover BOOLEAN NOT NULL,
    signal_status TEXT NOT NULL,
    disabled_reason TEXT,
    last_heartbeat_at TIMESTAMPTZ,
    last_successful_run_id TEXT,
    updated_at TIMESTAMPTZ DEFAULT now()
);
"""


AI_RUNTIME_STATE_MIGRATION_SQL: str = """
CREATE TABLE IF NOT EXISTS ai_runtime_state (
    state_id TEXT PRIMARY KEY,
    enabled BOOLEAN NOT NULL,
    mode TEXT NOT NULL,
    live_enabled BOOLEAN NOT NULL,
    manual_takeover BOOLEAN NOT NULL,
    signal_status TEXT NOT NULL,
    disabled_reason TEXT,
    last_heartbeat_at TIMESTAMPTZ,
    last_successful_run_id TEXT,
    updated_at TIMESTAMPTZ DEFAULT now()
);

INSERT INTO schema_version (
    namespace,
    version
) VALUES (
    'tradingagents',
    'p15'
)
ON CONFLICT (namespace)
DO UPDATE SET
    version = EXCLUDED.version,
    applied_at = now();
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


SELECT_LATEST_TRADE_INTENT_SQL: str = """
SELECT
    vt_symbol,
    trade_date,
    action,
    target_weight_hint,
    holding_period_hint,
    risk_notes,
    run_id
FROM trade_intent
WHERE vt_symbol = %(vt_symbol)s
  AND trade_date <= %(trade_date)s
ORDER BY trade_date DESC, created_at DESC
LIMIT 1;
"""


SELECT_ANALYSIS_HISTORY_SQL: str = """
SELECT
    ar.run_id,
    ar.vt_symbol,
    ar.trade_date,
    ar.mode,
    ar.model_provider,
    ar.model_name,
    ar.prompt_version,
    ar.snapshot_ids,
    ar.context,
    ar.created_at,
    rpt.report,
    rpt.raw_state,
    rpt.error_message,
    rs.rating,
    rs.confidence,
    ti.action,
    ti.target_weight_hint,
    ti.holding_period_hint,
    ti.risk_notes
FROM agent_run ar
LEFT JOIN agent_report rpt
    ON rpt.run_id = ar.run_id
LEFT JOIN rating_signal rs
    ON rs.run_id = ar.run_id
LEFT JOIN trade_intent ti
    ON ti.run_id = ar.run_id
WHERE (%(vt_symbol)s = '' OR ar.vt_symbol = %(vt_symbol)s)
ORDER BY ar.created_at DESC
LIMIT %(limit)s;
"""


UPSERT_AI_RUNTIME_STATE_SQL: str = """
INSERT INTO ai_runtime_state (
    state_id,
    enabled,
    mode,
    live_enabled,
    manual_takeover,
    signal_status,
    disabled_reason,
    last_heartbeat_at,
    last_successful_run_id
) VALUES (
    %(state_id)s,
    %(enabled)s,
    %(mode)s,
    %(live_enabled)s,
    %(manual_takeover)s,
    %(signal_status)s,
    %(disabled_reason)s,
    %(last_heartbeat_at)s,
    %(last_successful_run_id)s
)
ON CONFLICT (state_id)
DO UPDATE SET
    enabled = EXCLUDED.enabled,
    mode = EXCLUDED.mode,
    live_enabled = EXCLUDED.live_enabled,
    manual_takeover = EXCLUDED.manual_takeover,
    signal_status = EXCLUDED.signal_status,
    disabled_reason = EXCLUDED.disabled_reason,
    last_heartbeat_at = EXCLUDED.last_heartbeat_at,
    last_successful_run_id = EXCLUDED.last_successful_run_id,
    updated_at = now();
"""


SELECT_AI_RUNTIME_STATE_SQL: str = """
SELECT
    enabled,
    mode,
    live_enabled,
    manual_takeover,
    signal_status,
    disabled_reason,
    last_heartbeat_at,
    last_successful_run_id
FROM ai_runtime_state
WHERE state_id = %(state_id)s
LIMIT 1;
"""


DISABLE_AI_SIGNALS_SQL: str = """
UPDATE intraday_advice
SET valid_until = LEAST(valid_until, %(disabled_at)s)
WHERE valid_until > %(disabled_at)s;
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


@dataclass(frozen=True)
class AgentAnalysisRecord:
    """
    Persisted TradingAgents analysis record shown by the UI history tab.
    """

    run_id: str
    vt_symbol: str
    trade_date: str
    mode: str
    model_provider: str
    model_name: str
    prompt_version: str
    snapshot_ids: list[Any]
    context: dict[str, Any]
    created_at: Any
    report: str
    raw_state: dict[str, Any]
    error_message: str
    rating: str
    confidence: float | None
    action: str
    target_weight_hint: float | None
    holding_period_hint: str
    risk_notes: str


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
            if not _is_failed_response(response):
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

    def load_analysis_history(
        self,
        vt_symbol: str = "",
        limit: int = 100,
    ) -> list[AgentAnalysisRecord]:
        """
        Load persisted TradingAgents analysis history for the UI workspace.
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                SELECT_ANALYSIS_HISTORY_SQL,
                {
                    "vt_symbol": vt_symbol.strip(),
                    "limit": max(1, min(int(limit), 1000)),
                },
            )
            return [_analysis_record_from_row(row) for row in cursor.fetchall()]
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

    def load_latest_trade_intent(
        self,
        vt_symbol: str,
        trade_date: str,
    ) -> PortfolioIntent | None:
        """
        Load the latest AI trade intent at or before trade_date for one symbol.
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(
                SELECT_LATEST_TRADE_INTENT_SQL,
                {
                    "vt_symbol": vt_symbol,
                    "trade_date": trade_date,
                },
            )
            row = cursor.fetchone()
            if not row:
                return None

            return _portfolio_intent_from_row(row)
        finally:
            cursor.close()


class PostgresRuntimeStateStorage:
    """
    PostgreSQL persistence for TradingAgents runtime switches.
    """

    def __init__(self, connection: Connection, state_id: str = "default") -> None:
        """"""
        self.connection: Connection = connection
        self.state_id: str = state_id

    def save_state(self, state: TradingAgentsRuntimeState) -> None:
        """
        Persist the current runtime state.
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(UPSERT_AI_RUNTIME_STATE_SQL, _runtime_state_params(self.state_id, state))
            self.connection.commit()
        finally:
            cursor.close()

    def load_state(self) -> TradingAgentsRuntimeState | None:
        """
        Load the last persisted runtime state.
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(SELECT_AI_RUNTIME_STATE_SQL, {"state_id": self.state_id})
            row = cursor.fetchone()
            if not row:
                return None
            return _runtime_state_from_row(row)
        finally:
            cursor.close()

    def disable_active_signals(self, disabled_at: Any) -> None:
        """
        Expire unexpired intraday advice when AI is paused.
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(DISABLE_AI_SIGNALS_SQL, {"disabled_at": disabled_at})
            self.connection.commit()
        finally:
            cursor.close()


def _json_dumps(data: Any) -> str:
    """
    Serialize JSON payloads in a stable, readable format.
    """
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def _json_loads(value: Any, fallback: Any) -> Any:
    """
    Decode JSON values from psycopg or the vn.py test adapter.
    """
    if value is None:
        return fallback
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return fallback
    return value


def _analysis_record_from_row(row: Mapping[str, Any]) -> AgentAnalysisRecord:
    """
    Convert an analysis-history SQL row into a UI-friendly record.
    """
    snapshot_ids = _json_loads(row.get("snapshot_ids"), [])
    if not isinstance(snapshot_ids, list):
        snapshot_ids = [snapshot_ids]

    context = _json_loads(row.get("context"), {})
    if not isinstance(context, dict):
        context = {}

    raw_state = _json_loads(row.get("raw_state"), {})
    if not isinstance(raw_state, dict):
        raw_state = {}

    return AgentAnalysisRecord(
        run_id=str(row.get("run_id") or ""),
        vt_symbol=str(row.get("vt_symbol") or ""),
        trade_date=str(row.get("trade_date") or ""),
        mode=str(row.get("mode") or ""),
        model_provider=str(row.get("model_provider") or ""),
        model_name=str(row.get("model_name") or ""),
        prompt_version=str(row.get("prompt_version") or ""),
        snapshot_ids=snapshot_ids,
        context=context,
        created_at=row.get("created_at"),
        report=str(row.get("report") or ""),
        raw_state=raw_state,
        error_message=str(row.get("error_message") or ""),
        rating=str(row.get("rating") or ""),
        confidence=row.get("confidence"),
        action=str(row.get("action") or ""),
        target_weight_hint=row.get("target_weight_hint"),
        holding_period_hint=str(row.get("holding_period_hint") or ""),
        risk_notes=str(row.get("risk_notes") or ""),
    )


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


def _is_failed_response(response: TradingAgentsWorkerResponse) -> bool:
    """
    Return True when worker output is diagnostic only and must not become a signal.
    """
    return str(response.raw_state.get("status", "")).lower() == "failed"


def _runtime_state_params(
    state_id: str,
    state: TradingAgentsRuntimeState,
) -> dict[str, Any]:
    """
    Convert runtime state into SQL params.
    """
    return {
        "state_id": state_id,
        "enabled": state.enabled,
        "mode": state.mode.value,
        "live_enabled": state.live_enabled,
        "manual_takeover": state.manual_takeover,
        "signal_status": state.signal_status.value,
        "disabled_reason": state.disabled_reason,
        "last_heartbeat_at": state.last_heartbeat_at,
        "last_successful_run_id": state.last_successful_run_id,
    }


def _runtime_state_from_row(row: Mapping[str, Any]) -> TradingAgentsRuntimeState:
    """
    Convert a DB row into runtime state.
    """
    return TradingAgentsRuntimeState(
        enabled=bool(row["enabled"]),
        live_enabled=bool(row["live_enabled"]),
        mode=TradingAgentsMode(str(row["mode"])),
        disabled_reason=str(row.get("disabled_reason") or ""),
        last_heartbeat_at=row.get("last_heartbeat_at"),
        last_successful_run_id=str(row.get("last_successful_run_id") or ""),
        signal_status=SignalStatus(str(row["signal_status"])),
        manual_takeover=bool(row.get("manual_takeover")),
    )


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
