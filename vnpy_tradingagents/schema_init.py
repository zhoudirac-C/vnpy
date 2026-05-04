from typing import Any, Protocol

from vnpy_router.event_storage import EVENT_SCHEMA, EVENT_SOURCE_QUALITY_MIGRATION_SQL
from vnpy_router.storage import SNAPSHOT_SCHEMA

from .monitoring import REPLAY_RUN_STATUS_SCHEMA
from .migrations import Migration, MigrationApplyResult, MigrationRunner
from .ops_storage import OPS_SCHEMA
from .performance_feedback import FEEDBACK_SCHEMA
from .risk import DECISION_AUDIT_SCHEMA
from .storage import AI_RUNTIME_STATE_MIGRATION_SQL, TRADINGAGENTS_SCHEMA


SCHEMA_VERSION_SQL: str = """
CREATE TABLE IF NOT EXISTS schema_version (
    namespace TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    applied_at TIMESTAMPTZ DEFAULT now()
);

INSERT INTO schema_version (
    namespace,
    version
) VALUES (
    'tradingagents',
    'p6'
)
ON CONFLICT (namespace)
DO UPDATE SET
    version = EXCLUDED.version,
    applied_at = now();
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


DEFAULT_MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version="0001_tradingagents_schema",
        description="Create vnpy_router and TradingAgents production tables",
        sql="\n".join(
            [
                SCHEMA_VERSION_SQL,
                SNAPSHOT_SCHEMA,
                EVENT_SCHEMA,
                TRADINGAGENTS_SCHEMA,
                DECISION_AUDIT_SCHEMA,
                FEEDBACK_SCHEMA,
                REPLAY_RUN_STATUS_SCHEMA,
            ]
        ),
    ),
    Migration(
        version="0002_event_source_quality",
        description="Add production event source quality columns",
        sql=EVENT_SOURCE_QUALITY_MIGRATION_SQL,
    ),
    Migration(
        version="0003_ops_heartbeat",
        description="Create operational heartbeat tables",
        sql=OPS_SCHEMA,
    ),
    Migration(
        version="0004_ai_runtime_state",
        description="Create TradingAgents runtime state table",
        sql=AI_RUNTIME_STATE_MIGRATION_SQL,
    ),
)


def initialize_postgres_schema(connection: Connection) -> MigrationApplyResult:
    """
    Idempotently create all TradingAgents and router PostgreSQL tables.
    """
    return MigrationRunner(connection, DEFAULT_MIGRATIONS).apply()
