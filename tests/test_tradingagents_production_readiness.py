from pathlib import Path


def test_migration_runner_applies_pending_migrations_once():
    """MigrationRunner should apply pending migrations and skip applied ones."""
    from vnpy_tradingagents.migrations import Migration, MigrationRunner

    connection = FakeConnection(applied_versions={"0001_base"})
    migrations = [
        Migration(version="0001_base", description="base", sql="CREATE TABLE base(id TEXT);"),
        Migration(version="0002_events", description="events", sql="CREATE TABLE events(id TEXT);"),
    ]
    runner = MigrationRunner(connection, migrations)

    result = runner.apply()
    second = runner.apply()

    executed_sql = "\n".join(sql for sql, _ in connection.cursor_obj.executed)
    assert result.applied_versions == ["0002_events"]
    assert result.skipped_versions == ["0001_base"]
    assert second.applied_versions == []
    assert "CREATE TABLE IF NOT EXISTS schema_migration" in executed_sql
    assert "CREATE TABLE events" in executed_sql
    assert connection.commits == 2


def test_schema_init_uses_production_migration_runner():
    """initialize_postgres_schema should return migration apply status."""
    from vnpy_tradingagents.schema_init import initialize_postgres_schema

    connection = FakeConnection()

    result = initialize_postgres_schema(connection)

    assert result.applied_versions
    assert result.applied_versions[0] == "0001_tradingagents_schema"
    assert any("schema_migration" in sql for sql, _ in connection.cursor_obj.executed)


def test_cli_reports_missing_dsn_without_silent_success(capsys):
    """CLI should fail clearly when no PostgreSQL DSN is provided."""
    from vnpy_tradingagents.cli import main

    exit_code = main(["schema", "status"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "PostgreSQL DSN is required" in captured.err


def test_readiness_checker_reports_structured_failures(tmp_path):
    """ProductionReadinessChecker should classify config and dependency readiness."""
    from vnpy_tradingagents.readiness import ProductionReadinessChecker, ReadinessStatus

    checker = ProductionReadinessChecker(
        settings={
            "router.postgres_cache.enabled": True,
            "router.postgres.dsn": "",
            "router.providers": f"local_file:{tmp_path / 'missing.csv'},akshare",
            "tradingagents.api_key_env_var": "TRADINGAGENTS_API_KEY",
        },
        environ={},
        module_available=lambda name: name != "psycopg",
        path_exists=lambda path: Path(path).exists(),
    )

    report = checker.check()

    assert report.status == ReadinessStatus.FAILED
    assert report.by_name("postgres_dsn").status == ReadinessStatus.FAILED
    assert report.by_name("psycopg").status == ReadinessStatus.FAILED
    assert report.by_name("tradingagents_api_key").status == ReadinessStatus.FAILED
    assert report.by_name("local_file_provider").status == ReadinessStatus.WARNING


def test_readiness_checker_passes_with_required_runtime_inputs(tmp_path):
    """Readiness checker should pass when required production inputs are present."""
    from vnpy_tradingagents.readiness import ProductionReadinessChecker, ReadinessStatus

    data_path = tmp_path / "bars.csv"
    data_path.write_text("symbol,datetime,open,high,low,close,volume\n", encoding="utf-8")
    checker = ProductionReadinessChecker(
        settings={
            "router.postgres_cache.enabled": True,
            "router.postgres.dsn": "postgresql://user:pass@localhost:5432/vnpy",
            "router.providers": f"local_file:{data_path}",
            "tradingagents.api_key_env_var": "TRADINGAGENTS_API_KEY",
            "tradingagents.worker_factory": "worker_factory:build",
        },
        environ={"TRADINGAGENTS_API_KEY": "secret"},
        module_available=lambda name: True,
        path_exists=lambda path: Path(path).exists(),
    )

    report = checker.check()

    assert report.status == ReadinessStatus.READY
    assert all(item.status == ReadinessStatus.READY for item in report.items)


class FakeCursor:
    """Tiny DB-API cursor fake for migration tests."""

    def __init__(self, connection) -> None:
        self.connection = connection
        self.executed = []
        self.last_sql = ""

    def execute(self, sql, params=None) -> None:
        self.executed.append((sql, params or {}))
        self.last_sql = sql
        if "INSERT INTO schema_migration" in sql:
            self.connection.applied_versions.add(params["version"])

    def fetchall(self):
        if "FROM schema_migration" in self.last_sql:
            return [{"version": version} for version in sorted(self.connection.applied_versions)]
        return []

    def close(self) -> None:
        return


class FakeConnection:
    """Tiny DB-API connection fake."""

    def __init__(self, applied_versions=None) -> None:
        self.applied_versions = set(applied_versions or set())
        self.cursor_obj = FakeCursor(self)
        self.commits = 0

    def cursor(self):
        return self.cursor_obj

    def commit(self) -> None:
        self.commits += 1
