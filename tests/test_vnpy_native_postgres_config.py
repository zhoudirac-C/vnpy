def test_vnpy_postgres_peewee_params_use_database_settings_only():
    """PostgreSQL extension helpers should reuse vn.py database.* settings only."""
    from vnpy_router.peewee import vnpy_postgres_peewee_params

    settings = {
        "database.name": "postgresql",
        "database.host": "localhost",
        "database.port": 5432,
        "database.database": "vnpy",
        "database.user": "postgres",
        "database.password": "secret",
        "router.postgres.dsn": "postgresql://must-not-be-used",
    }

    params = vnpy_postgres_peewee_params(settings)

    assert params == {
        "database": "vnpy",
        "host": "localhost",
        "port": 5432,
        "user": "postgres",
        "password": "secret",
    }


def test_vnpy_postgres_missing_fields_report_database_keys():
    """Missing PostgreSQL config should be reported with vn.py database.* field names."""
    from vnpy_router.peewee import missing_vnpy_postgres_fields

    settings = {
        "database.name": "sqlite",
        "database.database": "",
        "database.host": "",
        "database.port": 0,
        "database.user": "",
        "database.password": "",
    }

    missing = missing_vnpy_postgres_fields(settings)

    assert missing == [
        "database.name",
        "database.database",
        "database.host",
        "database.port",
        "database.user",
        "database.password",
    ]


def test_peewee_connection_adapter_returns_mapping_rows():
    """Existing raw SQL readers should receive dict-like rows from a Peewee connection."""
    from vnpy_router.peewee import PeeweeConnectionAdapter

    adapter = PeeweeConnectionAdapter(FakePeeweeDatabase(rows=[("600519.SSE", 1688.0)]))
    cursor = adapter.cursor()

    cursor.execute("select vt_symbol, close_price from market_bar_snapshot")

    assert cursor.fetchall() == [{"vt_symbol": "600519.SSE", "close_price": 1688.0}]


class FakePeeweeCursor:
    """Tiny raw cursor fake returned by Peewee execute_sql."""

    description = (("vt_symbol",), ("close_price",))

    def __init__(self, rows):
        self.rows = rows
        self.closed = False

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def close(self):
        self.closed = True


class FakePeeweeDatabase:
    """Tiny Peewee database fake for connection adapter tests."""

    def __init__(self, rows):
        self.rows = rows
        self.executed = []
        self.commits = 0

    def execute_sql(self, sql, params=None):
        self.executed.append((sql, params or {}))
        return FakePeeweeCursor(self.rows)

    def commit(self):
        self.commits += 1
