from collections.abc import Mapping
import re
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

SECRET_VALUE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:api[_-]?key|openai[_-]?api[_-]?key|secret|password|authorization|token)\b\s*[:=]\s*"
        r"([A-Za-z0-9._~+/=-]{8,})",
        re.IGNORECASE,
    ),
    re.compile(r"\bbearer\s+([A-Za-z0-9._~+/=-]{12,})", re.IGNORECASE),
    re.compile(r"\b(sk-[A-Za-z0-9_-]{8,})\b"),
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
            sanitized[str(key)] = [_sanitize_value(item) for item in child]
        else:
            sanitized[str(key)] = _sanitize_value(child)
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
    elif _contains_secret_value(value):
        return path or "<value>"
    return ""


def _is_secret_key(key: str) -> bool:
    """
    Return whether a key name is likely sensitive.
    """
    normalized = key.strip().lower()
    return any(keyword in normalized for keyword in SECRET_KEYWORDS)


def _sanitize_value(value: Any) -> Any:
    """"""
    if isinstance(value, Mapping):
        return sanitize_mapping(value)
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, str):
        return _mask_secret_values(value)
    return value


def _contains_secret_value(value: Any) -> bool:
    """"""
    if not isinstance(value, str):
        return False
    return any(pattern.search(value) for pattern in SECRET_VALUE_PATTERNS)


def _mask_secret_values(value: str) -> str:
    """"""
    masked = value
    for pattern in SECRET_VALUE_PATTERNS:
        masked = pattern.sub(_mask_secret_match, masked)
    return masked


def _mask_secret_match(match: re.Match[str]) -> str:
    """"""
    if match.lastindex:
        secret = match.group(match.lastindex)
        start, end = match.span(match.lastindex)
        return f"{match.string[match.start():start]}{mask_secret(secret)}{match.string[end:match.end()]}"
    return mask_secret(match.group(0))
