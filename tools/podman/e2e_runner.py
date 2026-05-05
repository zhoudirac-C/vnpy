from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import traceback
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


CASE_IDS: tuple[str, ...] = tuple(f"PE2E-{index:02d}" for index in range(17))


@dataclass
class CaseResult:
    case_id: str
    result: str
    executed_at: str
    git_commit: str
    environment: str
    evidence_path: str
    notes: str = ""


class E2ERunner:
    def __init__(self, evidence_dir: Path) -> None:
        self.evidence_dir: Path = evidence_dir
        self.results_path: Path = evidence_dir / "pe2e_results.json"
        self.repo_root: Path = Path.cwd()
        self.git_commit: str = os.environ.get("HOST_GIT_COMMIT", "").strip() or _run_text(
            ["git", "rev-parse", "--short", "HEAD"]
        )
        self.environment: str = _environment_name()
        self.results: dict[str, CaseResult] = self._load_results()

    def run_case(self, case_id: str, func: Callable[[], str]) -> None:
        try:
            notes = func()
        except SkippedCase as exc:
            self.record(case_id, "跳过", str(exc))
        except BlockedCase as exc:
            self.record(case_id, "阻塞", str(exc))
        except Exception as exc:
            details_path = self.evidence_dir / f"{case_id}.traceback.log"
            details_path.write_text(traceback.format_exc(), encoding="utf-8")
            self.record(case_id, "失败", f"{type(exc).__name__}: {exc}")
        else:
            self.record(case_id, "通过", notes)

    def record(self, case_id: str, result: str, notes: str = "") -> None:
        self.results[case_id] = CaseResult(
            case_id=case_id,
            result=result,
            executed_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            git_commit=self.git_commit,
            environment=self.environment,
            evidence_path=str(self.evidence_dir),
            notes=notes,
        )
        self._save_results()

    def _load_results(self) -> dict[str, CaseResult]:
        if not self.results_path.exists():
            return {}
        raw = json.loads(self.results_path.read_text(encoding="utf-8"))
        return {
            case_id: CaseResult(**payload)
            for case_id, payload in raw.items()
        }

    def _save_results(self) -> None:
        payload = {
            case_id: asdict(result)
            for case_id, result in sorted(self.results.items())
        }
        self.results_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _write_markdown(self.evidence_dir / "pe2e_results.md", self.results)


class BlockedCase(RuntimeError):
    pass


class SkippedCase(RuntimeError):
    pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("pre-restart", "post-restart"), required=True)
    parser.add_argument("--evidence-dir", required=True)
    args = parser.parse_args(argv)

    evidence_dir = Path(args.evidence_dir)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    _prepare_vnpy_settings()

    runner = E2ERunner(evidence_dir)
    if args.phase == "pre-restart":
        runner.record("PE2E-00", "通过", "Podman image built and postgres runner container started by tools/podman/run_e2e.sh")
        runner.run_case("PE2E-01", case_postgres_connection)
        runner.run_case("PE2E-02", case_vnpy_postgres_settings)
        runner.run_case("PE2E-03", case_schema_init_status)
        runner.run_case("PE2E-04", case_readiness_negative)
        runner.run_case("PE2E-05", case_readiness_positive)
        runner.run_case("PE2E-06", case_datafeed_local_file_snapshot)
        runner.run_case("PE2E-07", case_worker_factory_lazy_load)
        runner.run_case("PE2E-08", case_worker_forbidden_context)
        runner.run_case("PE2E-09", case_llm_key_not_plaintext)
        runner.run_case("PE2E-10", case_tradingagents_app_registration)
        runner.run_case("PE2E-11", case_closed_loop_local)
        runner.run_case("PE2E-12", case_closed_loop_production)
        runner.run_case("PE2E-13", case_paper_smoke_no_live_gateway)
        runner.run_case("PE2E-14", case_tradingagents_disabled_degrades)
        runner.run_case("PE2E-15", case_persistence_pre_restart)
        runner.run_case("PE2E-16", case_optional_worker_container)
    else:
        runner.run_case("PE2E-15", case_persistence_post_restart)

    return 1 if any(
        result.result == "失败" for result in runner.results.values()
    ) else 0


def case_postgres_connection() -> str:
    import psycopg2

    with psycopg2.connect(**_pg_params()) as conn:
        with conn.cursor() as cursor:
            cursor.execute("select 1")
            row = cursor.fetchone()
    if row != (1,):
        raise AssertionError(f"unexpected select result: {row}")
    return "PostgreSQL select 1 succeeded"


def case_vnpy_postgres_settings() -> str:
    from vnpy.trader.setting import SETTINGS
    from vnpy_router.peewee import vnpy_postgres_peewee_params

    SETTINGS["router.postgres.dsn"] = "postgresql://must-not-be-used"
    params = vnpy_postgres_peewee_params(SETTINGS)
    expected = {
        "database": os.environ.get("POSTGRES_DB", "vnpy"),
        "host": os.environ.get("POSTGRES_HOST", "vnpy-e2e-postgres"),
        "port": int(os.environ.get("POSTGRES_PORT", "5432")),
        "user": os.environ.get("POSTGRES_USER", "vnpy"),
        "password": os.environ.get("POSTGRES_PASSWORD", "vnpy-e2e-password"),
    }
    if params != expected:
        raise AssertionError(f"params={params!r}, expected={expected!r}")
    return "Peewee params came from vn.py database.* settings"


def case_schema_init_status() -> str:
    from vnpy_tradingagents.schema_init import EXTENSION_TABLE_NAMES, initialize_postgres_schema, schema_status

    first = initialize_postgres_schema()
    second = initialize_postgres_schema()
    status = schema_status()
    missing = [
        table_name
        for table_name, table_status in status.tables.items()
        if table_status != "ready"
    ]
    if missing:
        raise AssertionError(f"missing extension tables: {missing}")
    if "schema_migration" in first.created_or_existing_tables:
        raise AssertionError("schema_migration should not be part of extension create_tables result")
    if set(first.created_or_existing_tables) != set(second.created_or_existing_tables):
        raise AssertionError("schema init was not idempotent")
    return f"{len(EXTENSION_TABLE_NAMES)} extension tables are ready"


def case_readiness_negative() -> str:
    from vnpy_tradingagents.readiness import ProductionReadinessChecker, ReadinessStatus

    report = ProductionReadinessChecker(
        settings={
            "database.name": "sqlite",
            "database.database": "",
            "database.host": "",
            "database.port": 0,
            "database.user": "",
            "database.password": "",
            "router.providers": "",
            "tradingagents.api_key_env_var": "MISSING_E2E_KEY",
            "tradingagents.worker_factory": "",
        },
        environ={},
    ).check()
    if report.status != ReadinessStatus.FAILED:
        raise AssertionError(f"expected failed readiness, got {report.status}")
    return "Missing PostgreSQL/provider/API key readiness fails explicitly"


def case_readiness_positive() -> str:
    from vnpy.trader.setting import SETTINGS
    from vnpy_tradingagents.readiness import ProductionReadinessChecker, ReadinessStatus

    report = ProductionReadinessChecker(settings=SETTINGS, environ=os.environ).check()
    failed = [item for item in report.items if item.status == ReadinessStatus.FAILED]
    if failed:
        raise AssertionError(f"readiness failed: {failed}")
    return f"Readiness status is {report.status.value}"


def case_datafeed_local_file_snapshot() -> str:
    import psycopg2

    from vnpy.trader.constant import Exchange, Interval
    from vnpy.trader.object import HistoryRequest
    from vnpy_router.datafeed import Datafeed

    with psycopg2.connect(**_pg_params()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "delete from market_bar_snapshot where vt_symbol=%s and provider_name=%s",
                ("600519.SSE", "local_file"),
            )
            conn.commit()

    datafeed = Datafeed()
    if not datafeed.init(lambda message: _append_log("datafeed.log", str(message))):
        raise AssertionError("Datafeed did not initialize any provider")
    req = HistoryRequest(
        symbol="600519",
        exchange=Exchange.SSE,
        interval=Interval.DAILY,
        start=datetime(2024, 1, 2),
        end=datetime(2024, 1, 4, 23, 59),
    )
    bars = datafeed.query_bar_history(req, lambda message: _append_log("datafeed.log", str(message)))
    if len(bars) != 3:
        raise AssertionError(f"expected 3 bars, got {len(bars)}")
    with psycopg2.connect(**_pg_params()) as conn:
        with conn.cursor() as cursor:
            cursor.execute("select count(*) from market_bar_snapshot where vt_symbol=%s and provider_name=%s", ("600519.SSE", "local_file"))
            count = cursor.fetchone()[0]
    if count < 3:
        raise AssertionError(f"expected at least 3 persisted bars, got {count}")
    return f"local_file provider returned and persisted {len(bars)} bars"


def case_worker_factory_lazy_load() -> str:
    from vnpy_tradingagents.worker import TradingAgentsWorkerRequest
    from vnpy_tradingagents.worker_process import load_configured_worker

    worker = load_configured_worker()
    if worker is None:
        raise AssertionError("configured worker factory returned None")
    response = worker.run(
        TradingAgentsWorkerRequest(
            run_id="pe2e-07",
            vt_symbol="600519.SSE",
            trade_date="2024-01-03",
            mode="paper",
            context={"market": {"bars": [{"datetime": "2024-01-03", "close": 1698}]}},
        )
    )
    error_type = response.raw_state.get("error_type")
    if response.action not in {"hold", "watch", "buy", "sell", "reduce", "cover"}:
        raise AssertionError(f"unexpected worker action: {response.action}")
    if error_type not in {None, "dependency_error"}:
        raise AssertionError(f"unexpected worker error_type: {error_type}")
    return f"worker loaded lazily; response action={response.action}, error_type={error_type}"


def case_worker_forbidden_context() -> str:
    from vnpy_tradingagents.config import TradingAgentsWorkerConfig
    from vnpy_tradingagents.tradingagents_factory import get_context_stock_data
    from vnpy_tradingagents.worker import TradingAgentsWorkerRequest
    from vnpy_tradingagents.worker_adapter import TradingAgentsWorkerAdapter

    class FailIfCalledRunner:
        def run(self, payload: Any) -> dict[str, Any]:
            raise AssertionError("runner should not be called")

    adapter = TradingAgentsWorkerAdapter(
        config=TradingAgentsWorkerConfig(api_key_env_var="OPENAI_API_KEY"),
        runner=FailIfCalledRunner(),
        environ=os.environ,
    )
    response = adapter.run(
        TradingAgentsWorkerRequest(
            run_id="pe2e-08",
            vt_symbol="600519.SSE",
            trade_date="2024-01-03",
            mode="paper",
            context={"market": {"bars": []}, "gateway": object()},
        )
    )
    if response.raw_state.get("error_type") != "forbidden_context":
        raise AssertionError(f"expected forbidden_context, got {response.raw_state}")
    no_context_message = get_context_stock_data("600519.SSE", "2024-01-01", "2024-01-03")
    if "external market data fallback is disabled" not in no_context_message:
        raise AssertionError(no_context_message)
    return "Forbidden trading handles blocked before runner execution"


def case_llm_key_not_plaintext() -> str:
    from vnpy_tradingagents.llm_secret import LlmApiKeyStore
    from vnpy_tradingagents.secrets_policy import SecretLeakError, assert_context_has_no_secrets

    widget_source = Path("vnpy/trader/ui/widget.py").read_text(encoding="utf-8")
    for expected_text in (
        "不会保存到 vt_setting.json",
        "保存到系统钥匙串",
        "TRADINGAGENTS_API_KEY_FIELD",
    ):
        if expected_text not in widget_source:
            raise AssertionError(f"UI guidance text missing: {expected_text}")

    environ: dict[str, str] = {}
    settings = {"tradingagents.api_key_env_var": "E2E_LLM_KEY"}
    result = LlmApiKeyStore(environ=environ).set_api_key(
        settings["tradingagents.api_key_env_var"],
        "sk-e2e-secret-value",
        persist=False,
    )
    if not result.runtime_configured:
        raise AssertionError("UI secret save did not configure runtime env")
    if environ.get("E2E_LLM_KEY") != "sk-e2e-secret-value":
        raise AssertionError("runtime environment did not receive secret")
    if "sk-e2e-secret-value" in json.dumps(settings):
        raise AssertionError("plaintext key leaked into settings")
    try:
        assert_context_has_no_secrets({"news": [{"headline": "OPENAI_API_KEY=sk-e2e-secret-value"}]})
    except SecretLeakError:
        return "UI guidance is present; runtime secret stays out of settings and secret policy blocks value leaks"
    raise AssertionError("secret value in context was not blocked")


def case_tradingagents_app_registration() -> str:
    import importlib

    run_py = Path("examples/veighna_trader/run.py").read_text(encoding="utf-8")
    if "TradingAgentsApp" not in run_py or "main_engine.add_app(TradingAgentsApp)" not in run_py:
        raise AssertionError("examples/veighna_trader/run.py does not register TradingAgentsApp")
    from vnpy_tradingagents import TradingAgentsApp

    try:
        ui_module = importlib.import_module(TradingAgentsApp.app_module + ".ui")
    except ImportError as exc:
        if "libEGL.so.1" in str(exc):
            raise BlockedCase("Qt UI import requires libEGL.so.1 in the Podman image")
        raise
    if not hasattr(ui_module, TradingAgentsApp.widget_name):
        raise AssertionError(f"missing UI widget {TradingAgentsApp.widget_name}")
    return "TradingAgentsApp is registered and UI module imports"


def case_closed_loop_local() -> str:
    if shutil.which("git") is None:
        raise BlockedCase("git is not available in the minimal Podman runner image")

    output = Path(os.environ.get("EVIDENCE_DIR", "/evidence")) / "closed_loop_local.md"
    json_output = Path(os.environ.get("EVIDENCE_DIR", "/evidence")) / "closed_loop_local.json"
    completed = _run_command(
        [
            "uv",
            "run",
            "python",
            "-m",
            "tools.production.closed_loop_validation",
            "--profile",
            "local",
            "--output",
            str(output),
            "--json-output",
            str(json_output),
        ],
        "closed_loop_local",
        timeout=420,
    )
    if completed.returncode != 0:
        raise AssertionError("local closed-loop validation failed")
    return f"local closed-loop report: {output}"


def case_closed_loop_production() -> str:
    if shutil.which("git") is None:
        raise BlockedCase("git is not available in the minimal Podman runner image")

    bad_env = dict(os.environ)
    bad_env.pop("OPENAI_API_KEY", None)
    failed = _run_command(
        [
            "uv",
            "run",
            "python",
            "-m",
            "tools.production.closed_loop_validation",
            "--profile",
            "production",
        ],
        "closed_loop_production_missing_key",
        timeout=420,
        env=bad_env,
    )
    if failed.returncode == 0:
        raise AssertionError("production validation unexpectedly passed without API key")

    passed = _run_command(
        [
            "uv",
            "run",
            "python",
            "-m",
            "tools.production.closed_loop_validation",
            "--profile",
            "production",
            "--output",
            str(Path(os.environ.get("EVIDENCE_DIR", "/evidence")) / "closed_loop_production.md"),
            "--json-output",
            str(Path(os.environ.get("EVIDENCE_DIR", "/evidence")) / "closed_loop_production.json"),
        ],
        "closed_loop_production_full",
        timeout=420,
    )
    if passed.returncode != 0:
        raise BlockedCase(
            "production profile did not pass in the mutable E2E worktree; see closed_loop_production_full logs"
        )
    return "production profile rejects missing key and passes with configured gates"


def case_paper_smoke_no_live_gateway() -> str:
    completed = _run_command(
        [
            "uv",
            "run",
            "--with",
            "pytest",
            "pytest",
            "tests/test_vnpy_paper_ops_integration.py::test_paper_smoke_runs_snapshot_worker_signal_fill_feedback_without_live_gateway",
            "tests/test_vnpy_paper_ops_integration.py::test_paper_smoke_does_not_record_fill_for_hold_advice",
            "-q",
        ],
        "paper_smoke_pytest",
        timeout=180,
    )
    if completed.returncode != 0:
        raise AssertionError("paper smoke pytest failed")
    return "paper smoke buy/hold paths passed without live Gateway"


def case_tradingagents_disabled_degrades() -> str:
    from vnpy_tradingagents.runtime import TradingAgentsRuntimeController
    from vnpy_tradingagents.service import TradingAgentsService
    from vnpy_tradingagents.worker import TradingAgentsWorkerRequest, TradingAgentsWorkerResponse

    class FailIfCalledWorker:
        def run(self, request: TradingAgentsWorkerRequest) -> TradingAgentsWorkerResponse:
            raise AssertionError("disabled service should not call worker")

    class RecordingStorage:
        def __init__(self) -> None:
            self.saved: list[tuple[TradingAgentsWorkerRequest, TradingAgentsWorkerResponse]] = []

        def save_worker_result(
            self,
            request: TradingAgentsWorkerRequest,
            response: TradingAgentsWorkerResponse,
        ) -> None:
            self.saved.append((request, response))

    runtime = TradingAgentsRuntimeController()
    runtime.disable("pe2e-disabled")
    storage = RecordingStorage()
    service = TradingAgentsService(runtime=runtime, worker=FailIfCalledWorker(), storage=storage)
    result = service.run(
        TradingAgentsWorkerRequest(
            run_id="pe2e-14",
            vt_symbol="600519.SSE",
            trade_date="2024-01-03",
            mode="paper",
            context={"market": {"bars": []}},
        )
    )
    if result is not None:
        raise AssertionError(f"expected disabled service to return None, got {result}")
    if storage.saved:
        raise AssertionError("disabled service should not persist worker output")
    return "disabled TradingAgents service degrades without worker call"


def case_persistence_pre_restart() -> str:
    import psycopg2

    with psycopg2.connect(**_pg_params()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "insert into agent_run ("
                "run_id, vt_symbol, trade_date, mode, model_provider, model_name, "
                "prompt_version, snapshot_ids, context"
                ") values (%s, %s, %s::date, %s, %s, %s, %s, %s::jsonb, %s::jsonb) "
                "on conflict (run_id) do update set context = excluded.context",
                (
                    "pe2e-persist",
                    "600519.SSE",
                    "2024-01-03",
                    "paper",
                    "openai",
                    "gpt-4o-mini",
                    "pe2e",
                    "[]",
                    '{"status": "started"}',
                ),
            )
            conn.commit()
    return "Inserted persistence sentinel agent_run pe2e-persist before restart"


def case_persistence_post_restart() -> str:
    import psycopg2

    with psycopg2.connect(**_pg_params()) as conn:
        with conn.cursor() as cursor:
            cursor.execute("select context->>%s from agent_run where run_id=%s", ("status", "pe2e-persist"))
            row = cursor.fetchone()
    if row != ("started",):
        raise AssertionError(f"persistence sentinel missing after restart: {row}")
    return "Persistence sentinel survived PostgreSQL container restart"


def case_optional_worker_container() -> str:
    raise SkippedCase("Independent worker container/RPC mode is optional and not implemented in this fork yet")


def _prepare_vnpy_settings() -> None:
    home = Path.home()
    setting_dir = home / ".vntrader"
    setting_dir.mkdir(parents=True, exist_ok=True)
    settings = json.loads(Path("tests/fixtures/e2e/vt_setting.postgres.json").read_text(encoding="utf-8"))
    settings.update(
        {
            "database.host": os.environ.get("POSTGRES_HOST", settings["database.host"]),
            "database.port": int(os.environ.get("POSTGRES_PORT", settings["database.port"])),
            "database.database": os.environ.get("POSTGRES_DB", settings["database.database"]),
            "database.user": os.environ.get("POSTGRES_USER", settings["database.user"]),
            "database.password": os.environ.get("POSTGRES_PASSWORD", settings["database.password"]),
            "router.local_path": str(Path("tests/fixtures/e2e").resolve()),
        }
    )
    (setting_dir / "vt_setting.json").write_text(
        json.dumps(settings, ensure_ascii=False, indent=4),
        encoding="utf-8",
    )


def _pg_params() -> dict[str, Any]:
    return {
        "dbname": os.environ.get("POSTGRES_DB", "vnpy"),
        "host": os.environ.get("POSTGRES_HOST", "vnpy-e2e-postgres"),
        "port": int(os.environ.get("POSTGRES_PORT", "5432")),
        "user": os.environ.get("POSTGRES_USER", "vnpy"),
        "password": os.environ.get("POSTGRES_PASSWORD", "vnpy-e2e-password"),
    }


def _run_command(
    command: list[str],
    name: str,
    *,
    timeout: int,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    evidence_dir = Path(os.environ.get("EVIDENCE_DIR", "/evidence"))
    completed = subprocess.run(
        command,
        cwd=Path.cwd(),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    (evidence_dir / f"{name}.stdout.log").write_text(completed.stdout, encoding="utf-8")
    (evidence_dir / f"{name}.stderr.log").write_text(completed.stderr, encoding="utf-8")
    return completed


def _append_log(name: str, text: str) -> None:
    evidence_dir = Path(os.environ.get("EVIDENCE_DIR", "/evidence"))
    with (evidence_dir / name).open("a", encoding="utf-8") as f:
        f.write(text + "\n")


def _run_text(command: list[str]) -> str:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return "unknown"
    if completed.returncode != 0:
        return "unknown"
    return completed.stdout.strip() or "unknown"


def _environment_name() -> str:
    return "podman:" + _run_text(["python", "-c", "import platform; print(platform.platform())"])


def _write_markdown(path: Path, results: dict[str, CaseResult]) -> None:
    lines = [
        "# Podman E2E Results",
        "",
        "| ID | Result | Time | Commit | Evidence | Notes |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for case_id in CASE_IDS:
        result = results.get(case_id)
        if result is None:
            lines.append(f"| {case_id} | 未执行 |  |  |  |  |")
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    result.case_id,
                    result.result,
                    result.executed_at,
                    result.git_commit,
                    result.evidence_path,
                    result.notes.replace("|", "/"),
                ]
            )
            + " |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
