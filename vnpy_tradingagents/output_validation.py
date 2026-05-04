import math
from dataclasses import replace
from typing import Any

from .worker import TradingAgentsWorkerResponse


ALLOWED_ACTIONS: frozenset[str] = frozenset({"buy", "sell", "reduce", "hold", "watch"})
ALLOWED_RATINGS: frozenset[str] = frozenset(
    {"Buy", "Overweight", "Hold", "Underweight", "Sell", "Unavailable"}
)


def validate_worker_response(
    response: TradingAgentsWorkerResponse,
) -> TradingAgentsWorkerResponse:
    """
    Validate and downgrade unsafe TradingAgents worker output.
    """
    errors: list[str] = []
    rating: str = response.rating
    action: str = response.action.strip().lower()
    confidence, confidence_error = _clamp_confidence(response.confidence)
    risk_notes: str = response.risk_notes

    if rating not in ALLOWED_RATINGS:
        rating = "Unavailable"
        errors.append("invalid_rating")

    if action not in ALLOWED_ACTIONS:
        action = "hold"
        errors.append("invalid_action")

    if confidence_error:
        errors.append(confidence_error)

    if errors and not risk_notes:
        risk_notes = "invalid output downgraded"

    raw_state: dict[str, Any] = dict(response.raw_state)
    if errors:
        raw_state["validation_errors"] = errors

    return replace(
        response,
        rating=rating,
        action=action,
        confidence=confidence,
        risk_notes=risk_notes,
        raw_state=raw_state,
    )


def _clamp_confidence(value: Any) -> tuple[float, str]:
    """
    Clamp confidence into [0, 1], returning a validation error when needed.
    """
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0, "invalid_confidence"

    if not math.isfinite(numeric):
        return 0, "invalid_confidence"

    clamped = min(max(numeric, 0), 1)
    if clamped != numeric:
        return clamped, "confidence_clamped"

    return clamped, ""
