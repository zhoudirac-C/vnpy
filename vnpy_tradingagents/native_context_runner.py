from collections.abc import Callable, Mapping, Sequence
from typing import Any

from .prompts import build_worker_system_prompt
from .secrets_policy import assert_context_has_no_secrets
from .worker_adapter import FORBIDDEN_CONTEXT_KEYS


class ContextRunnerError(RuntimeError):
    """
    Raised when a native TradingAgents runner cannot be used safely.
    """


class AShareContextOnlyRunner:
    """
    Thin wrapper that forces native TradingAgents calls through local A-share context.
    """

    def __init__(
        self,
        native_runner: Any,
        required_context_sections: Sequence[str] = ("market",),
        prompt_factory: Callable[[str], str] = build_worker_system_prompt,
    ) -> None:
        """"""
        self.native_runner: Any = native_runner
        self.required_context_sections: tuple[str, ...] = tuple(required_context_sections)
        self.prompt_factory: Callable[[str], str] = prompt_factory

    def run(self, native_input: Mapping[str, Any]) -> Any:
        """
        Validate context-only input and invoke the native runner.
        """
        context = dict(native_input.get("context") or {})
        _assert_context_only(native_input, context, self.required_context_sections)

        safe_input: dict[str, Any] = dict(native_input)
        safe_input["context"] = context
        safe_input.setdefault("system_prompt", self.prompt_factory(str(native_input.get("mode") or "")))
        return _invoke_native(self.native_runner, safe_input)


def _assert_context_only(
    native_input: Mapping[str, Any],
    context: Mapping[str, Any],
    required_context_sections: Sequence[str],
) -> None:
    """
    Reject native runner input that contains trading handles or missing snapshots.
    """
    for key in native_input:
        key_text = str(key).strip().lower()
        if key_text in FORBIDDEN_CONTEXT_KEYS:
            raise ContextRunnerError(f"forbidden native input key: {key}")

    for section in required_context_sections:
        value = context.get(section)
        if value in (None, {}, []):
            raise ContextRunnerError(f"missing required context section: {section}")

    assert_context_has_no_secrets(context)


def _invoke_native(native_runner: Any, safe_input: Mapping[str, Any]) -> Any:
    """
    Invoke only context-taking native runner shapes.
    """
    if hasattr(native_runner, "run"):
        return native_runner.run(dict(safe_input))
    if hasattr(native_runner, "invoke"):
        return native_runner.invoke(dict(safe_input))
    if callable(native_runner):
        return native_runner(dict(safe_input))
    raise ContextRunnerError("native runner must expose run/invoke/callable context interface")
