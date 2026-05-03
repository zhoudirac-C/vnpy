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
            "tradingagents.timeout_seconds": "30",
            "tradingagents.max_retries": "2",
            "tradingagents.checkpoint_dir": str(tmp_path),
        }
    )

    assert config.llm_provider == "openai"
    assert config.api_key_env_var == "OPENAI_API_KEY"
    assert config.model == "gpt-test"
    assert config.timeout_seconds == 30
    assert config.max_retries == 2
    assert config.checkpoint_dir == Path(tmp_path)
