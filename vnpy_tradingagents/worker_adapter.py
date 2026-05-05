import os
from collections.abc import Mapping
from dataclasses import dataclass
from queue import Queue
from threading import Thread
from typing import Protocol, Any

from .config import TradingAgentsWorkerConfig
from .output_validation import validate_worker_response
from .secrets_policy import SecretLeakError, assert_context_has_no_secrets
from .source_policy import SnapshotSourcePolicy
from .worker import TradingAgentsWorkerRequest, TradingAgentsWorkerResponse


FORBIDDEN_CONTEXT_KEYS: frozenset[str] = frozenset(
    {
        "akshare",
        "alpha_vantage",
        "alphavantage",
        "gateway",
        "main_engine",
        "mainengine",
        "qmt",
        "send_order",
        "sendorder",
        "tushare",
        "yfinance",
    }
)


@dataclass(frozen=True)
class TradingAgentsContextPayload:
    """
    Context-only payload passed into a TradingAgents runner.
    """

    run_id: str
    vt_symbol: str
    trade_date: str
    mode: str
    context: dict[str, Any]
    config: TradingAgentsWorkerConfig


class TradingAgentsRunner(Protocol):
    """
    Context-only runner boundary implemented by the real TradingAgents process.
    """

    def run(
        self,
        payload: TradingAgentsContextPayload,
    ) -> Mapping[str, Any] | TradingAgentsWorkerResponse:
        pass


class RunnerTimeoutError(TimeoutError):
    """
    Raised when a TradingAgents runner exceeds the adapter timeout.
    """


class TradingAgentsWorkerAdapter:
    """
    Safe adapter from vn.py worker requests to a context-only TradingAgents runner.
    """

    def __init__(
        self,
        config: TradingAgentsWorkerConfig | None = None,
        runner: TradingAgentsRunner | None = None,
        source_policy: SnapshotSourcePolicy | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        """"""
        self.config: TradingAgentsWorkerConfig = config or TradingAgentsWorkerConfig.from_settings()
        self.runner: TradingAgentsRunner | None = runner
        self.source_policy: SnapshotSourcePolicy = source_policy or SnapshotSourcePolicy.default()
        self.environ: Mapping[str, str] | None = environ

    def run(self, request: TradingAgentsWorkerRequest) -> TradingAgentsWorkerResponse:
        """
        Run TradingAgents through a context-only boundary.
        """
        config: TradingAgentsWorkerConfig = self.config.for_request_mode(request.mode)
        validation = config.validate(self.environ)
        if not validation.ready:
            return _failure_response(request, "configuration_error", validation.error)
        self._sync_api_key_to_process_env(config)

        forbidden_key: str = _find_forbidden_context_key(request.context)
        if forbidden_key:
            return _failure_response(
                request,
                "forbidden_context",
                f"Forbidden provider or trading handle in context: {forbidden_key}",
            )

        try:
            assert_context_has_no_secrets(request.context)
        except SecretLeakError as exc:
            return _failure_response(request, "secret_context", str(exc))

        source_result = self.source_policy.evaluate(request.context)
        if not source_result.allowed:
            return _failure_response(
                request,
                "source_policy_blocked",
                source_result.blocked_reason,
            )

        if self.runner is None:
            return _failure_response(
                request,
                "runner_not_configured",
                "TradingAgents context-only runner is not configured",
            )

        payload = TradingAgentsContextPayload(
            run_id=request.run_id,
            vt_symbol=request.vt_symbol,
            trade_date=request.trade_date,
            mode=request.mode,
            context=request.context,
            config=config,
        )

        try:
            result = self._run_with_timeout(payload)
        except RunnerTimeoutError:
            return _failure_response(
                request,
                "timeout",
                f"TradingAgents runner exceeded {config.timeout_seconds} seconds",
            )
        except Exception as exc:
            return _failure_response(request, "worker_error", str(exc))

        return _response_from_result(request, result)

    def _sync_api_key_to_process_env(self, config: TradingAgentsWorkerConfig) -> None:
        """
        Make keyring-resolved secrets visible to upstream LLM SDKs.
        """
        if self.environ is not None:
            return
        if os.environ.get(config.api_key_env_var):
            return
        api_key = config.resolve_api_key()
        if api_key:
            os.environ[config.api_key_env_var] = api_key

    def _run_with_timeout(
        self,
        payload: TradingAgentsContextPayload,
    ) -> Mapping[str, Any] | TradingAgentsWorkerResponse:
        """
        Execute runner with adapter-level timeout.
        """
        if self.runner is None:
            raise RuntimeError("TradingAgents runner is not configured")

        result_queue: Queue[
            tuple[str, Mapping[str, Any] | TradingAgentsWorkerResponse | BaseException]
        ] = Queue(maxsize=1)

        def invoke_runner() -> None:
            try:
                result_queue.put(("result", self.runner.run(payload)))
            except BaseException as exc:
                result_queue.put(("error", exc))

        thread = Thread(
            target=invoke_runner,
            name=f"tradingagents-runner-{payload.run_id}",
            daemon=True,
        )
        thread.start()
        timeout_seconds: float = float(payload.config.timeout_seconds)
        thread.join(timeout=timeout_seconds)
        if thread.is_alive():
            raise RunnerTimeoutError(
                f"TradingAgents runner exceeded {timeout_seconds:g} seconds"
            )

        kind, value = result_queue.get_nowait()
        if kind == "error":
            raise value
        return value


def _response_from_result(
    request: TradingAgentsWorkerRequest,
    result: Mapping[str, Any] | TradingAgentsWorkerResponse,
) -> TradingAgentsWorkerResponse:
    """
    Normalize runner output into the vn.py worker response contract.
    """
    if isinstance(result, TradingAgentsWorkerResponse):
        return validate_worker_response(result)

    raw_state: dict[str, Any] = dict(result.get("raw_state") or {})
    response = TradingAgentsWorkerResponse(
        run_id=request.run_id,
        vt_symbol=request.vt_symbol,
        rating=str(result.get("rating", "Unavailable")),
        confidence=float(result.get("confidence") or 0),
        report=str(result.get("report", "")),
        raw_state=raw_state,
        action=str(result.get("action", "hold")),
        target_weight_hint=_optional_float(result.get("target_weight_hint")),
        holding_period_hint=str(result.get("holding_period_hint") or ""),
        risk_notes=str(result.get("risk_notes") or ""),
    )
    return validate_worker_response(response)


def _failure_response(
    request: TradingAgentsWorkerRequest,
    error_type: str,
    error_message: str,
) -> TradingAgentsWorkerResponse:
    """
    Build an auditable failed worker response.
    """
    return TradingAgentsWorkerResponse(
        run_id=request.run_id,
        vt_symbol=request.vt_symbol,
        rating="Unavailable",
        confidence=0,
        report=f"TradingAgents worker failed: {error_message}",
        raw_state={
            "status": "failed",
            "error_type": error_type,
            "error_message": error_message,
            "run_id": request.run_id,
            "vt_symbol": request.vt_symbol,
            "trade_date": request.trade_date,
            "mode": request.mode,
            "context_keys": sorted(str(key) for key in request.context),
        },
        action="hold",
        risk_notes=error_message,
    )


def failed_worker_response(
    request: TradingAgentsWorkerRequest,
    error_type: str,
    error_message: str,
) -> TradingAgentsWorkerResponse:
    """
    Public helper for process/service boundaries to create auditable failures.
    """
    return _failure_response(request, error_type, error_message)


def _find_forbidden_context_key(value: Any, path: str = "") -> str:
    """
    Find forbidden provider or trading handles inside a nested context.
    """
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text: str = str(key)
            key_path: str = f"{path}.{key_text}" if path else key_text
            if key_text.strip().lower() in FORBIDDEN_CONTEXT_KEYS:
                return key_path

            found: str = _find_forbidden_context_key(child, key_path)
            if found:
                return found

    elif isinstance(value, list):
        for index, child in enumerate(value):
            found = _find_forbidden_context_key(child, f"{path}[{index}]")
            if found:
                return found

    return ""


def _optional_float(value: Any) -> float | None:
    """
    Convert optional numeric output.
    """
    if value is None:
        return None
    return float(value)
