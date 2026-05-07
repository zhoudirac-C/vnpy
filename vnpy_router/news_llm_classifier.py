"""
Optional LLM semantic classifier for industry/theme news.
"""

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.request import Request, urlopen

from vnpy_router.event_storage import NewsRaw
from vnpy_router.news_entity import ResolvedEntityLink
from vnpy_router.security_catalog import SecurityEntity, SecurityEntityCatalog


class LlmChatClient(Protocol):
    """
    Minimal chat-completion client protocol.
    """

    def complete(
        self,
        messages: Sequence[dict[str, str]],
        model: str,
        thinking_type: str,
        timeout_seconds: int,
    ) -> str:
        pass


@dataclass(frozen=True)
class LlmClassifierRuntimeConfig:
    """
    Runtime policy for LLM message classification.
    """

    model: str = "glm-4.7"
    intraday_thinking_type: str = "disabled"
    scheduled_thinking_type: str = "disabled"
    research_thinking_type: str = "enabled"
    replay_thinking_type: str = "enabled"
    batch_thinking_type: str = "enabled"
    fast_timeout_seconds: int = 360
    deep_timeout_seconds: int = 2700
    min_confidence: float = 0.65

    def thinking_for_mode(self, mode: str) -> str:
        """
        Return thinking mode for one runtime mode.
        """
        normalized = mode.strip().lower()
        if normalized in {"intraday", "realtime", "timer"}:
            return self.intraday_thinking_type
        if normalized in {"scheduled", "scheduled_ingestion", "news_ingestion"}:
            return self.scheduled_thinking_type
        if normalized in {"research", "long_horizon"}:
            return self.research_thinking_type
        if normalized in {"replay", "backtest", "review"}:
            return self.replay_thinking_type
        if normalized in {"batch", "batch_industry_mapping", "portfolio"}:
            return self.batch_thinking_type
        return self.scheduled_thinking_type

    def timeout_for_mode(self, mode: str) -> int:
        """
        Return timeout for one runtime mode.
        """
        thinking = self.thinking_for_mode(mode)
        if thinking == "enabled":
            return self.deep_timeout_seconds
        return self.fast_timeout_seconds


@dataclass(frozen=True)
class LlmMessageClassification:
    """
    LLM semantic classification result after local validation.
    """

    event_type: str = ""
    topics: list[str] = field(default_factory=list)
    impact_direction: str = "unclear"
    links: list[ResolvedEntityLink] = field(default_factory=list)
    dropped_symbols: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)
    error: str = ""


class LlmMessageClassifier:
    """
    Use an LLM to propose industry/theme-related stocks, then verify locally.
    """

    def __init__(
        self,
        catalog: SecurityEntityCatalog,
        client: LlmChatClient,
        config: LlmClassifierRuntimeConfig | None = None,
    ) -> None:
        """"""
        self.catalog: SecurityEntityCatalog = catalog
        self.client: LlmChatClient = client
        self.config: LlmClassifierRuntimeConfig = config or LlmClassifierRuntimeConfig()

    def classify_and_link(
        self,
        news: NewsRaw,
        mode: str = "scheduled_ingestion",
    ) -> LlmMessageClassification:
        """
        Classify a message and return locally validated stock links.
        """
        thinking_type = self.config.thinking_for_mode(mode)
        timeout_seconds = self.config.timeout_for_mode(mode)
        content = self.client.complete(
            messages=_build_messages(news),
            model=self.config.model,
            thinking_type=thinking_type,
            timeout_seconds=timeout_seconds,
        )
        payload = _parse_json_object(content)
        links: list[ResolvedEntityLink] = []
        dropped: list[str] = []

        for stock in payload.get("stocks", []):
            if not isinstance(stock, dict):
                continue
            confidence = _float(stock.get("confidence"), default=0)
            if confidence < self.config.min_confidence:
                dropped.append(str(stock.get("vt_symbol") or stock.get("name") or ""))
                continue
            entity = self._resolve_stock(stock)
            if not entity:
                dropped.append(str(stock.get("vt_symbol") or stock.get("name") or ""))
                continue
            links.append(
                ResolvedEntityLink(
                    vt_symbol=entity.vt_symbol,
                    confidence=confidence,
                    reason=str(stock.get("reason") or ""),
                    sector=entity.sector,
                    topic="|".join(str(topic) for topic in payload.get("topics", []) if topic),
                    link_reason="llm_industry_linker",
                )
            )

        return LlmMessageClassification(
            event_type=str(payload.get("event_type") or ""),
            topics=[str(topic) for topic in payload.get("topics", []) if str(topic).strip()],
            impact_direction=str(payload.get("impact_direction") or "unclear"),
            links=_dedup_links(links),
            dropped_symbols=[symbol for symbol in dropped if symbol],
            limitations=[str(item) for item in payload.get("limitations", []) if str(item).strip()],
            raw_payload=payload,
        )

    def _resolve_stock(self, stock: dict[str, Any]) -> SecurityEntity | None:
        """
        Resolve LLM stock output against local security master.
        """
        vt_symbol = str(stock.get("vt_symbol") or "").strip()
        if vt_symbol:
            entity = self.catalog.find_by_symbol(vt_symbol)
            if entity:
                return entity

        name = str(stock.get("name") or "").strip()
        if name:
            lookup = self.catalog.lookup_alias(name)
            if lookup and not lookup.is_ambiguous:
                return self.catalog.get(lookup.matches[0].vt_symbol)
        return None


class ZhipuGlmChatClient:
    """
    Small stdlib GLM chat client for optional production use.
    """

    endpoint: str = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    def __init__(self, api_key: str, endpoint: str | None = None) -> None:
        """"""
        self.api_key = api_key.strip()
        self.endpoint = endpoint or self.endpoint
        self.last_usage: dict[str, Any] = {}

    def complete(
        self,
        messages: Sequence[dict[str, str]],
        model: str,
        thinking_type: str,
        timeout_seconds: int,
    ) -> str:
        """
        Call GLM chat completions and return message content.
        """
        payload = {
            "model": model,
            "messages": list(messages),
            "thinking": {"type": thinking_type},
            "temperature": 0.2,
            "max_tokens": 4096,
            "stream": False,
        }
        req = Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urlopen(req, timeout=timeout_seconds) as resp:
            body = resp.read().decode("utf-8")
        data = json.loads(body)
        usage = data.get("usage", {})
        self.last_usage = usage if isinstance(usage, dict) else {}
        return str(data["choices"][0]["message"]["content"])


def _build_messages(news: NewsRaw) -> list[dict[str, str]]:
    """
    Build prompt messages for industry/theme message linking.
    """
    user = f"""
请从一条 A 股行业/板块/宏观消息中识别最相关的股票。

消息标题：
{news.title}

消息摘要：
{news.content[:3000]}

要求：
1. 只输出严格 JSON，不要 Markdown。
2. 不要给投资建议，只做消息相关性识别。
3. 可以自由提名股票，但股票必须尽量给出 A 股代码和交易所后缀，格式如 600000.SSE 或 000001.SZSE。
4. 最多输出 10 只，按相关性从高到低排序。
5. 每只股票给 confidence 0 到 1、relation_type、reason、risk。
6. 如果没有候选池可能误配或遗漏，请写入 limitations。

JSON Schema:
{{
  "event_type": "industry|macro|policy|other",
  "topics": ["..."],
  "impact_direction": "positive|negative|mixed|unclear",
  "stocks": [
    {{
      "name": "",
      "vt_symbol": "",
      "confidence": 0.0,
      "relation_type": "direct|supply_chain|theme|indirect",
      "reason": "",
      "risk": ""
    }}
  ],
  "limitations": [""]
}}
""".strip()
    return [
        {
            "role": "system",
            "content": "你是 A 股行业消息实体关联测试器。你必须输出严格 JSON。",
        },
        {"role": "user", "content": user},
    ]


def _parse_json_object(content: str) -> dict[str, Any]:
    """
    Parse a JSON object, tolerating fenced output.
    """
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text.strip(), flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise
        data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("LLM classifier response must be a JSON object")
    return data


def _dedup_links(links: list[ResolvedEntityLink]) -> list[ResolvedEntityLink]:
    """
    Deduplicate links by symbol and keep highest confidence.
    """
    result: dict[str, ResolvedEntityLink] = {}
    for link in links:
        current = result.get(link.vt_symbol)
        if current is None or link.confidence > current.confidence:
            result[link.vt_symbol] = link
    return sorted(result.values(), key=lambda item: item.confidence, reverse=True)


def _float(value: Any, default: float) -> float:
    """
    Parse a float score.
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
