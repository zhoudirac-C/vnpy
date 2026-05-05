"""
Peewee helpers that reuse vn.py global PostgreSQL settings.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from vnpy.trader.setting import SETTINGS


POSTGRES_DATABASE_NAMES: set[str] = {"postgres", "postgresql"}
REQUIRED_POSTGRES_FIELDS: tuple[str, ...] = (
    "database.database",
    "database.host",
    "database.port",
    "database.user",
    "database.password",
)


class VnpyPostgresConfigError(RuntimeError):
    """
    Raised when vn.py database.* settings do not select a usable PostgreSQL database.
    """


class VnpyPostgresDependencyError(RuntimeError):
    """
    Raised when Peewee PostgreSQL support is unavailable.
    """


class PeeweeConnectionAdapter:
    """
    DB-API-like adapter over a Peewee database for existing SQL storage classes.
    """

    def __init__(self, database: Any) -> None:
        """"""
        self.database: Any = database

    def cursor(self) -> "PeeweeCursorAdapter":
        """
        Return a cursor adapter that executes through Peewee.
        """
        return PeeweeCursorAdapter(self.database)

    def commit(self) -> None:
        """
        Commit when the underlying Peewee database exposes an explicit commit method.
        """
        commit = getattr(self.database, "commit", None)
        if commit is not None:
            commit()


class PeeweeCursorAdapter:
    """
    Small cursor wrapper that normalizes tuple rows into dictionaries.
    """

    def __init__(self, database: Any) -> None:
        """"""
        self.database: Any = database
        self.cursor: Any | None = None

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> None:
        """
        Execute raw SQL via Peewee.
        """
        self.cursor = self.database.execute_sql(sql, params)

    def fetchall(self) -> list[Mapping[str, Any]]:
        """
        Fetch all rows as mappings.
        """
        if self.cursor is None:
            return []
        rows = self.cursor.fetchall()
        return [_row_to_mapping(row, self.cursor.description) for row in rows]

    def fetchone(self) -> Mapping[str, Any] | None:
        """
        Fetch one row as a mapping.
        """
        if self.cursor is None:
            return None
        row = self.cursor.fetchone()
        if row is None:
            return None
        return _row_to_mapping(row, self.cursor.description)

    def close(self) -> None:
        """
        Close the underlying raw cursor when present.
        """
        if self.cursor is not None:
            close = getattr(self.cursor, "close", None)
            if close is not None:
                close()


def is_vnpy_postgres(settings: Mapping[str, Any] | None = None) -> bool:
    """
    Return whether vn.py global settings select PostgreSQL.
    """
    source: Mapping[str, Any] = settings or SETTINGS
    database_name: str = str(source.get("database.name", "")).strip().lower()
    return database_name in POSTGRES_DATABASE_NAMES


def missing_vnpy_postgres_fields(settings: Mapping[str, Any] | None = None) -> list[str]:
    """
    Return missing vn.py PostgreSQL configuration field names.
    """
    source: Mapping[str, Any] = settings or SETTINGS
    missing: list[str] = []

    if not is_vnpy_postgres(source):
        missing.append("database.name")

    for field_name in REQUIRED_POSTGRES_FIELDS:
        value: Any = source.get(field_name)
        if value in {"", 0, None}:
            missing.append(field_name)

    return missing


def vnpy_postgres_peewee_params(
    settings: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build Peewee PostgreSQL connection params from vn.py database.* settings.
    """
    source: Mapping[str, Any] = settings or SETTINGS
    missing: list[str] = missing_vnpy_postgres_fields(source)
    if missing:
        raise VnpyPostgresConfigError(
            "vn.py PostgreSQL settings are incomplete: " + ", ".join(missing)
        )

    return {
        "database": source["database.database"],
        "host": source["database.host"],
        "port": source["database.port"],
        "user": source["database.user"],
        "password": source["database.password"],
    }


def create_vnpy_postgres_database(settings: Mapping[str, Any] | None = None) -> Any:
    """
    Create a Peewee PostgreSQL database from vn.py database.* settings.
    """
    try:
        from playhouse.postgres_ext import PostgresqlExtDatabase
    except ModuleNotFoundError as exc:
        raise VnpyPostgresDependencyError(
            "peewee playhouse.postgres_ext is required for PostgreSQL extensions"
        ) from exc

    return PostgresqlExtDatabase(**vnpy_postgres_peewee_params(settings))


def connect_vnpy_postgres_adapter(
    settings: Mapping[str, Any] | None = None,
) -> PeeweeConnectionAdapter:
    """
    Connect to vn.py PostgreSQL and expose a DB-API-like adapter.
    """
    database = create_vnpy_postgres_database(settings)
    database.connect(reuse_if_open=True)
    return PeeweeConnectionAdapter(database)


def _row_to_mapping(row: Any, description: Sequence[Any] | None) -> Mapping[str, Any]:
    """
    Convert tuple/list cursor rows into dictionaries using cursor.description.
    """
    if isinstance(row, Mapping):
        return dict(row)
    if description is None:
        return {}

    names: list[str] = [str(column[0]) for column in description]
    values: Sequence[Any] = row if isinstance(row, Sequence) else [row]
    return {name: values[index] for index, name in enumerate(names)}
