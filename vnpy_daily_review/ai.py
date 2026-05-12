"""
Auditable LLM orchestration for daily market review.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from hashlib import sha256
import json
import socket
import time
from typing import Any, Protocol
from urllib.parse import urlparse
from urllib import error, request

from vnpy_tradingagents.config import TradingAgentsWorkerConfig
from vnpy_tradingagents.llm_secret import resolve_llm_api_key
from vnpy_tradingagents.tradingagents_factory import (
    OPENAI_COMPATIBLE_PROVIDER_CONFIG,
    _provider_extra_body,
)

from .evidence import EvidencePack


@dataclass(frozen=True)
class DailyReviewLLMResponse:
    """
    Normalized response from one LLM call.
    """

    content: str
    usage: dict[str, Any] = field(default_factory=dict)


class DailyReviewLLMClient(Protocol):
    """
    Minimal chat client used by the daily review orchestrator.
    """

    def chat(
        self,
        messages: Sequence[Mapping[str, str]],
        timeout_seconds: int,
        extra_body: Mapping[str, Any] | None = None,
    ) -> DailyReviewLLMResponse:
        """
        Execute one chat completion.
        """


@dataclass(frozen=True)
class DailyReviewAIOutput:
    """
    Result returned by the staged AI orchestration.
    """

    status: str
    markdown: str
    watch_items: list[dict[str, Any]]
    audit: list[dict[str, Any]]
    message: str


@dataclass(frozen=True)
class DailyReviewStageSpec:
    """
    One review stage definition.
    """

    name: str
    instruction: str


DAILY_REVIEW_STAGE_SPECS: tuple[DailyReviewStageSpec, ...] = (
    DailyReviewStageSpec(
        "MarketRegimeAnalyst",
        "判断市场状态、指数风险、情绪拐点和仓位节奏，必须引用 evidence_id。",
    ),
    DailyReviewStageSpec(
        "ThemeRotationAnalyst",
        (
            "判断主线、分支、防御方向、退潮方向和持续性；结合龙虎榜上榜原因、"
            "机构净买/净卖、活跃营业部净买和板块共振情况，必须引用 evidence_id。"
        ),
    ),
    DailyReviewStageSpec(
        "LeaderAnalyst",
        (
            "筛选风向标、趋势中军、逆势抗跌标和需要规避的后排；必须区分"
            "institution_net_buy、hot_money_net_buy、mixed_net_buy、net_sell，"
            "并说明高换手/高集中度是否只适合观察，必须引用 evidence_id。"
        ),
    ),
    DailyReviewStageSpec(
        "RiskCritic",
        (
            "审查追高、缩量、财报、节假日、数据缺失、证据不足、龙虎榜高集中度、"
            "机构净卖、游资一致性过强和上榜原因偏风险类的问题。"
        ),
    ),
    DailyReviewStageSpec(
        "WatchPlanWriter",
        (
            "输出 JSON 对象，字段为 report_markdown 和 watch_items。"
            "report_markdown 使用中文 Markdown，watch_items 是明日观察列表；"
            "每个观察项必须包含 symbol/name/role/watch_action/entry_condition/"
            "avoid_condition/position_rule/evidence_ids；如有龙虎榜证据，补充 "
            "capital_type/lhb_summary/lhb_reason_category/concentration_risk。"
        ),
    ),
)


class DailyReviewAIOrchestrator:
    """
    Multi-stage LLM composer that only reads Evidence Pack.
    """

    def __init__(
        self,
        client: DailyReviewLLMClient,
        provider: str,
        model_name: str,
        timeout_seconds: int,
        max_retries: int = 1,
        extra_body: Mapping[str, Any] | None = None,
    ) -> None:
        self.client: DailyReviewLLMClient = client
        self.provider: str = provider
        self.model_name: str = model_name
        self.timeout_seconds: int = timeout_seconds
        self.max_retries: int = max(0, int(max_retries))
        self.extra_body: dict[str, Any] = dict(extra_body or {})

    def run(
        self,
        pack: EvidencePack,
        deterministic_markdown: str,
        base_watch_items: list[dict[str, Any]],
    ) -> DailyReviewAIOutput:
        """
        Run staged LLM review with deterministic fallback.
        """
        try:
            llm_payload = pack.to_llm_input()
        except Exception as exc:
            return _fallback_output(
                deterministic_markdown=deterministic_markdown,
                base_watch_items=base_watch_items,
                audit=[
                    self._failed_audit(
                        stage="EvidencePackGuard",
                        prompt_hash="",
                        prompt_chars=0,
                        attempt=1,
                        elapsed_ms=0,
                        error_message=str(exc),
                    )
                ],
                message="llm_failed_fallback_deterministic:evidence_guard",
            )

        stage_outputs: dict[str, str] = {}
        audits: list[dict[str, Any]] = []
        run_started = time.perf_counter()

        for spec in DAILY_REVIEW_STAGE_SPECS:
            stage_timeout = _remaining_timeout_seconds(run_started, self.timeout_seconds)
            if stage_timeout <= 0:
                audits.append(
                    self._failed_audit(
                        stage=spec.name,
                        prompt_hash="",
                        prompt_chars=0,
                        attempt=1,
                        elapsed_ms=_elapsed_ms(run_started),
                        error_message=(
                            "daily_review_ai_total_timeout:"
                            f"{self.timeout_seconds}s"
                        ),
                    )
                )
                return _fallback_output(
                    deterministic_markdown=deterministic_markdown,
                    base_watch_items=base_watch_items,
                    audit=audits,
                    message=f"llm_failed_fallback_deterministic:{spec.name}:total_timeout",
                )
            messages = _stage_messages(
                spec=spec,
                llm_payload=llm_payload,
                deterministic_markdown=deterministic_markdown,
                previous_outputs=stage_outputs,
            )
            prompt_hash = _prompt_hash(messages)
            prompt_chars = sum(len(message.get("content", "")) for message in messages)
            response: DailyReviewLLMResponse | None = None

            for attempt in range(1, self.max_retries + 2):
                started = time.perf_counter()
                try:
                    response = self.client.chat(
                        messages,
                        timeout_seconds=stage_timeout,
                        extra_body=self.extra_body,
                    )
                except Exception as exc:
                    elapsed_ms = _elapsed_ms(started)
                    audit = self._failed_audit(
                        stage=spec.name,
                        prompt_hash=prompt_hash,
                        prompt_chars=prompt_chars,
                        attempt=attempt,
                        elapsed_ms=elapsed_ms,
                        error_message=str(exc),
                    )
                    audits.append(audit)
                    if attempt > self.max_retries:
                        return _fallback_output(
                            deterministic_markdown=deterministic_markdown,
                            base_watch_items=base_watch_items,
                            audit=audits,
                            message=(
                                "llm_failed_fallback_deterministic:"
                                f"{spec.name}"
                            ),
                        )
                    stage_timeout = _remaining_timeout_seconds(
                        run_started,
                        self.timeout_seconds,
                    )
                    if stage_timeout <= 0:
                        return _fallback_output(
                            deterministic_markdown=deterministic_markdown,
                            base_watch_items=base_watch_items,
                            audit=audits,
                            message=(
                                "llm_failed_fallback_deterministic:"
                                f"{spec.name}:total_timeout"
                            ),
                        )
                    continue

                elapsed_ms = _elapsed_ms(started)
                stage_outputs[spec.name] = response.content
                audits.append(
                    self._success_audit(
                        stage=spec.name,
                        prompt_hash=prompt_hash,
                        prompt_chars=prompt_chars,
                        response=response,
                        attempt=attempt,
                        elapsed_ms=elapsed_ms,
                    )
                )
                break

            if response is None:
                return _fallback_output(
                    deterministic_markdown=deterministic_markdown,
                    base_watch_items=base_watch_items,
                    audit=audits,
                    message=f"llm_failed_fallback_deterministic:{spec.name}",
                )

        markdown, watch_items = _parse_final_output(
            stage_outputs.get("WatchPlanWriter", ""),
            deterministic_markdown=deterministic_markdown,
            base_watch_items=base_watch_items,
        )
        return DailyReviewAIOutput(
            status="completed",
            markdown=markdown,
            watch_items=watch_items,
            audit=audits,
            message="llm_completed",
        )

    def _success_audit(
        self,
        stage: str,
        prompt_hash: str,
        prompt_chars: int,
        response: DailyReviewLLMResponse,
        attempt: int,
        elapsed_ms: int,
    ) -> dict[str, Any]:
        usage = dict(response.usage or {})
        completion_chars = len(response.content)
        prompt_tokens = int(usage.get("prompt_tokens") or _estimate_tokens(prompt_chars))
        completion_tokens = int(
            usage.get("completion_tokens") or _estimate_tokens(completion_chars)
        )
        total_tokens = int(
            usage.get("total_tokens") or prompt_tokens + completion_tokens
        )
        return {
            "mode": "llm",
            "stage": stage,
            "provider": self.provider,
            "model_name": self.model_name,
            "status": "completed",
            "attempt": attempt,
            "prompt_hash": prompt_hash,
            "prompt_chars": prompt_chars,
            "completion_chars": completion_chars,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "elapsed_ms": elapsed_ms,
        }

    def _failed_audit(
        self,
        stage: str,
        prompt_hash: str,
        prompt_chars: int,
        attempt: int,
        elapsed_ms: int,
        error_message: str,
    ) -> dict[str, Any]:
        return {
            "mode": "llm",
            "stage": stage,
            "provider": self.provider,
            "model_name": self.model_name,
            "status": "failed",
            "attempt": attempt,
            "prompt_hash": prompt_hash,
            "prompt_chars": prompt_chars,
            "completion_chars": 0,
            "prompt_tokens": _estimate_tokens(prompt_chars),
            "completion_tokens": 0,
            "total_tokens": _estimate_tokens(prompt_chars),
            "elapsed_ms": elapsed_ms,
            "error_message": error_message,
        }


class OpenAICompatibleDailyReviewLLMClient:
    """
    Small OpenAI-compatible HTTP client for daily review composition.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model_name: str,
        max_completion_tokens: int,
        connect_timeout_seconds: int = 5,
    ) -> None:
        self.base_url: str = base_url.rstrip("/")
        self.api_key: str = api_key
        self.model_name: str = model_name
        self.max_completion_tokens: int = max_completion_tokens
        self.connect_timeout_seconds: int = max(1, int(connect_timeout_seconds))

    def chat(
        self,
        messages: Sequence[Mapping[str, str]],
        timeout_seconds: int,
        extra_body: Mapping[str, Any] | None = None,
    ) -> DailyReviewLLMResponse:
        """
        POST one chat completion request.
        """
        _assert_endpoint_reachable(
            self.base_url,
            timeout_seconds=min(self.connect_timeout_seconds, timeout_seconds),
        )
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": [dict(message) for message in messages],
            "temperature": 0.2,
            "max_tokens": self.max_completion_tokens,
        }
        payload.update(dict(extra_body or {}))
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            url=f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=timeout_seconds) as response:
                response_body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"llm_http_error:{exc.code}:{detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"llm_url_error:{exc.reason}") from exc

        parsed = json.loads(response_body)
        choices = list(parsed.get("choices", []) or [])
        if not choices:
            raise RuntimeError("llm_empty_choices")
        message = dict(choices[0].get("message", {}) or {})
        content = str(message.get("content") or "").strip()
        if not content:
            raise RuntimeError("llm_empty_content")
        return DailyReviewLLMResponse(
            content=content,
            usage=dict(parsed.get("usage", {}) or {}),
        )


def build_daily_review_ai_orchestrator_from_settings(
    settings: Mapping[str, Any] | None = None,
    environ: Mapping[str, str] | None = None,
) -> DailyReviewAIOrchestrator | None:
    """
    Build the daily review AI orchestrator from existing vn.py AI settings.
    """
    base_config = TradingAgentsWorkerConfig.from_settings(settings)
    config = base_config.for_request_mode("daily_review_replay")
    api_key = resolve_llm_api_key(config.api_key_env_var, environ=environ)
    if not api_key:
        return None

    provider = config.llm_provider
    default_base_url, _default_env = OPENAI_COMPATIBLE_PROVIDER_CONFIG.get(
        provider,
        ("https://api.openai.com/v1", config.api_key_env_var),
    )
    base_url = config.backend_url.strip() or default_base_url
    client = OpenAICompatibleDailyReviewLLMClient(
        base_url=base_url,
        api_key=api_key,
        model_name=config.model,
        max_completion_tokens=config.max_completion_tokens,
    )
    extra_body = _provider_extra_body(
        {
            "llm_provider": provider,
            "deep_think_llm": config.model,
            "quick_think_llm": config.model,
            "thinking_type": config.thinking_type,
        }
    )
    return DailyReviewAIOrchestrator(
        client=client,
        provider=provider,
        model_name=config.model,
        timeout_seconds=config.timeout_seconds,
        max_retries=config.max_retries,
        extra_body=extra_body,
    )


def _stage_messages(
    spec: DailyReviewStageSpec,
    llm_payload: dict[str, Any],
    deterministic_markdown: str,
    previous_outputs: Mapping[str, str],
) -> list[dict[str, str]]:
    stage_payload = {
        "stage": spec.name,
        "instruction": spec.instruction,
        "evidence_pack": llm_payload,
        "deterministic_report": deterministic_markdown,
        "previous_stage_outputs": dict(previous_outputs),
    }
    return [
        {
            "role": "system",
            "content": (
                "你是A股盘后复盘分析师，只能基于用户给出的 Evidence Pack。"
                "不要编造不存在的数据，不要输出直接下单指令；结论必须可审计，"
                "关键判断要引用 evidence_id。龙虎榜只能作为资金行为证据，"
                "不能单独构成买入建议；高换手、高集中度、机构净卖必须显式提示风险。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(stage_payload, ensure_ascii=False, default=str),
        },
    ]


def _assert_endpoint_reachable(base_url: str, timeout_seconds: int) -> None:
    """
    Fail fast when the LLM endpoint is unreachable.
    """
    parsed = urlparse(base_url)
    host = parsed.hostname
    if not host:
        raise RuntimeError(f"llm_invalid_base_url:{base_url}")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return
    except OSError as exc:
        raise RuntimeError(f"llm_network_unreachable:{host}:{port}:{exc}") from exc


def _parse_final_output(
    content: str,
    deterministic_markdown: str,
    base_watch_items: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    try:
        payload = _extract_json_object(content)
    except ValueError:
        return content.strip() or deterministic_markdown, base_watch_items

    markdown = str(payload.get("report_markdown") or "").strip()
    if not markdown:
        markdown = deterministic_markdown
    raw_items = list(payload.get("watch_items", []) or [])
    watch_items = [_normalize_watch_item(item) for item in raw_items if isinstance(item, dict)]
    return markdown, watch_items or base_watch_items


def _extract_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("missing JSON object")
    parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("JSON output is not an object")
    return parsed


def _normalize_watch_item(item: Mapping[str, Any]) -> dict[str, Any]:
    normalized = {
        "symbol": str(item.get("symbol", "")),
        "name": str(item.get("name", "")),
        "role": str(item.get("role", "")),
        "watch_action": str(item.get("watch_action", "")),
        "entry_condition": str(item.get("entry_condition", "")),
        "avoid_condition": str(item.get("avoid_condition", "")),
        "position_rule": str(item.get("position_rule", "")),
        "evidence_ids": [str(value) for value in list(item.get("evidence_ids", []) or [])],
    }
    for key in (
        "capital_type",
        "lhb_summary",
        "lhb_reason_category",
        "concentration_risk",
    ):
        if key in item:
            normalized[key] = item[key]
    return normalized


def _fallback_output(
    deterministic_markdown: str,
    base_watch_items: list[dict[str, Any]],
    audit: list[dict[str, Any]],
    message: str,
) -> DailyReviewAIOutput:
    markdown = "\n\n".join(
        [
            deterministic_markdown,
            "## AI 编排失败，已使用确定性兜底",
            f"- message: `{message}`",
        ]
    )
    return DailyReviewAIOutput(
        status="partial",
        markdown=markdown,
        watch_items=base_watch_items,
        audit=audit,
        message=message,
    )


def _prompt_hash(messages: Sequence[Mapping[str, str]]) -> str:
    raw = json.dumps(list(messages), ensure_ascii=False, sort_keys=True)
    return sha256(raw.encode("utf-8")).hexdigest()


def _estimate_tokens(char_count: int) -> int:
    return max(1, int(char_count / 4)) if char_count else 0


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _remaining_timeout_seconds(started: float, total_timeout_seconds: int) -> int:
    remaining = float(total_timeout_seconds) - (time.perf_counter() - started)
    if remaining <= 0:
        return 0
    return max(1, int(remaining + 0.999))
