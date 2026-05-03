from vnpy_tradingagents.gateway_policy import (
    GatewayAccountMode,
    GatewayAiPolicy,
    GatewayProfile,
)
from vnpy_tradingagents.runtime import TradingAgentsMode, TradingAgentsRuntimeController


def test_gateway_policy_enables_ai_for_simulation_gateway():
    """GatewayAiPolicy should enable AI signals for simulation accounts."""
    runtime = TradingAgentsRuntimeController()
    policy = GatewayAiPolicy()

    policy.apply(
        runtime=runtime,
        profile=GatewayProfile(gateway_name="PAPER", account_mode=GatewayAccountMode.SIMULATION),
        ai_enabled=True,
    )

    assert runtime.state.enabled
    assert runtime.state.mode == TradingAgentsMode.PAPER_ONLY
    assert runtime.can_use_signal(live=False)
    assert not runtime.can_use_signal(live=True)


def test_gateway_policy_keeps_live_gateway_disabled_by_default():
    """GatewayAiPolicy should keep live accounts disabled unless explicitly allowed."""
    runtime = TradingAgentsRuntimeController()
    policy = GatewayAiPolicy()

    policy.apply(
        runtime=runtime,
        profile=GatewayProfile(gateway_name="QMT", account_mode=GatewayAccountMode.LIVE),
        ai_enabled=True,
    )

    assert not runtime.state.enabled
    assert runtime.state.disabled_reason == "ai_not_allowed_for_gateway"
    assert not runtime.can_use_signal(live=False)
    assert not runtime.can_use_signal(live=True)


def test_gateway_policy_requires_explicit_live_permission():
    """Live AI signal use should require explicit live permission."""
    runtime = TradingAgentsRuntimeController()
    policy = GatewayAiPolicy(allow_live_ai=True)

    policy.apply(
        runtime=runtime,
        profile=GatewayProfile(gateway_name="QMT", account_mode=GatewayAccountMode.LIVE),
        ai_enabled=True,
    )

    assert runtime.state.enabled
    assert runtime.state.mode == TradingAgentsMode.LIVE_ALLOWED
    assert runtime.can_use_signal(live=True)


def test_gateway_policy_respects_frontend_ai_disabled_switch():
    """Frontend disabling AI should override simulation account eligibility."""
    runtime = TradingAgentsRuntimeController()
    policy = GatewayAiPolicy()

    policy.apply(
        runtime=runtime,
        profile=GatewayProfile(gateway_name="PAPER", account_mode=GatewayAccountMode.SIMULATION),
        ai_enabled=False,
    )

    assert not runtime.state.enabled
    assert runtime.state.disabled_reason == "front_switch_off"
