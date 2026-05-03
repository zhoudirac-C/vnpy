from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol


SCHEMA_MIGRATION_TABLE_SQL: str = """
CREATE TABLE IF NOT EXISTS schema_migration (
    version TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at TIMESTAMPTZ DEFAULT now()
);
"""


SELECT_APPLIED_MIGRATIONS_SQL: str = """
SELECT
    version
FROM schema_migration
ORDER BY version;
"""


INSERT_SCHEMA_MIGRATION_SQL: str = """
INSERT INTO schema_migration (
    version,
    description
) VALUES (
    %(version)s,
    %(description)s
)
ON CONFLICT (version) DO NOTHING;
"""


@dataclass(frozen=True)
class Migration:
    """
    One idempotent PostgreSQL schema migration.
    """

    version: str
    description: str
    sql: str


@dataclass(frozen=True)
class MigrationApplyResult:
    """
    Result of applying a migration batch.
    """

    applied_versions: list[str]
    skipped_versions: list[str]


class Cursor(Protocol):
    """
    Minimal DB-API cursor protocol.
    """

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> None:
        pass

    def fetchall(self) -> list[dict[str, Any]]:
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


class MigrationRunner:
    """
    Apply ordered PostgreSQL schema migrations and record applied versions.
    """

    def __init__(
        self,
        connection: Connection,
        migrations: Sequence[Migration],
    ) -> None:
        """"""
        self.connection: Connection = connection
        self.migrations: list[Migration] = list(migrations)

    def applied_versions(self) -> set[str]:
        """
        Return versions already recorded in schema_migration.
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(SCHEMA_MIGRATION_TABLE_SQL)
            cursor.execute(SELECT_APPLIED_MIGRATIONS_SQL)
            return _fetch_versions(cursor)
        finally:
            cursor.close()

    def apply(self) -> MigrationApplyResult:
        """
        Apply pending migrations once and record their versions.
        """
        cursor = self.connection.cursor()
        applied_versions: list[str] = []
        skipped_versions: list[str] = []
        try:
            cursor.execute(SCHEMA_MIGRATION_TABLE_SQL)
            cursor.execute(SELECT_APPLIED_MIGRATIONS_SQL)
            already_applied: set[str] = _fetch_versions(cursor)

            for migration in self.migrations:
                if migration.version in already_applied:
                    skipped_versions.append(migration.version)
                    continue

                cursor.execute(migration.sql)
                cursor.execute(
                    INSERT_SCHEMA_MIGRATION_SQL,
                    {
                        "version": migration.version,
                        "description": migration.description,
                    },
                )
                already_applied.add(migration.version)
                applied_versions.append(migration.version)

            self.connection.commit()
        finally:
            cursor.close()

        return MigrationApplyResult(
            applied_versions=applied_versions,
            skipped_versions=skipped_versions,
        )


def _fetch_versions(cursor: Cursor) -> set[str]:
    """
    Fetch applied migration versions when the DB-API cursor supports fetchall.
    """
    fetchall = getattr(cursor, "fetchall", None)
    if fetchall is None:
        return set()
    return {str(row["version"]) for row in fetchall()}
