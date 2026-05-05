from pathlib import Path


def test_worker_config_reports_missing_api_key():
    """Worker config should fail clearly before starting a real worker."""
    from vnpy_tradingagents.config import TradingAgentsWorkerConfig

    config = TradingAgentsWorkerConfig(api_key_env_var="MISSING_TRADINGAGENTS_KEY")

    result = config.validate(environ={})

    assert not result.ready
    assert "MISSING_TRADINGAGENTS_KEY" in result.error
    assert "API key" in result.error


def test_worker_config_resolves_api_key_when_present():
    """Worker config should resolve API key from the configured environment name."""
    from vnpy_tradingagents.config import TradingAgentsWorkerConfig

    config = TradingAgentsWorkerConfig(api_key_env_var="TRADINGAGENTS_TEST_KEY")

    assert config.resolve_api_key({"TRADINGAGENTS_TEST_KEY": "secret"}) == "secret"
    assert config.validate({"TRADINGAGENTS_TEST_KEY": "secret"}).ready


def test_worker_config_loads_from_settings_with_type_casting(tmp_path):
    """Worker config should load vn.py settings values with typed fields."""
    from vnpy_tradingagents.config import TradingAgentsWorkerConfig

    config = TradingAgentsWorkerConfig.from_settings(
        {
            "tradingagents.llm_provider": "openai",
            "tradingagents.api_key_env_var": "OPENAI_API_KEY",
            "tradingagents.model": "gpt-test",
            "tradingagents.backend_url": "https://example.test/v1",
            "tradingagents.thinking_type": "disabled",
            "tradingagents.timeout_seconds": "30",
            "tradingagents.max_retries": "2",
            "tradingagents.max_completion_tokens": "1024",
            "tradingagents.checkpoint_dir": str(tmp_path),
        }
    )

    assert config.llm_provider == "openai"
    assert config.api_key_env_var == "OPENAI_API_KEY"
    assert config.model == "gpt-test"
    assert config.backend_url == "https://example.test/v1"
    assert config.thinking_type == "disabled"
    assert config.timeout_seconds == 30
    assert config.max_retries == 2
    assert config.max_completion_tokens == 1024
    assert config.checkpoint_dir == Path(tmp_path)


def test_worker_config_loads_mode_profiles_from_settings(tmp_path):
    """Worker config should load per-mode thinking and timeout profiles."""
    from vnpy_tradingagents.config import TradingAgentsWorkerConfig

    config = TradingAgentsWorkerConfig.from_settings(
        {
            "tradingagents.llm_provider": "openai",
            "tradingagents.api_key_env_var": "OPENAI_API_KEY",
            "tradingagents.model": "gpt-test",
            "tradingagents.timeout_seconds": "1800",
            "tradingagents.intraday_thinking_type": "disabled",
            "tradingagents.intraday_timeout_seconds": "360",
            "tradingagents.long_horizon_thinking_type": "enabled",
            "tradingagents.long_horizon_timeout_seconds": "2700",
            "tradingagents.replay_thinking_type": "enabled",
            "tradingagents.replay_timeout_seconds": "2700",
            "tradingagents.checkpoint_dir": str(tmp_path),
        }
    )

    intraday = config.for_request_mode("intraday_advice")
    long_horizon = config.for_request_mode("long_horizon")
    replay = config.for_request_mode("backtesting_replay")
    default = config.for_request_mode("report_only")

    assert intraday.thinking_type == "disabled"
    assert intraday.timeout_seconds == 360
    assert long_horizon.thinking_type == "enabled"
    assert long_horizon.timeout_seconds == 2700
    assert replay.thinking_type == "enabled"
    assert replay.timeout_seconds == 2700
    assert default.thinking_type == "auto"
    assert default.timeout_seconds == 1800


def test_worker_config_normalizes_zhipu_alias_to_upstream_glm():
    """User-facing zhipu provider should map to TradingAgents' glm provider."""
    from vnpy_tradingagents.config import TradingAgentsWorkerConfig

    config = TradingAgentsWorkerConfig.from_settings(
        {
            "tradingagents.llm_provider": "zhipu",
            "tradingagents.api_key_env_var": "ZHIPU_API_KEY",
            "tradingagents.model": "glm-4.7",
        }
    )

    assert config.llm_provider == "glm"


def test_worker_config_normalizes_domestic_provider_aliases():
    """Domestic provider names shown in the UI should map to runnable providers."""
    from vnpy_tradingagents.config import TradingAgentsWorkerConfig

    cases = {
        "moonshot": "kimi",
        "volcengine": "doubao",
        "baidu": "qianfan",
        "iflytek": "spark",
        "lingyiwanwu": "yi",
        "aliyun": "qwen",
        "moda": "modelscope",
        "custom": "openai_compatible",
    }

    for user_provider, runtime_provider in cases.items():
        config = TradingAgentsWorkerConfig.from_settings(
            {
                "tradingagents.llm_provider": user_provider,
                "tradingagents.api_key_env_var": "TEST_KEY",
            }
        )
        assert config.llm_provider == runtime_provider
