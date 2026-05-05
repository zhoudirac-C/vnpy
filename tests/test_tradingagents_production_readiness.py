from pathlib import Path


def test_schema_init_uses_peewee_create_tables():
    """initialize_postgres_schema should reuse Peewee create_tables like vnpy_postgresql."""
    from vnpy_tradingagents.schema_init import initialize_postgres_schema

    database = FakePeeweeDatabase(existing_tables=[])

    result = initialize_postgres_schema(database)

    assert database.connected
    assert database.safe is True
    assert "agent_run" in result.created_or_existing_tables
    assert "market_bar_snapshot" in result.created_or_existing_tables
    assert "schema_migration" not in result.created_or_existing_tables


def test_schema_status_reports_extension_table_presence():
    """schema status should inspect extension tables instead of schema_migration."""
    from vnpy_tradingagents.schema_init import schema_status

    status = schema_status(
        FakePeeweeDatabase(
            existing_tables=[
                "agent_run",
                "market_bar_snapshot",
            ]
        )
    )

    assert status.tables["agent_run"] == "ready"
    assert status.tables["market_bar_snapshot"] == "ready"
    assert status.tables["rating_signal"] == "missing"


def test_cli_reports_missing_vnpy_postgres_config_without_silent_success(capsys):
    """CLI should fail clearly when vn.py PostgreSQL settings are missing."""
    from vnpy_tradingagents.cli import main

    exit_code = main(["schema", "status"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "vn.py PostgreSQL settings are incomplete" in captured.err


def test_readiness_checker_reports_structured_failures(tmp_path):
    """ProductionReadinessChecker should classify config and dependency readiness."""
    from vnpy_tradingagents.readiness import ProductionReadinessChecker, ReadinessStatus

    checker = ProductionReadinessChecker(
        settings={
            "database.name": "sqlite",
            "database.database": "",
            "database.host": "",
            "database.port": 0,
            "database.user": "",
            "database.password": "",
            "router.providers": "local_file,akshare",
            "router.local_path": str(tmp_path / "missing.csv"),
            "tradingagents.api_key_env_var": "TRADINGAGENTS_API_KEY",
        },
        environ={},
        module_available=lambda name: name != "peewee",
        path_exists=lambda path: Path(path).exists(),
    )

    report = checker.check()

    assert report.status == ReadinessStatus.FAILED
    assert report.by_name("vnpy_postgres_config").status == ReadinessStatus.FAILED
    assert report.by_name("peewee").status == ReadinessStatus.FAILED
    assert report.by_name("tradingagents_api_key").status == ReadinessStatus.FAILED
    assert report.by_name("local_file_provider").status == ReadinessStatus.WARNING


def test_readiness_checker_passes_with_required_runtime_inputs(tmp_path):
    """Readiness checker should pass when required production inputs are present."""
    from vnpy_tradingagents.readiness import ProductionReadinessChecker, ReadinessStatus

    data_path = tmp_path / "bars.csv"
    data_path.write_text("symbol,datetime,open,high,low,close,volume\n", encoding="utf-8")
    checker = ProductionReadinessChecker(
        settings={
            "database.name": "postgresql",
            "database.host": "localhost",
            "database.port": 5432,
            "database.database": "vnpy",
            "database.user": "postgres",
            "database.password": "secret",
            "router.providers": "local_file",
            "router.local_path": str(data_path),
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


def test_readiness_checker_requires_router_local_path_for_local_file(tmp_path):
    """Readiness should match vn.py Datafeed config and not accept local_file:/path."""
    from vnpy_tradingagents.readiness import ProductionReadinessChecker, ReadinessStatus

    inline_path = tmp_path / "bars.csv"
    inline_path.write_text("symbol,datetime,open,high,low,close,volume\n", encoding="utf-8")
    checker = ProductionReadinessChecker(
        settings={
            "database.name": "postgresql",
            "database.host": "localhost",
            "database.port": 5432,
            "database.database": "vnpy",
            "database.user": "postgres",
            "database.password": "secret",
            "router.providers": f"local_file:{inline_path}",
            "tradingagents.api_key_env_var": "TRADINGAGENTS_API_KEY",
            "tradingagents.worker_factory": "worker_factory:build",
        },
        environ={"TRADINGAGENTS_API_KEY": "secret"},
        module_available=lambda name: True,
        path_exists=lambda path: Path(path).exists(),
    )

    report = checker.check()

    assert report.status == ReadinessStatus.WARNING
    local_file = report.by_name("local_file_provider")
    assert local_file.status == ReadinessStatus.WARNING
    assert "router.local_path" in local_file.message


def test_readiness_checker_requires_psycopg2_for_postgres(tmp_path):
    """Production readiness should fail when PostgreSQL driver is unavailable."""
    from vnpy_tradingagents.readiness import ProductionReadinessChecker, ReadinessStatus

    data_path = tmp_path / "bars.csv"
    data_path.write_text("symbol,datetime,open,high,low,close,volume\n", encoding="utf-8")
    checker = ProductionReadinessChecker(
        settings={
            "database.name": "postgresql",
            "database.host": "localhost",
            "database.port": 5432,
            "database.database": "vnpy",
            "database.user": "postgres",
            "database.password": "secret",
            "router.providers": "local_file",
            "router.local_path": str(data_path),
            "tradingagents.api_key_env_var": "TRADINGAGENTS_API_KEY",
            "tradingagents.worker_factory": "worker_factory:build",
        },
        environ={"TRADINGAGENTS_API_KEY": "secret"},
        module_available=lambda name: name != "psycopg2",
        path_exists=lambda path: Path(path).exists(),
    )

    report = checker.check()

    assert report.status == ReadinessStatus.FAILED
    assert report.by_name("psycopg2").status == ReadinessStatus.FAILED


class FakePeeweeDatabase:
    """Tiny Peewee-like database fake for schema init/status tests."""

    def __init__(self, existing_tables=None) -> None:
        self.existing_tables = set(existing_tables or [])
        self.created_models = []
        self.safe = None
        self.connected = False

    def connect(self, reuse_if_open=False) -> None:
        self.connected = reuse_if_open

    def create_tables(self, models, safe=False) -> None:
        self.created_models = list(models)
        self.safe = safe
        for model in models:
            self.existing_tables.add(model._meta.table_name)

    def get_tables(self):
        return sorted(self.existing_tables)
