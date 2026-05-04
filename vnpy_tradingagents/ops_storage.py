import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


OPS_SCHEMA: str = """
CREATE TABLE IF NOT EXISTS ops_heartbeat (
    component TEXT PRIMARY KEY,
    heartbeat_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL,
    last_error TEXT,
    data_latency_seconds DOUBLE PRECISION,
    queue_backlog INTEGER,
    degraded_sources JSONB,
    payload JSONB,
    updated_at TIMESTAMPTZ DEFAULT now()
);
"""


INSERT_OPS_HEARTBEAT_SQL: str = """
INSERT INTO ops_heartbeat (
    component,
    heartbeat_at,
    status,
    last_error,
    data_latency_seconds,
    queue_backlog,
    degraded_sources,
    payload
) VALUES (
    %(component)s,
    %(heartbeat_at)s,
    %(status)s,
    %(last_error)s,
    %(data_latency_seconds)s,
    %(queue_backlog)s,
    %(degraded_sources)s,
    %(payload)s
)
ON CONFLICT (component)
DO UPDATE SET
    heartbeat_at = EXCLUDED.heartbeat_at,
    status = EXCLUDED.status,
    last_error = EXCLUDED.last_error,
    data_latency_seconds = EXCLUDED.data_latency_seconds,
    queue_backlog = EXCLUDED.queue_backlog,
    degraded_sources = EXCLUDED.degraded_sources,
    payload = EXCLUDED.payload,
    updated_at = now();
"""


@dataclass(frozen=True)
class OpsHeartbeat:
    """
    Production heartbeat for workers, providers and schedulers.
    """

    component: str
    heartbeat_at: datetime
    status: str
    last_error: str = ""
    data_latency_seconds: float = 0
    queue_backlog: int = 0
    degraded_sources: list[str] = field(default_factory=list)
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


class PostgresOpsStorage:
    """
    PostgreSQL storage for operational health snapshots.
    """

    def __init__(self, connection: Connection) -> None:
        """"""
        self.connection: Connection = connection

    def create_schema(self) -> None:
        """
        Create ops tables.
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(OPS_SCHEMA)
            self.connection.commit()
        finally:
            cursor.close()

    def save_heartbeat(self, heartbeat: OpsHeartbeat) -> None:
        """
        Persist one heartbeat snapshot.
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(INSERT_OPS_HEARTBEAT_SQL, _heartbeat_params(heartbeat))
            self.connection.commit()
        finally:
            cursor.close()


def _heartbeat_params(heartbeat: OpsHeartbeat) -> dict[str, Any]:
    """
    Convert heartbeat to SQL params.
    """
    return {
        "component": heartbeat.component,
        "heartbeat_at": heartbeat.heartbeat_at,
        "status": heartbeat.status,
        "last_error": heartbeat.last_error,
        "data_latency_seconds": heartbeat.data_latency_seconds,
        "queue_backlog": heartbeat.queue_backlog,
        "degraded_sources": json.dumps(heartbeat.degraded_sources, ensure_ascii=False),
        "payload": json.dumps(heartbeat.payload, ensure_ascii=False, sort_keys=True),
    }
