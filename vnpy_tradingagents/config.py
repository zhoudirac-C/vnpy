import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from vnpy.trader.setting import SETTINGS

from .llm_secret import LlmApiKeyStore, resolve_llm_api_key


class WorkerConfigError(RuntimeError):
    """
    Raised when TradingAgents worker configuration is not runnable.
    """


@dataclass(frozen=True)
class WorkerConfigValidation:
    """
    Validation result used before starting a real TradingAgents worker.
    """

    ready: bool
    error: str = ""


@dataclass(frozen=True)
class TradingAgentsWorkerConfig:
    """
    Runtime configuration for the real TradingAgents worker adapter.
    """

    llm_provider: str = "openai"
    api_key_env_var: str = "OPENAI_API_KEY"
    model: str = "gpt-4o-mini"
    backend_url: str = ""
    thinking_type: str = "auto"
    timeout_seconds: int = 1800
    intraday_thinking_type: str = "disabled"
    intraday_timeout_seconds: int = 360
    long_horizon_thinking_type: str = "enabled"
    long_horizon_timeout_seconds: int = 2700
    replay_thinking_type: str = "enabled"
    replay_timeout_seconds: int = 2700
    max_retries: int = 1
    max_completion_tokens: int = 1536
    checkpoint_dir: Path = Path(".tradingagents/checkpoints")

    @classmethod
    def from_settings(
        cls,
        settings: Mapping[str, Any] | None = None,
    ) -> "TradingAgentsWorkerConfig":
        """
        Load worker config from vn.py SETTINGS-compatible values.
        """
        source: Mapping[str, Any] = SETTINGS if settings is None else settings
        return cls(
            llm_provider=_normalize_llm_provider(
                str(source.get("tradingagents.llm_provider", "openai"))
            ),
            api_key_env_var=str(
                source.get("tradingagents.api_key_env_var", "OPENAI_API_KEY")
            ),
            model=str(source.get("tradingagents.model", "gpt-4o-mini")),
            backend_url=str(source.get("tradingagents.backend_url", "")),
            thinking_type=str(source.get("tradingagents.thinking_type", "auto")),
            timeout_seconds=int(source.get("tradingagents.timeout_seconds", 1800)),
            intraday_thinking_type=str(
                source.get("tradingagents.intraday_thinking_type", "disabled")
            ),
            intraday_timeout_seconds=int(
                source.get("tradingagents.intraday_timeout_seconds", 360)
            ),
            long_horizon_thinking_type=str(
                source.get("tradingagents.long_horizon_thinking_type", "enabled")
            ),
            long_horizon_timeout_seconds=int(
                source.get("tradingagents.long_horizon_timeout_seconds", 2700)
            ),
            replay_thinking_type=str(
                source.get("tradingagents.replay_thinking_type", "enabled")
            ),
            replay_timeout_seconds=int(
                source.get("tradingagents.replay_timeout_seconds", 2700)
            ),
            max_retries=int(source.get("tradingagents.max_retries", 1)),
            max_completion_tokens=int(source.get("tradingagents.max_completion_tokens", 1536)),
            checkpoint_dir=Path(
                str(source.get("tradingagents.checkpoint_dir", ".tradingagents/checkpoints"))
            ),
        )

    def for_request_mode(self, mode: str) -> "TradingAgentsWorkerConfig":
        """
        Return the effective worker config for a request mode.
        """
        normalized: str = mode.strip().lower()
        if "intraday" in normalized:
            return replace(
                self,
                thinking_type=self.intraday_thinking_type,
                timeout_seconds=self.intraday_timeout_seconds,
            )

        if any(token in normalized for token in ("replay", "backtest", "backtesting")):
            return replace(
                self,
                thinking_type=self.replay_thinking_type,
                timeout_seconds=self.replay_timeout_seconds,
            )

        if any(
            token in normalized
            for token in ("long", "horizon", "portfolio", "research", "batch")
        ):
            return replace(
                self,
                thinking_type=self.long_horizon_thinking_type,
                timeout_seconds=self.long_horizon_timeout_seconds,
            )

        return self

    def resolve_api_key(
        self,
        environ: Mapping[str, str] | None = None,
        secret_store: LlmApiKeyStore | None = None,
    ) -> str:
        """
        Resolve the API key from the configured environment variable.
        """
        api_key: str = resolve_llm_api_key(
            self.api_key_env_var,
            environ=environ,
            secret_store=secret_store,
        )
        if not api_key:
            raise WorkerConfigError(
                f"Missing API key environment variable: {self.api_key_env_var}"
            )
        return api_key

    def validate(self, environ: Mapping[str, str] | None = None) -> WorkerConfigValidation:
        """
        Validate config before starting a real worker process.
        """
        if self.timeout_seconds <= 0:
            return WorkerConfigValidation(False, "timeout_seconds must be positive")

        if self.intraday_timeout_seconds <= 0:
            return WorkerConfigValidation(False, "intraday_timeout_seconds must be positive")

        if self.long_horizon_timeout_seconds <= 0:
            return WorkerConfigValidation(
                False,
                "long_horizon_timeout_seconds must be positive",
            )

        if self.replay_timeout_seconds <= 0:
            return WorkerConfigValidation(False, "replay_timeout_seconds must be positive")

        if self.max_retries < 0:
            return WorkerConfigValidation(False, "max_retries must be non-negative")

        if self.max_completion_tokens <= 0:
            return WorkerConfigValidation(False, "max_completion_tokens must be positive")

        try:
            self.resolve_api_key(environ)
        except WorkerConfigError as exc:
            return WorkerConfigValidation(False, str(exc))

        return WorkerConfigValidation(True)

    def checkpoint_path_for(
        self,
        run_id: str,
        vt_symbol: str,
        trade_date: str,
    ) -> Path:
        """
        Return an isolated checkpoint/memory path for one worker run.
        """
        return (
            self.checkpoint_dir
            / _safe_path_part(trade_date)
            / _safe_path_part(vt_symbol)
            / _safe_path_part(run_id)
        )


def _safe_path_part(value: str) -> str:
    """
    Convert run metadata into a filesystem-safe path segment.
    """
    text: str = re.sub(r"[^A-Za-z0-9-]+", "_", value.strip())
    return text.strip("_") or "unknown"


def _normalize_llm_provider(provider: str) -> str:
    """
    Normalize user-facing provider aliases to upstream TradingAgents names.
    """
    normalized = provider.strip().lower()
    aliases = {
        "01.ai": "yi",
        "01ai": "yi",
        "aliyun": "qwen",
        "ark": "doubao",
        "baidu": "qianfan",
        "zhipu": "glm",
        "bigmodel": "glm",
        "custom": "openai_compatible",
        "dashscope": "qwen",
        "doubao": "doubao",
        "huoshan": "doubao",
        "iflytek": "spark",
        "lingyiwanwu": "yi",
        "minimax": "minimax",
        "moda": "modelscope",
        "modelscope": "modelscope",
        "mota": "modelscope",
        "moonshot": "kimi",
        "openai-compatible": "openai_compatible",
        "openai_compatible": "openai_compatible",
        "tencent": "hunyuan",
        "volcengine": "doubao",
        "wenxin": "qianfan",
        "xfyun": "spark",
    }
    return aliases.get(normalized, normalized)
