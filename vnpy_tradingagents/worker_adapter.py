from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass
from typing import Protocol, Any

from .config import TradingAgentsWorkerConfig
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
        validation = self.config.validate(self.environ)
        if not validation.ready:
            return _failure_response(request, "configuration_error", validation.error)

        forbidden_key: str = _find_forbidden_context_key(request.context)
        if forbidden_key:
            return _failure_response(
                request,
                "forbidden_context",
                f"Forbidden provider or trading handle in context: {forbidden_key}",
            )

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
            config=self.config,
        )

        try:
            result = self._run_with_timeout(payload)
        except FutureTimeout:
            return _failure_response(
                request,
                "timeout",
                f"TradingAgents runner exceeded {self.config.timeout_seconds} seconds",
            )
        except Exception as exc:
            return _failure_response(request, "worker_error", str(exc))

        return _response_from_result(request, result)

    def _run_with_timeout(
        self,
        payload: TradingAgentsContextPayload,
    ) -> Mapping[str, Any] | TradingAgentsWorkerResponse:
        """
        Execute runner with adapter-level timeout.
        """
        if self.runner is None:
            raise RuntimeError("TradingAgents runner is not configured")

        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(self.runner.run, payload)
        try:
            return future.result(timeout=float(self.config.timeout_seconds))
        finally:
            executor.shutdown(wait=False, cancel_futures=True)


def _response_from_result(
    request: TradingAgentsWorkerRequest,
    result: Mapping[str, Any] | TradingAgentsWorkerResponse,
) -> TradingAgentsWorkerResponse:
    """
    Normalize runner output into the vn.py worker response contract.
    """
    if isinstance(result, TradingAgentsWorkerResponse):
        return result

    raw_state: dict[str, Any] = dict(result.get("raw_state") or {})
    return TradingAgentsWorkerResponse(
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
