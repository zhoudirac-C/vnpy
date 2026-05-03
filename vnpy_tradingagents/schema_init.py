from typing import Any, Protocol

from vnpy_router.event_storage import EVENT_SCHEMA
from vnpy_router.storage import SNAPSHOT_SCHEMA

from .monitoring import REPLAY_RUN_STATUS_SCHEMA
from .performance_feedback import FEEDBACK_SCHEMA
from .risk import DECISION_AUDIT_SCHEMA
from .storage import TRADINGAGENTS_SCHEMA


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


def initialize_postgres_schema(connection: Connection) -> None:
    """
    Idempotently create all TradingAgents and router PostgreSQL tables.
    """
    cursor = connection.cursor()
    try:
        cursor.execute(
            "\n".join(
                [
                    SCHEMA_VERSION_SQL,
                    SNAPSHOT_SCHEMA,
                    EVENT_SCHEMA,
                    TRADINGAGENTS_SCHEMA,
                    DECISION_AUDIT_SCHEMA,
                    FEEDBACK_SCHEMA,
                    REPLAY_RUN_STATUS_SCHEMA,
                ]
            )
        )
        connection.commit()
    finally:
        cursor.close()
