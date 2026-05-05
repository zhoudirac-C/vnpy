from pathlib import Path
import subprocess


def test_closed_loop_validation_marks_local_readiness_failure_as_blocked():
    """Local validation should record production-only readiness failure without failing local checks."""
    from tools.production.closed_loop_validation import build_report

    def runner(command, repo_root: Path, timeout_seconds: int):
        if command == ("git", "status", "--short"):
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if "vnpy-tradingagents-schema" in command:
            return subprocess.CompletedProcess(command, 1, stdout='{"status":"failed"}', stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    report = build_report(
        repo_root=Path("."),
        profile="local",
        environ={},
        runner=runner,
    )

    readiness = next(check for check in report.checks if check.name == "readiness_cli")
    assert readiness.status == "blocked"
    assert not report.production_ready


def test_closed_loop_validation_passes_production_when_all_gates_pass():
    """Production validation should be ready only when commands and external gates pass."""
    from tools.production.closed_loop_validation import build_report

    def runner(command, repo_root: Path, timeout_seconds: int):
        if command == ("git", "status", "--short"):
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    report = build_report(
        repo_root=Path("."),
        profile="production",
        environ={
            "TRADINGAGENTS_WORKER_FACTORY": "worker_factory:build",
            "OPENAI_API_KEY": "secret",
        },
        runner=runner,
        settings={"tradingagents.api_key_env_var": "OPENAI_API_KEY"},
    )

    assert report.production_ready
    assert {check.status for check in report.checks} == {"passed"}


def test_closed_loop_validation_ignores_generated_validation_evidence():
    """Generated validation result files should not make production profile dirty."""
    from tools.production.closed_loop_validation import build_report

    def runner(command, repo_root: Path, timeout_seconds: int):
        if command == ("git", "status", "--short"):
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=(
                    "?? docs/community/ops/validation_results/podman-e2e/latest/run.log\n"
                    "A  docs/community/ops/validation_results/podman-e2e/latest/pe2e_results.md\n"
                ),
                stderr="",
            )
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    report = build_report(
        repo_root=Path("."),
        profile="production",
        environ={
            "TRADINGAGENTS_WORKER_FACTORY": "worker_factory:build",
            "OPENAI_API_KEY": "secret",
        },
        runner=runner,
        settings={"tradingagents.api_key_env_var": "OPENAI_API_KEY"},
    )

    assert report.worktree_clean
    assert report.dirty_files == []
    assert report.production_ready


def test_closed_loop_validation_accepts_vnpy_worker_factory_setting():
    """Worker factory gate should accept the vn.py UI setting, not only env vars."""
    from tools.production.closed_loop_validation import environment_gate_results

    results = environment_gate_results(
        {"OPENAI_API_KEY": "secret"},
        settings={
            "tradingagents.api_key_env_var": "OPENAI_API_KEY",
            "tradingagents.worker_factory": "vnpy_tradingagents.tradingagents_factory:build",
        },
    )
    worker_gate = next(
        result for result in results if result.name == "tradingagents_worker_factory_env"
    )

    assert worker_gate.status == "passed"
    assert worker_gate.command == "setting:tradingagents.worker_factory"


def test_closed_loop_validation_markdown_contains_conclusion():
    """Markdown report should include enough data for audit review."""
    from tools.production.closed_loop_validation import build_report, render_markdown

    def runner(command, repo_root: Path, timeout_seconds: int):
        if command == ("git", "status", "--short"):
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    report = build_report(
        repo_root=Path("."),
        profile="production",
        environ={
            "TRADINGAGENTS_WORKER_FACTORY": "worker_factory:build",
            "OPENAI_API_KEY": "secret",
        },
        runner=runner,
        settings={"tradingagents.api_key_env_var": "OPENAI_API_KEY"},
    )

    markdown = render_markdown(report)

    assert "# 生产闭环验证结果" in markdown
    assert "production_ready" in markdown
    assert "worktree_clean" in markdown
    assert "readiness_cli" in markdown
