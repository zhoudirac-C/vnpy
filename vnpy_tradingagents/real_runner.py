from collections.abc import Callable, Mapping
from dataclasses import asdict, is_dataclass
from typing import Any

from .text_output_parser import parse_free_text_worker_output
from .worker_adapter import TradingAgentsContextPayload


DependencyLoader = Callable[[], Any]


class UnsupportedRunnerShapeError(RuntimeError):
    """
    Raised when a native runner would bypass context-only input.
    """


class TradingAgentsRunnerAdapter:
    """
    Context-only adapter around a native TradingAgents runner.
    """

    def __init__(
        self,
        native_runner: Any | None = None,
        dependency_loader: DependencyLoader | None = None,
        allow_legacy_propagate: bool = False,
    ) -> None:
        """"""
        self.native_runner: Any | None = native_runner
        self.dependency_loader: DependencyLoader = dependency_loader or _default_dependency_loader
        self.allow_legacy_propagate: bool = allow_legacy_propagate

    def run(self, payload: TradingAgentsContextPayload) -> Mapping[str, Any]:
        """
        Run the native TradingAgents implementation with context-only input.
        """
        try:
            native_runner: Any = self.native_runner or self.dependency_loader()
        except ModuleNotFoundError:
            return _dependency_failure(payload)

        native_input: dict[str, Any] = _native_input(payload)
        try:
            result: Any = _call_native_runner(
                native_runner,
                native_input,
                allow_legacy_propagate=self.allow_legacy_propagate,
            )
        except UnsupportedRunnerShapeError as exc:
            return _unsupported_runner_failure(payload, str(exc))
        return _normalize_native_result(result)


def _native_input(payload: TradingAgentsContextPayload) -> dict[str, Any]:
    """
    Convert vn.py payload into native TradingAgents input without trading handles.
    """
    checkpoint_dir = payload.config.checkpoint_path_for(
        payload.run_id,
        payload.vt_symbol,
        payload.trade_date,
    )
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    return {
        "run_id": payload.run_id,
        "symbol": payload.vt_symbol,
        "trade_date": payload.trade_date,
        "mode": payload.mode,
        "context": payload.context,
        "llm_provider": payload.config.llm_provider,
        "model": payload.config.model,
        "backend_url": payload.config.backend_url,
        "thinking_type": payload.config.thinking_type,
        "timeout_seconds": payload.config.timeout_seconds,
        "max_retries": payload.config.max_retries,
        "max_completion_tokens": payload.config.max_completion_tokens,
        "checkpoint_dir": str(checkpoint_dir),
    }


def _call_native_runner(
    native_runner: Any,
    native_input: dict[str, Any],
    *,
    allow_legacy_propagate: bool = False,
) -> Any:
    """
    Call a native runner object, supporting common run/invoke/call shapes.
    """
    if hasattr(native_runner, "run"):
        return native_runner.run(native_input)
    if hasattr(native_runner, "invoke"):
        return native_runner.invoke(native_input)
    if hasattr(native_runner, "propagate"):
        if not allow_legacy_propagate:
            raise UnsupportedRunnerShapeError(
                "TradingAgentsGraph.propagate(symbol, date) bypasses context-only input; "
                "wrap the graph with AShareContextOnlyRunner or enable legacy mode only for tests"
            )
        return native_runner.propagate(
            native_input["symbol"],
            native_input["trade_date"],
        )
    if callable(native_runner):
        return native_runner(native_input)
    raise RuntimeError(
        "TradingAgents native runner has no run/invoke/propagate/call interface"
    )


def _normalize_native_result(result: Any) -> Mapping[str, Any]:
    """
    Normalize native TradingAgents output into a mapping expected by worker adapter.
    """
    if _is_state_decision_pair(result):
        state, decision = result[0], result[1]
        return _mapping_from_decision(decision, state)

    mapping = _to_mapping(result)
    if mapping is not None:
        return _normalize_mapping(mapping, result)

    if isinstance(result, str):
        return _mapping_from_decision(result, None)

    raise RuntimeError("TradingAgents native runner returned unsupported output")


def _normalize_mapping(mapping: Mapping[str, Any], original: Any) -> Mapping[str, Any]:
    """
    Normalize structured dict/Pydantic output from a native runner.
    """
    if "final_trade_decision" in mapping and "action" not in mapping:
        return _mapping_from_decision(mapping["final_trade_decision"], mapping)

    normalized: dict[str, Any] = dict(mapping)
    decision_text = str(
        mapping.get("decision")
        or mapping.get("recommendation")
        or mapping.get("signal")
        or mapping.get("action")
        or ""
    )

    if "action" not in normalized:
        normalized["action"] = _action_from_decision(decision_text)

    if "rating" not in normalized:
        normalized["rating"] = _rating_from_action(str(normalized["action"]))

    if "confidence" not in normalized:
        normalized["confidence"] = mapping.get("score") or mapping.get("probability") or 0

    if "report" not in normalized:
        normalized["report"] = str(
            mapping.get("report")
            or mapping.get("analysis")
            or mapping.get("reasoning")
            or mapping.get("summary")
            or decision_text
        )

    parsed = parse_free_text_worker_output(str(normalized.get("report") or ""))
    if parsed.get("rating") and "rating" not in mapping:
        normalized["rating"] = parsed["rating"]
    if parsed.get("action") and "action" not in mapping:
        normalized["action"] = parsed["action"]
    if parsed.get("confidence") is not None and "confidence" not in mapping:
        normalized["confidence"] = parsed["confidence"]
    if parsed.get("risk_notes") and "risk_notes" not in mapping:
        normalized["risk_notes"] = parsed["risk_notes"]

    raw_state = _to_mapping(mapping.get("raw_state"))
    if raw_state is None:
        raw_state = {
            "status": "ok",
            "native_output_type": type(original).__name__,
        }
    if parsed.get("text_output_parsed"):
        raw_state = dict(raw_state)
        raw_state["text_output_parsed"] = True
    normalized["raw_state"] = _json_safe(raw_state)
    return normalized


def _mapping_from_decision(
    decision: Any,
    state: Any,
) -> Mapping[str, Any]:
    """
    Convert an upstream TradingAgents decision into the worker adapter mapping shape.
    """
    decision_mapping = _to_mapping(decision)
    if decision_mapping is not None:
        return _normalize_mapping(decision_mapping, decision)

    decision_text = str(decision)
    state_mapping = _to_mapping(state)
    report = decision_text
    if state_mapping is not None and state_mapping.get("final_trade_decision"):
        report = str(state_mapping["final_trade_decision"])

    parsed = parse_free_text_worker_output(report)
    action = str(parsed.get("action") or _action_from_decision(decision_text))
    raw_state = _state_summary(state)
    if parsed.get("text_output_parsed"):
        raw_state["text_output_parsed"] = True

    return {
        "rating": str(parsed.get("rating") or _rating_from_action(action)),
        "confidence": parsed.get("confidence", 0),
        "report": report,
        "action": action,
        "risk_notes": str(parsed.get("risk_notes") or ""),
        "raw_state": raw_state,
    }


def _is_state_decision_pair(result: Any) -> bool:
    """
    Return True for TradingAgentsGraph.propagate-style ``(state, decision)`` output.
    """
    return isinstance(result, tuple | list) and len(result) >= 2


def _to_mapping(value: Any) -> Mapping[str, Any] | None:
    """
    Convert common structured-output objects into mappings.
    """
    if isinstance(value, Mapping):
        return value
    if value is None:
        return None
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, Mapping):
            return dumped

    dict_method = getattr(value, "dict", None)
    if callable(dict_method):
        dumped = dict_method()
        if isinstance(dumped, Mapping):
            return dumped

    return None


def _action_from_decision(decision: str) -> str:
    """
    Map upstream decision text into the internal action enum.
    """
    text = decision.upper()
    if "SELL" in text:
        return "sell"
    if "UNDERWEIGHT" in text or "REDUCE" in text:
        return "reduce"
    if "BUY" in text or "OVERWEIGHT" in text:
        return "buy"
    if "WATCH" in text:
        return "watch"
    if "HOLD" in text:
        return "hold"
    return "hold"


def _rating_from_action(action: str) -> str:
    """
    Map internal action into the TradingAgents five-tier rating scale.
    """
    normalized = action.strip().lower()
    if normalized == "buy":
        return "Buy"
    if normalized == "sell":
        return "Sell"
    if normalized == "reduce":
        return "Underweight"
    if normalized in {"hold", "watch"}:
        return "Hold"
    return "Unavailable"


def _state_summary(state: Any) -> dict[str, Any]:
    """
    Keep raw_state audit-friendly without storing full LangGraph state objects.
    """
    summary: dict[str, Any] = {
        "status": "ok",
        "native_state_type": type(state).__name__,
    }
    state_mapping = _to_mapping(state)
    if state_mapping is not None:
        for key in ("company_of_interest", "trade_date", "final_trade_decision"):
            if key in state_mapping:
                summary[key] = _json_safe(state_mapping[key])
    return summary


def _json_safe(value: Any) -> Any:
    """
    Convert nested values into JSON-safe audit data.
    """
    if isinstance(value, Mapping):
        return {str(key): _json_safe(child) for key, child in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(child) for child in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def _dependency_failure(payload: TradingAgentsContextPayload) -> dict[str, Any]:
    """
    Return a structured dependency failure without raising through worker boundaries.
    """
    message: str = "TradingAgents dependency is not available"
    return {
        "rating": "Unavailable",
        "confidence": 0,
        "report": f"TradingAgents runner failed: {message}",
        "action": "hold",
        "risk_notes": message,
        "raw_state": {
            "status": "failed",
            "error_type": "dependency_error",
            "error_message": message,
            "run_id": payload.run_id,
            "vt_symbol": payload.vt_symbol,
            "trade_date": payload.trade_date,
        },
    }


def _unsupported_runner_failure(
    payload: TradingAgentsContextPayload,
    message: str,
) -> dict[str, Any]:
    """
    Return a structured failure when a native runner is not context-only safe.
    """
    return {
        "rating": "Unavailable",
        "confidence": 0,
        "report": f"TradingAgents runner failed: {message}",
        "action": "hold",
        "risk_notes": message,
        "raw_state": {
            "status": "failed",
            "error_type": "unsupported_runner_shape",
            "error_message": message,
            "run_id": payload.run_id,
            "vt_symbol": payload.vt_symbol,
            "trade_date": payload.trade_date,
        },
    }


def _default_dependency_loader() -> Any:
    """
    Load the installed TradingAgents package.
    """
    return __import__("tradingagents")
