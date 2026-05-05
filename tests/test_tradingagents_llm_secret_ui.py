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


class FakeKeyring:
    """In-memory keyring fake."""

    def __init__(self) -> None:
        self.passwords = {}

    def set_password(self, service_name, username, password) -> None:
        self.passwords[(service_name, username)] = password

    def get_password(self, service_name, username):
        return self.passwords.get((service_name, username))
