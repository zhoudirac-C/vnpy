import re
from typing import Any


LABEL_ALIASES: dict[str, tuple[str, ...]] = {
    "rating": ("rating", "评级", "投资评级"),
    "confidence": ("confidence", "置信度", "信心分", "确定性"),
    "action": ("action", "操作", "建议操作", "交易动作"),
    "risk_notes": ("risk notes", "risk", "risks", "风险提示", "主要风险", "风险"),
}

RISK_KEYWORDS: tuple[str, ...] = (
    "风险",
    "止损",
    "回撤",
    "阻力",
    "亏损",
    "波动",
    "现金流",
    "存货",
    "应收",
    "杠杆",
    "监管",
    "退市",
    "违约",
    "不确定",
    "压力",
)


def parse_free_text_worker_output(text: str) -> dict[str, Any]:
    """
    Extract auditable fields from a Markdown/plain-text TradingAgents fallback.
    """
    if not text.strip():
        return {}

    parsed: dict[str, Any] = {}

    rating_value = _extract_label_value(text, LABEL_ALIASES["rating"])
    rating = _normalize_rating(rating_value or "")
    if rating:
        parsed["rating"] = rating

    action_value = _extract_label_value(text, LABEL_ALIASES["action"])
    action = _normalize_action(action_value or "")
    if not action and rating:
        action = _action_from_rating(rating)
    if action:
        parsed["action"] = action

    confidence_value = _extract_label_value(text, LABEL_ALIASES["confidence"])
    confidence = _parse_confidence(confidence_value or "")
    if confidence is not None:
        parsed["confidence"] = confidence

    risk_notes = _extract_label_value(text, LABEL_ALIASES["risk_notes"])
    if not risk_notes:
        risk_notes = _extract_risk_sentences(text)
    if risk_notes:
        parsed["risk_notes"] = _clean_text(risk_notes)[:800]

    if parsed:
        parsed["text_output_parsed"] = True
    return parsed


def _extract_label_value(text: str, aliases: tuple[str, ...]) -> str:
    alias_pattern = "|".join(re.escape(alias) for alias in aliases)
    pattern = re.compile(
        rf"(?im)^\s*(?:[-*]\s*)?(?:\*\*)?\s*(?:{alias_pattern})\s*(?:\*\*)?\s*[:：]\s*(?P<value>.+?)\s*$"
    )
    match = pattern.search(text)
    if match:
        return _clean_text(match.group("value"))
    return ""


def _normalize_rating(value: str) -> str:
    lowered = value.strip().lower()
    if not lowered:
        return ""
    if "unavailable" in lowered or "不可用" in lowered:
        return "Unavailable"
    if "underweight" in lowered or "reduce" in lowered or "减持" in lowered:
        return "Underweight"
    if "overweight" in lowered or "增持" in lowered:
        return "Overweight"
    if "sell" in lowered or "卖出" in lowered or "看空" in lowered:
        return "Sell"
    if "buy" in lowered or "买入" in lowered or "看多" in lowered:
        return "Buy"
    if (
        "hold" in lowered
        or "neutral" in lowered
        or "watch" in lowered
        or "持有" in lowered
        or "中性" in lowered
        or "观望" in lowered
        or "维持" in lowered
    ):
        return "Hold"
    return ""


def _normalize_action(value: str) -> str:
    lowered = value.strip().lower()
    if not lowered:
        return ""
    if "sell" in lowered or "卖出" in lowered:
        return "sell"
    if "reduce" in lowered or "underweight" in lowered or "减持" in lowered:
        return "reduce"
    if "buy" in lowered or "overweight" in lowered or "买入" in lowered or "增持" in lowered:
        return "buy"
    if "watch" in lowered or "观察" in lowered or "观望" in lowered:
        return "watch"
    if "hold" in lowered or "持有" in lowered or "中性" in lowered or "维持" in lowered:
        return "hold"
    return ""


def _action_from_rating(rating: str) -> str:
    if rating in {"Buy", "Overweight"}:
        return "buy"
    if rating == "Sell":
        return "sell"
    if rating == "Underweight":
        return "reduce"
    if rating == "Hold":
        return "hold"
    return "hold"


def _parse_confidence(value: str) -> float | None:
    match = re.search(r"(?P<number>\d+(?:\.\d+)?)\s*(?P<percent>%|％)?", value)
    if not match:
        return None
    number = float(match.group("number"))
    if match.group("percent") or number > 1:
        number = number / 100
    return round(number, 4)


def _extract_risk_sentences(text: str) -> str:
    cleaned = _clean_text(text)
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[。.!?！？])\s*|\n+", cleaned)
        if sentence.strip()
    ]
    selected: list[str] = []
    for sentence in sentences:
        if any(keyword in sentence for keyword in RISK_KEYWORDS):
            selected.append(sentence)
        if len(selected) >= 3:
            break
    return "；".join(selected)


def _clean_text(value: str) -> str:
    cleaned = re.sub(r"\*\*", "", value)
    cleaned = re.sub(r"`", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()
