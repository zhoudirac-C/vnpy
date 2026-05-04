from collections.abc import Mapping
from typing import Any


SECRET_KEYWORDS: tuple[str, ...] = (
    "api_key",
    "apikey",
    "secret",
    "token",
    "password",
    "authorization",
    "openai_api_key",
)


class SecretLeakError(ValueError):
    """
    Raised when a TradingAgents context contains sensitive material.
    """


def mask_secret(value: str) -> str:
    """
    Mask a secret for diagnostics and logs.
    """
    text = str(value)
    if len(text) <= 4:
        return "*" * len(text)
    if len(text) <= 8:
        return f"{text[:1]}{'*' * (len(text) - 2)}{text[-1:]}"
    return f"{text[:4]}{'*' * max(len(text) - 6, 1)}{text[-2:]}"


def sanitize_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    """
    Return a copy with sensitive fields masked.
    """
    sanitized: dict[str, Any] = {}
    for key, child in value.items():
        if _is_secret_key(str(key)):
            sanitized[str(key)] = mask_secret(str(child))
        elif isinstance(child, Mapping):
            sanitized[str(key)] = sanitize_mapping(child)
        elif isinstance(child, list):
            sanitized[str(key)] = [
                sanitize_mapping(item) if isinstance(item, Mapping) else item
                for item in child
            ]
        else:
            sanitized[str(key)] = child
    return sanitized


def assert_context_has_no_secrets(context: Mapping[str, Any]) -> None:
    """
    Reject worker context containing likely secret keys.
    """
    leaked_path = _find_secret_path(context)
    if leaked_path:
        raise SecretLeakError(f"secret field is not allowed in TradingAgents context: {leaked_path}")


def _find_secret_path(value: Any, path: str = "") -> str:
    """
    Find likely secret keys in nested dictionaries.
    """
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            key_path = f"{path}.{key_text}" if path else key_text
            if _is_secret_key(key_text):
                return key_path
            found = _find_secret_path(child, key_path)
            if found:
                return found
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found = _find_secret_path(child, f"{path}[{index}]")
            if found:
                return found
    return ""


def _is_secret_key(key: str) -> bool:
    """
    Return whether a key name is likely sensitive.
    """
    normalized = key.strip().lower()
    return any(keyword in normalized for keyword in SECRET_KEYWORDS)
