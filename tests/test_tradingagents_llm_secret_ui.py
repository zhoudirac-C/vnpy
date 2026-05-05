from vnpy_tradingagents.config import TradingAgentsWorkerConfig


def test_llm_api_key_store_uses_runtime_env_and_optional_keyring_without_returning_secret():
    """UI key entry should configure runtime/keyring without exposing the raw key."""
    from vnpy_tradingagents.llm_secret import LlmApiKeyStore

    environ = {}
    keyring = FakeKeyring()
    store = LlmApiKeyStore(environ=environ, keyring_backend=keyring)

    result = store.set_api_key("OPENAI_API_KEY", "sk-test-value", persist=True)

    assert environ["OPENAI_API_KEY"] == "sk-test-value"
    assert keyring.passwords[("vnpy.tradingagents", "OPENAI_API_KEY")] == "sk-test-value"
    assert result.runtime_configured
    assert result.persisted
    assert "sk-test-value" not in result.message


def test_worker_config_resolves_api_key_from_keyring_when_process_env_missing():
    """Worker config should support UI-saved keyring secrets without plaintext settings."""
    from vnpy_tradingagents.llm_secret import LlmApiKeyStore

    keyring = FakeKeyring()
    store = LlmApiKeyStore(environ={}, keyring_backend=keyring)
    store.set_api_key("OPENAI_API_KEY", "sk-from-keyring", persist=True)

    config = TradingAgentsWorkerConfig(api_key_env_var="OPENAI_API_KEY")

    assert config.resolve_api_key(environ=None, secret_store=store) == "sk-from-keyring"


def test_global_setting_coercion_excludes_plaintext_llm_api_key():
    """The pseudo UI field for a real API key must never be saved to vt_setting."""
    from vnpy.trader.ui.widget import (
        TRADINGAGENTS_API_KEY_FIELD,
        coerce_global_setting_values,
    )

    settings, secrets = coerce_global_setting_values(
        {
            "tradingagents.api_key_env_var": "OPENAI_API_KEY",
            TRADINGAGENTS_API_KEY_FIELD: "sk-plain-text",
            "tradingagents.timeout_seconds": "120",
        },
        {
            "tradingagents.api_key_env_var": str,
            TRADINGAGENTS_API_KEY_FIELD: str,
            "tradingagents.timeout_seconds": int,
        },
    )

    assert TRADINGAGENTS_API_KEY_FIELD not in settings
    assert settings["tradingagents.timeout_seconds"] == 120
    assert secrets[TRADINGAGENTS_API_KEY_FIELD] == "sk-plain-text"


def test_global_setting_ui_documents_worker_factory_default():
    """Global settings should expose the default context-only worker factory with help text."""
    from vnpy.trader.setting import SETTINGS
    from vnpy.trader.ui.widget import SETTING_HELP_TEXT

    assert (
        SETTINGS["tradingagents.worker_factory"]
        == "vnpy_tradingagents.tradingagents_factory:build"
    )
    assert "TRADINGAGENTS_WORKER_FACTORY" in SETTING_HELP_TEXT["tradingagents.worker_factory"]


def test_global_setting_ui_lists_domestic_llm_providers_and_base_urls():
    """Global settings help should show common domestic LLM provider choices."""
    from vnpy.trader.ui.widget import SETTING_HELP_TEXT

    provider_help = SETTING_HELP_TEXT["tradingagents.llm_provider"]
    base_url_help = SETTING_HELP_TEXT["tradingagents.backend_url"]

    assert "kimi" in provider_help
    assert "doubao" in provider_help
    assert "qianfan" in provider_help
    assert "MOONSHOT_API_KEY" in provider_help
    assert "modelscope" in provider_help
    assert "openai_compatible" in provider_help
    assert "https://api.moonshot.cn/v1" in base_url_help
    assert "https://ark.cn-beijing.volces.com/api/v3" in base_url_help
    assert "https://qianfan.baidubce.com/v2" in base_url_help
    assert "https://api-inference.modelscope.cn/v1" in base_url_help


def test_global_setting_ui_documents_mode_specific_thinking_and_timeouts():
    """Global settings help should explain intraday and long-horizon LLM profiles."""
    from vnpy.trader.ui.widget import SETTING_HELP_TEXT
    from vnpy_tradingagents.config import TradingAgentsWorkerConfig

    config = TradingAgentsWorkerConfig.from_settings({"tradingagents.llm_provider": "openai"})
    assert config.timeout_seconds == 1800
    assert config.intraday_thinking_type == "disabled"
    assert config.intraday_timeout_seconds == 360
    assert config.long_horizon_thinking_type == "enabled"
    assert config.long_horizon_timeout_seconds == 2700
    assert config.replay_thinking_type == "enabled"
    assert config.replay_timeout_seconds == 2700

    assert "日内" in SETTING_HELP_TEXT["tradingagents.intraday_thinking_type"]
    assert "360" in SETTING_HELP_TEXT["tradingagents.intraday_timeout_seconds"]
    assert "长期" in SETTING_HELP_TEXT["tradingagents.long_horizon_thinking_type"]
    assert "45 分钟" in SETTING_HELP_TEXT["tradingagents.replay_timeout_seconds"]


def test_trading_widget_subscribe_request_rejects_empty_exchange():
    """Trading panel helpers should not raise ValueError when exchange text is empty."""
    from vnpy.trader.constant import Exchange
    from vnpy.trader.ui.widget import build_trading_subscribe_request

    assert build_trading_subscribe_request("001267", "") is None
    assert build_trading_subscribe_request("001267", "NOT_AN_EXCHANGE") is None

    req = build_trading_subscribe_request("001267", "SZSE")
    assert req is not None
    assert req.symbol == "001267"
    assert req.exchange == Exchange.SZSE


def test_global_setting_ui_documents_router_akshare_configuration():
    """Global settings help should explain router/AKShare datafeed fields."""
    from vnpy.trader.ui.widget import SETTING_HELP_TEXT

    assert "datafeed.name=router" in SETTING_HELP_TEXT["datafeed.name"]
    assert "akshare" in SETTING_HELP_TEXT["router.providers"]
    assert "router.local_path" in SETTING_HELP_TEXT["router.local_path"]
    assert "历史 Datafeed" in SETTING_HELP_TEXT["router.providers"]


class FakeKeyring:
    """In-memory keyring fake."""

    def __init__(self) -> None:
        self.passwords = {}

    def set_password(self, service_name, username, password) -> None:
        self.passwords[(service_name, username)] = password

    def get_password(self, service_name, username):
        return self.passwords.get((service_name, username))
