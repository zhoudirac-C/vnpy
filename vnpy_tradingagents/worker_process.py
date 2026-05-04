import json
import os
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import asdict
from typing import Protocol, Any

from .config import TradingAgentsWorkerConfig
from .real_runner import TradingAgentsRunnerAdapter
from .worker import TradingAgentsWorkerRequest, TradingAgentsWorkerResponse
from .worker_adapter import TradingAgentsWorkerAdapter, failed_worker_response


class Worker(Protocol):
    """
    Worker process protocol.
    """

    def run(self, request: TradingAgentsWorkerRequest) -> TradingAgentsWorkerResponse:
        pass


class SubprocessTradingAgentsWorker:
    """
    Worker client that invokes a JSON stdin/stdout subprocess.
    """

    def __init__(
        self,
        command: Sequence[str],
        timeout_seconds: float,
        max_retries: int = 0,
    ) -> None:
        """"""
        self.command: list[str] = list(command)
        self.timeout_seconds: float = timeout_seconds
        self.max_retries: int = max_retries

    def run(self, request: TradingAgentsWorkerRequest) -> TradingAgentsWorkerResponse:
        """
        Run worker subprocess and parse JSON response.
        """
        request_json: str = request_to_json(request)
        last_error: str = ""

        for attempt in range(self.max_retries + 1):
            try:
                completed = subprocess.run(
                    self.command,
                    input=request_json,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                last_error = f"worker subprocess timed out on attempt {attempt + 1}"
                continue

            if completed.returncode != 0:
                last_error = completed.stderr.strip() or (
                    f"worker subprocess exited with code {completed.returncode}"
                )
                continue

            try:
                return response_from_json(completed.stdout)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                last_error = f"invalid worker JSON response: {exc}"

        error_type: str = "timeout" if "timed out" in last_error else "subprocess_error"
        return failed_worker_response(request, error_type, last_error or "worker failed")


def run_worker_process_json(input_text: str, worker: Worker) -> str:
    """
    Run a worker against a JSON request payload and return JSON response text.
    """
    request: TradingAgentsWorkerRequest = request_from_json(input_text)
    try:
        response: TradingAgentsWorkerResponse = worker.run(request)
    except Exception as exc:
        response = failed_worker_response(request, "worker_exception", str(exc))
    return response_to_json(response)


def request_from_json(input_text: str) -> TradingAgentsWorkerRequest:
    """
    Parse a worker request from JSON.
    """
    data: dict[str, Any] = json.loads(input_text)
    return TradingAgentsWorkerRequest(
        run_id=str(data["run_id"]),
        vt_symbol=str(data["vt_symbol"]),
        trade_date=str(data["trade_date"]),
        mode=str(data["mode"]),
        context=dict(data.get("context") or {}),
    )


def response_from_json(input_text: str) -> TradingAgentsWorkerResponse:
    """
    Parse a worker response from JSON.
    """
    data: dict[str, Any] = json.loads(input_text)
    return TradingAgentsWorkerResponse(
        run_id=str(data["run_id"]),
        vt_symbol=str(data["vt_symbol"]),
        rating=str(data["rating"]),
        confidence=float(data["confidence"]),
        report=str(data["report"]),
        raw_state=dict(data.get("raw_state") or {}),
        action=str(data.get("action", "hold")),
        target_weight_hint=data.get("target_weight_hint"),
        holding_period_hint=str(data.get("holding_period_hint") or ""),
        risk_notes=str(data.get("risk_notes") or ""),
    )


def request_to_json(request: TradingAgentsWorkerRequest) -> str:
    """
    Serialize a worker request to JSON.
    """
    return json.dumps(asdict(request), ensure_ascii=False)


def response_to_json(response: TradingAgentsWorkerResponse) -> str:
    """
    Serialize a worker response to JSON.
    """
    return json.dumps(asdict(response), ensure_ascii=False)


def main(worker: Worker | None = None) -> int:
    """
    CLI entry point for JSON stdin/stdout worker processes.
    """
    if worker is None:
        worker = load_configured_worker()

    if worker is None:
        input_text = sys.stdin.read()
        request = request_from_json(input_text)
        response = failed_worker_response(
            request,
            "runner_not_configured",
            "No TradingAgents worker implementation configured for this CLI process",
        )
        sys.stdout.write(response_to_json(response))
        return 1

    sys.stdout.write(run_worker_process_json(sys.stdin.read(), worker))
    return 0


def load_configured_worker() -> Worker | None:
    """
    Load a context-only worker from TRADINGAGENTS_WORKER_FACTORY.

    The factory value must be ``module:function`` and return a runner object
    that accepts context input through run/invoke/callable.
    """
    factory_path: str = os.environ.get("TRADINGAGENTS_WORKER_FACTORY", "").strip()
    if not factory_path:
        return None

    try:
        module_name, function_name = factory_path.split(":", 1)
        module = __import__(module_name, fromlist=[function_name])
        factory = getattr(module, function_name)
        native_runner = factory()
    except Exception:
        return None

    return TradingAgentsWorkerAdapter(
        config=TradingAgentsWorkerConfig.from_settings(),
        runner=TradingAgentsRunnerAdapter(native_runner=native_runner),
    )


if __name__ == "__main__":
    raise SystemExit(main())
