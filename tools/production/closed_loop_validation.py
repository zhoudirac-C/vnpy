from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from vnpy.trader.setting import SETTINGS


Status = str
CommandRunner = Callable[[Sequence[str], Path, int], subprocess.CompletedProcess[str]]
IGNORED_DIRTY_PREFIXES: tuple[str, ...] = (
    "docs/community/ops/validation_results/",
)


@dataclass(frozen=True)
class CommandSpec:
    """One command-based validation check."""

    name: str
    command: tuple[str, ...]
    required_local: bool = True
    required_production: bool = True
    timeout_seconds: int = 120


@dataclass(frozen=True)
class CheckResult:
    """Validation check result persisted in reports."""

    name: str
    status: Status
    command: str
    exit_code: int | None
    duration_seconds: float
    required_local: bool
    required_production: bool
    message: str
    stdout_tail: str = ""
    stderr_tail: str = ""


@dataclass(frozen=True)
class ValidationReport:
    """Full validation report."""

    generated_at: str
    profile: str
    repo_root: str
    branch: str
    commit: str
    worktree_clean: bool
    dirty_files: list[str]
    production_ready: bool
    checks: list[CheckResult]

    def status_counts(self) -> dict[str, int]:
        """Return result counts by status."""
        counts: dict[str, int] = {}
        for check in self.checks:
            counts[check.status] = counts.get(check.status, 0) + 1
        return counts


LOCAL_COMMANDS: tuple[CommandSpec, ...] = (
    CommandSpec(
        name="ruff_core",
        command=(
            "uv",
            "run",
            "--with",
            "ruff",
            "ruff",
            "check",
            "vnpy/alpha",
            "vnpy_router",
            "vnpy_tradingagents",
            "tests/test_alpha_optional_imports.py",
            "tests/test_data_router.py",
            "tests/test_tradingagents_toolkit.py",
        ),
    ),
    CommandSpec(
        name="pytest_non_alpha",
        command=(
            "uv",
            "run",
            "--with",
            "pytest",
            "--with",
            "psycopg2-binary",
            "pytest",
            "tests",
            "-q",
            "--ignore=tests/test_alpha101.py",
        ),
    ),
    CommandSpec(
        name="alpha_optional_imports",
        command=(
            "uv",
            "run",
            "--with",
            "polars[rtcompat]",
            "--with",
            "pytest",
            "pytest",
            "tests/test_alpha_optional_imports.py",
            "-q",
        ),
    ),
    CommandSpec(
        name="alpha101_smoke",
        command=(
            "uv",
            "run",
            "--with",
            "polars[rtcompat]",
            "--with",
            "scipy",
            "--with",
            "pytest",
            "pytest",
            "tests/test_alpha101.py::TestAlpha101::test_alpha1",
            "-q",
        ),
    ),
    CommandSpec(
        name="compileall_core",
        command=("uv", "run", "python", "-m", "compileall", "vnpy/alpha", "vnpy_router", "vnpy_tradingagents", "-q"),
    ),
    CommandSpec(
        name="diff_check",
        command=("git", "diff", "--check"),
    ),
)


PRODUCTION_COMMANDS: tuple[CommandSpec, ...] = (
    CommandSpec(
        name="readiness_cli",
        command=(
            "uv",
            "run",
            "--with",
            "psycopg2-binary",
            "vnpy-tradingagents-schema",
            "readiness",
            "--json",
        ),
        required_local=False,
        required_production=True,
    ),
)


def main(argv: Sequence[str] | None = None) -> int:
    """Run production closed-loop validation and optionally write reports."""
    parser = argparse.ArgumentParser(prog="closed-loop-validation")
    parser.add_argument("--profile", choices=("local", "production"), default="local")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output", default="")
    parser.add_argument("--json-output", default="")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    report = build_report(repo_root=repo_root, profile=args.profile, environ=os.environ)

    markdown = render_markdown(report)
    print(markdown)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")

    if args.json_output:
        json_path = Path(args.json_output)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(report_to_dict(report), ensure_ascii=False, indent=2), encoding="utf-8")

    return 0 if report.production_ready or args.profile == "local" else 1


def build_report(
    repo_root: Path,
    profile: str,
    environ: Mapping[str, str],
    runner: CommandRunner | None = None,
    settings: Mapping[str, Any] | None = None,
) -> ValidationReport:
    """Build a validation report by running local checks and production gates."""
    command_runner = runner or _run_subprocess
    checks: list[CheckResult] = []

    for spec in LOCAL_COMMANDS:
        checks.append(run_command(spec, repo_root, profile, command_runner))

    for spec in PRODUCTION_COMMANDS:
        checks.append(run_command(spec, repo_root, profile, command_runner))

    checks.extend(environment_gate_results(environ, settings=settings))
    dirty_files = _git_dirty_files(repo_root, command_runner)
    production_ready = _is_production_ready(checks) and not dirty_files
    return ValidationReport(
        generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        profile=profile,
        repo_root=str(repo_root),
        branch=_git_value(repo_root, ("git", "branch", "--show-current"), command_runner),
        commit=_git_value(repo_root, ("git", "rev-parse", "--short", "HEAD"), command_runner),
        worktree_clean=not dirty_files,
        dirty_files=dirty_files,
        production_ready=production_ready,
        checks=checks,
    )


def run_command(
    spec: CommandSpec,
    repo_root: Path,
    profile: str,
    runner: CommandRunner,
) -> CheckResult:
    """Run one command and normalize the result."""
    start = time.monotonic()
    command_text = " ".join(spec.command)
    try:
        completed = runner(spec.command, repo_root, spec.timeout_seconds)
        duration = round(time.monotonic() - start, 3)
    except subprocess.TimeoutExpired as exc:
        return CheckResult(
            name=spec.name,
            status="failed",
            command=command_text,
            exit_code=None,
            duration_seconds=round(time.monotonic() - start, 3),
            required_local=spec.required_local,
            required_production=spec.required_production,
            message=f"timed out after {exc.timeout}s",
            stdout_tail="",
            stderr_tail="",
        )

    status: Status = "passed" if completed.returncode == 0 else "failed"
    if profile == "local" and not spec.required_local and completed.returncode != 0:
        status = "blocked"

    return CheckResult(
        name=spec.name,
        status=status,
        command=command_text,
        exit_code=completed.returncode,
        duration_seconds=duration,
        required_local=spec.required_local,
        required_production=spec.required_production,
        message=_message_for_command(spec, status),
        stdout_tail=_tail(completed.stdout),
        stderr_tail=_tail(completed.stderr),
    )


def environment_gate_results(
    environ: Mapping[str, str],
    settings: Mapping[str, Any] | None = None,
) -> list[CheckResult]:
    """Return production-only gate results that depend on external runtime config."""
    source: Mapping[str, Any] = SETTINGS if settings is None else settings
    results: list[CheckResult] = [_worker_factory_gate(environ, source)]

    api_key_env_name = str(source.get("tradingagents.api_key_env_var", "OPENAI_API_KEY"))
    api_key_value = environ.get(api_key_env_name, "").strip()
    results.append(
        CheckResult(
            name="llm_api_key_env",
            status="passed" if api_key_value else "blocked",
            command=f"env:{api_key_env_name}",
            exit_code=None,
            duration_seconds=0,
            required_local=False,
            required_production=True,
            message=(
                "LLM API key environment variable is configured"
                if api_key_value
                else f"{api_key_env_name} is not configured in this validation environment"
            ),
        )
    )
    return results


def _worker_factory_gate(
    environ: Mapping[str, str],
    settings: Mapping[str, Any],
) -> CheckResult:
    env_value = environ.get("TRADINGAGENTS_WORKER_FACTORY", "").strip()
    setting_value = str(settings.get("tradingagents.worker_factory", "")).strip()

    if env_value:
        return CheckResult(
            name="tradingagents_worker_factory_env",
            status="passed",
            command="env:TRADINGAGENTS_WORKER_FACTORY",
            exit_code=None,
            duration_seconds=0,
            required_local=False,
            required_production=True,
            message="context-only worker factory is configured",
        )

    if setting_value:
        return CheckResult(
            name="tradingagents_worker_factory_env",
            status="passed",
            command="setting:tradingagents.worker_factory",
            exit_code=None,
            duration_seconds=0,
            required_local=False,
            required_production=True,
            message="context-only worker factory is configured in vn.py settings",
        )

    return CheckResult(
        name="tradingagents_worker_factory_env",
        status="blocked",
        command="env:TRADINGAGENTS_WORKER_FACTORY",
        exit_code=None,
        duration_seconds=0,
        required_local=False,
        required_production=True,
        message="TRADINGAGENTS_WORKER_FACTORY or tradingagents.worker_factory is not configured in this validation environment",
    )


def render_markdown(report: ValidationReport) -> str:
    """Render a report as Markdown."""
    counts = report.status_counts()
    lines = [
        "# 生产闭环验证结果",
        "",
        f"- 生成时间：`{report.generated_at}`",
        f"- profile：`{report.profile}`",
        f"- branch：`{report.branch}`",
        f"- commit：`{report.commit}`",
        f"- worktree_clean：`{str(report.worktree_clean).lower()}`",
        f"- production_ready：`{str(report.production_ready).lower()}`",
        f"- 结果计数：`{json.dumps(counts, ensure_ascii=False, sort_keys=True)}`",
        "",
        "## 命令和门禁结果",
        "",
        "| 检查项 | 状态 | 生产必需 | 命令/门禁 | 说明 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for check in report.checks:
        lines.append(
            "| "
            + " | ".join(
                [
                    check.name,
                    check.status,
                    "yes" if check.required_production else "no",
                    f"`{check.command}`",
                    check.message.replace("|", "/"),
                ]
            )
            + " |"
        )

    if report.dirty_files:
        lines.extend(
            [
                "",
                "## 工作区状态",
                "",
                "本次验证运行时工作区存在未提交变更：",
                "",
            ]
        )
        lines.extend(f"- `{item}`" for item in report.dirty_files)

    lines.extend(
        [
            "",
            "## 结论",
            "",
            _conclusion(report),
            "",
            "## 备注",
            "",
            "- 本地 profile 的目标是证明代码级闭环、smoke、依赖边界和降级路径可重复验证。",
            "- production profile 必须接入真实 PostgreSQL、真实 context-only TradingAgents Worker、真实 API key 和真实 provider 配置后再运行。",
            "- 新闻/社媒实时 provider 本轮不纳入验证范围；缺失时应保持 degraded，不阻塞主交易链路。",
            "",
        ]
    )
    return "\n".join(lines)


def report_to_dict(report: ValidationReport) -> dict[str, Any]:
    """Convert report to JSON-serializable dict."""
    data = asdict(report)
    data["status_counts"] = report.status_counts()
    return data


def _run_subprocess(
    command: Sequence[str],
    repo_root: Path,
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    """Default subprocess runner."""
    return subprocess.run(
        list(command),
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )


def _git_value(repo_root: Path, command: Sequence[str], runner: CommandRunner) -> str:
    """Return a small git value for report metadata."""
    completed = runner(command, repo_root, 10)
    if completed.returncode != 0:
        return "unknown"
    return completed.stdout.strip() or "unknown"


def _is_production_ready(checks: Sequence[CheckResult]) -> bool:
    """Production is ready only when every production-required check passes."""
    for check in checks:
        if check.required_production and check.status != "passed":
            return False
    return True


def _message_for_command(spec: CommandSpec, status: Status) -> str:
    """Return a concise command result message."""
    if status == "passed":
        return "command passed"
    if status == "blocked":
        return "command failed in local validation; treated as production gate not satisfied"
    return "command failed"


def _tail(text: str, limit: int = 2000) -> str:
    """Keep report payloads compact."""
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[-limit:]


def _conclusion(report: ValidationReport) -> str:
    """Render the top-level conclusion."""
    if report.production_ready:
        return "本次验证满足 production profile 的所有生产必需门禁。"
    blocked = [check.name for check in report.checks if check.required_production and check.status != "passed"]
    if not report.worktree_clean:
        blocked.append("worktree_clean")
    return "本次验证未达到生产可用准入；未通过或阻塞的生产门禁：" + ", ".join(blocked)


def _git_dirty_files(repo_root: Path, runner: CommandRunner) -> list[str]:
    """Return dirty worktree lines from git status --short."""
    completed = runner(("git", "status", "--short"), repo_root, 10)
    if completed.returncode != 0:
        return ["git status failed"]
    return [
        line
        for line in completed.stdout.splitlines()
        if line.strip() and not _is_ignored_dirty_line(line)
    ]


def _is_ignored_dirty_line(line: str) -> bool:
    """Return whether a dirty worktree line only points at generated validation evidence."""
    path = line[3:].strip() if len(line) > 3 else line.strip()
    if " -> " in path:
        path = path.split(" -> ", 1)[1].strip()
    return any(path.startswith(prefix) for prefix in IGNORED_DIRTY_PREFIXES)


if __name__ == "__main__":
    raise SystemExit(main())
