import os
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from typing import Protocol


SERVICE_NAME = "vnpy.tradingagents"


class KeyringBackend(Protocol):
    """
    Minimal keyring protocol used by the UI secret bridge.
    """

    def set_password(self, service_name: str, username: str, password: str) -> None:
        pass

    def get_password(self, service_name: str, username: str) -> str | None:
        pass


@dataclass(frozen=True)
class LlmApiKeySaveResult:
    """
    Result returned after the UI receives an LLM API key.
    """

    env_var: str
    runtime_configured: bool
    persisted: bool
    message: str


class LlmApiKeyStore:
    """
    Store LLM keys outside vn.py's plaintext JSON settings.

    The UI always writes the key into the current process environment so the
    running session can use it immediately. If the optional ``keyring`` package
    is installed, the key can also be persisted in the OS credential store.
    """

    def __init__(
        self,
        environ: MutableMapping[str, str] | None = None,
        keyring_backend: KeyringBackend | None = None,
    ) -> None:
        self.environ: MutableMapping[str, str] = environ if environ is not None else os.environ
        self._keyring_backend: KeyringBackend | None = keyring_backend

    def set_api_key(
        self,
        env_var: str,
        api_key: str,
        *,
        persist: bool = False,
    ) -> LlmApiKeySaveResult:
        """
        Configure an API key without returning or logging the raw secret.
        """
        clean_env_var = env_var.strip()
        clean_api_key = api_key.strip()
        if not clean_env_var:
            return LlmApiKeySaveResult(
                env_var="",
                runtime_configured=False,
                persisted=False,
                message="LLM API key was not configured: missing environment variable name.",
            )
        if not clean_api_key:
            return LlmApiKeySaveResult(
                env_var=clean_env_var,
                runtime_configured=False,
                persisted=False,
                message=f"LLM API key for {clean_env_var} was left empty.",
            )

        self.environ[clean_env_var] = clean_api_key

        persisted = False
        if persist:
            backend = self._resolve_keyring_backend()
            if backend is not None:
                backend.set_password(SERVICE_NAME, clean_env_var, clean_api_key)
                persisted = True

        if persisted:
            message = (
                f"LLM API key for {clean_env_var} is configured for this session "
                "and saved in the system credential store."
            )
        elif persist:
            message = (
                f"LLM API key for {clean_env_var} is configured for this session. "
                "Install optional dependency keyring to persist it securely."
            )
        else:
            message = (
                f"LLM API key for {clean_env_var} is configured for this session only."
            )

        return LlmApiKeySaveResult(
            env_var=clean_env_var,
            runtime_configured=True,
            persisted=persisted,
            message=message,
        )

    def get_api_key(self, env_var: str) -> str:
        """
        Resolve a key from process environment first, then optional keyring.
        """
        clean_env_var = env_var.strip()
        if not clean_env_var:
            return ""

        value = self.environ.get(clean_env_var, "").strip()
        if value:
            return value

        backend = self._resolve_keyring_backend()
        if backend is None:
            return ""

        stored = backend.get_password(SERVICE_NAME, clean_env_var)
        return (stored or "").strip()

    def _resolve_keyring_backend(self) -> KeyringBackend | None:
        """
        Return injected keyring backend or import the optional dependency.
        """
        if self._keyring_backend is not None:
            return self._keyring_backend

        try:
            import keyring  # type: ignore[import-not-found]
        except Exception:
            return None

        self._keyring_backend = keyring
        return self._keyring_backend


def resolve_llm_api_key(
    env_var: str,
    environ: Mapping[str, str] | None = None,
    secret_store: LlmApiKeyStore | None = None,
) -> str:
    """
    Resolve an LLM key without storing it in vn.py settings.
    """
    if environ is not None:
        return environ.get(env_var, "").strip()

    store = secret_store or LlmApiKeyStore()
    return store.get_api_key(env_var)
