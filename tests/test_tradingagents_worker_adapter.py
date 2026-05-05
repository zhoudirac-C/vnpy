import os
from threading import Event, current_thread
from time import sleep

from vnpy_tradingagents.config import TradingAgentsWorkerConfig
from vnpy_tradingagents.worker import TradingAgentsWorkerRequest


def test_worker_adapter_fails_before_runner_when_api_key_missing():
    """Worker adapter should not start the runner without a configured API key."""
    from vnpy_tradingagents.worker_adapter import TradingAgentsWorkerAdapter

    runner = RecordingRunner()
    adapter = TradingAgentsWorkerAdapter(
        config=TradingAgentsWorkerConfig(api_key_env_var="MISSING_KEY"),
        runner=runner,
        environ={},
    )

    response = adapter.run(make_request())

    assert runner.payload is None
    assert response.action == "hold"
    assert response.confidence == 0
    assert response.raw_state["status"] == "failed"
    assert response.raw_state["error_type"] == "configuration_error"
    assert "MISSING_KEY" in response.raw_state["error_message"]


def test_worker_adapter_syncs_keyring_secret_to_process_env(monkeypatch):
    """Keyring-only secrets should become visible to upstream LLM SDKs."""
    import vnpy_tradingagents.config as config_module

    from vnpy_tradingagents.worker_adapter import TradingAgentsWorkerAdapter

    monkeypatch.delenv("SYNC_TEST_KEY", raising=False)
    runner = RecordingRunner()
    adapter = TradingAgentsWorkerAdapter(
        config=TradingAgentsWorkerConfig(api_key_env_var="SYNC_TEST_KEY"),
        runner=runner,
    )
    monkeypatch.setattr(
        config_module,
        "resolve_llm_api_key",
        lambda env_var, environ=None, secret_store=None: "secret-from-keyring",
    )

    response = adapter.run(make_request())

    assert runner.payload is not None
    assert response.raw_state["decision"] == "buy"
    assert os.environ["SYNC_TEST_KEY"] == "secret-from-keyring"


def test_worker_adapter_passes_context_only_payload_to_runner():
    """Worker adapter should pass context-only input and map structured output."""
    from vnpy_tradingagents.worker_adapter import TradingAgentsWorkerAdapter

    runner = RecordingRunner()
    adapter = TradingAgentsWorkerAdapter(
        config=TradingAgentsWorkerConfig(api_key_env_var="TEST_KEY"),
        runner=runner,
        environ={"TEST_KEY": "secret"},
    )

    request = make_request()
    response = adapter.run(request)

    assert runner.payload is not None
    assert runner.payload.context is request.context
    assert not hasattr(runner.payload, "main_engine")
    assert not hasattr(runner.payload, "gateway")
    assert not hasattr(runner.payload, "send_order")
    assert response.rating == "Buy"
    assert response.action == "buy"
    assert response.report == "context-only report"
    assert response.raw_state["decision"] == "buy"


def test_worker_adapter_applies_intraday_profile_to_runner_payload():
    """Intraday worker requests should disable thinking and use the shorter timeout."""
    from vnpy_tradingagents.worker_adapter import TradingAgentsWorkerAdapter

    runner = RecordingRunner()
    adapter = TradingAgentsWorkerAdapter(
        config=TradingAgentsWorkerConfig(
            api_key_env_var="TEST_KEY",
            timeout_seconds=1800,
            intraday_thinking_type="disabled",
            intraday_timeout_seconds=360,
        ),
        runner=runner,
        environ={"TEST_KEY": "secret"},
    )

    response = adapter.run(make_request(mode="intraday_advice"))

    assert response.action == "buy"
    assert runner.payload is not None
    assert runner.payload.config.thinking_type == "disabled"
    assert runner.payload.config.timeout_seconds == 360


def test_worker_adapter_applies_long_horizon_profile_to_runner_payload():
    """Long-horizon requests should enable thinking and use the long timeout."""
    from vnpy_tradingagents.worker_adapter import TradingAgentsWorkerAdapter

    runner = RecordingRunner()
    adapter = TradingAgentsWorkerAdapter(
        config=TradingAgentsWorkerConfig(
            api_key_env_var="TEST_KEY",
            timeout_seconds=1800,
            long_horizon_thinking_type="enabled",
            long_horizon_timeout_seconds=2700,
        ),
        runner=runner,
        environ={"TEST_KEY": "secret"},
    )

    response = adapter.run(make_request(mode="long_horizon"))

    assert response.action == "buy"
    assert runner.payload is not None
    assert runner.payload.config.thinking_type == "enabled"
    assert runner.payload.config.timeout_seconds == 2700


def test_worker_adapter_rejects_forbidden_provider_context():
    """Worker adapter should refuse provider handles in request context."""
    from vnpy_tradingagents.worker_adapter import TradingAgentsWorkerAdapter

    runner = RecordingRunner()
    adapter = TradingAgentsWorkerAdapter(
        config=TradingAgentsWorkerConfig(api_key_env_var="TEST_KEY"),
        runner=runner,
        environ={"TEST_KEY": "secret"},
    )
    request = make_request(context={"market": {"bars": []}, "akshare": object()})

    response = adapter.run(request)

    assert runner.payload is None
    assert response.action == "hold"
    assert response.raw_state["status"] == "failed"
    assert response.raw_state["error_type"] == "forbidden_context"
    assert "akshare" in response.raw_state["error_message"]


def test_worker_adapter_blocks_missing_required_market_source():
    """Worker adapter should not run TradingAgents without required market data."""
    from vnpy_tradingagents.worker_adapter import TradingAgentsWorkerAdapter

    runner = RecordingRunner()
    adapter = TradingAgentsWorkerAdapter(
        config=TradingAgentsWorkerConfig(api_key_env_var="TEST_KEY"),
        runner=runner,
        environ={"TEST_KEY": "secret"},
    )

    response = adapter.run(make_request(context={"market": {"bars": []}}))

    assert runner.payload is None
    assert response.action == "hold"
    assert response.raw_state["error_type"] == "source_policy_blocked"
    assert response.raw_state["error_message"] == "missing_required_source:market"


def test_worker_adapter_returns_auditable_failure_on_timeout():
    """Worker adapter should return a failed response when the runner times out."""
    from vnpy_tradingagents.worker_adapter import TradingAgentsWorkerAdapter

    adapter = TradingAgentsWorkerAdapter(
        config=TradingAgentsWorkerConfig(
            api_key_env_var="TEST_KEY",
            timeout_seconds=0.01,
        ),
        runner=SlowRunner(),
        environ={"TEST_KEY": "secret"},
    )

    response = adapter.run(make_request())

    assert response.action == "hold"
    assert response.confidence == 0
    assert response.raw_state["status"] == "failed"
    assert response.raw_state["error_type"] == "timeout"
    assert response.raw_state["run_id"] == "run-1"


def test_worker_adapter_timeout_thread_does_not_block_process_exit():
    """Timed-out upstream graph calls should run in a daemon thread."""
    from vnpy_tradingagents.worker_adapter import TradingAgentsWorkerAdapter

    runner = BlockingRunner()
    adapter = TradingAgentsWorkerAdapter(
        config=TradingAgentsWorkerConfig(
            api_key_env_var="TEST_KEY",
            timeout_seconds=0.01,
        ),
        runner=runner,
        environ={"TEST_KEY": "secret"},
    )

    response = adapter.run(make_request())

    assert response.raw_state["error_type"] == "timeout"
    assert runner.started.wait(timeout=1)
    assert runner.thread is not None
    assert runner.thread.daemon is True
    runner.release.set()


def make_request(
    context: dict | None = None,
    mode: str = "report_only",
) -> TradingAgentsWorkerRequest:
    """Create a reusable worker request."""
    return TradingAgentsWorkerRequest(
        run_id="run-1",
        vt_symbol="600519.SSE",
        trade_date="2024-01-03",
        mode=mode,
        context=context or {"market": {"bars": [{"close_price": 1695}]}},
    )


class RecordingRunner:
    """Fake context-only runner for adapter tests."""

    def __init__(self) -> None:
        self.payload = None

    def run(self, payload):
        self.payload = payload
        return {
            "rating": "Buy",
            "confidence": 0.82,
            "report": "context-only report",
            "action": "buy",
            "target_weight_hint": 0.15,
            "holding_period_hint": "20d",
            "risk_notes": "risk checked",
            "raw_state": {"decision": "buy"},
        }


class SlowRunner:
    """Runner fake that exceeds adapter timeout."""

    def run(self, payload):
        sleep(0.2)
        return {"rating": "Buy", "report": "too late"}


class BlockingRunner:
    """Runner fake that stays alive until the test releases it."""

    def __init__(self) -> None:
        self.started = Event()
        self.release = Event()
        self.thread = None

    def run(self, payload):
        self.thread = current_thread()
        self.started.set()
        self.release.wait(timeout=30)
        return {"rating": "Buy", "report": "released"}
