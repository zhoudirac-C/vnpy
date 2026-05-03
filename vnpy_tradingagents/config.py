import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vnpy.trader.setting import SETTINGS


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
    timeout_seconds: int = 120
    max_retries: int = 1
    checkpoint_dir: Path = Path(".tradingagents/checkpoints")

    @classmethod
    def from_settings(
        cls,
        settings: Mapping[str, Any] | None = None,
    ) -> "TradingAgentsWorkerConfig":
        """
        Load worker config from vn.py SETTINGS-compatible values.
        """
        source: Mapping[str, Any] = settings or SETTINGS
        return cls(
            llm_provider=str(source.get("tradingagents.llm_provider", "openai")),
            api_key_env_var=str(
                source.get("tradingagents.api_key_env_var", "OPENAI_API_KEY")
            ),
            model=str(source.get("tradingagents.model", "gpt-4o-mini")),
            timeout_seconds=int(source.get("tradingagents.timeout_seconds", 120)),
            max_retries=int(source.get("tradingagents.max_retries", 1)),
            checkpoint_dir=Path(
                str(source.get("tradingagents.checkpoint_dir", ".tradingagents/checkpoints"))
            ),
        )

    def resolve_api_key(self, environ: Mapping[str, str] | None = None) -> str:
        """
        Resolve the API key from the configured environment variable.
        """
        source: Mapping[str, str] = environ or os.environ
        api_key: str = source.get(self.api_key_env_var, "").strip()
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

        if self.max_retries < 0:
            return WorkerConfigValidation(False, "max_retries must be non-negative")

        try:
            self.resolve_api_key(environ)
        except WorkerConfigError as exc:
            return WorkerConfigValidation(False, str(exc))

        return WorkerConfigValidation(True)
