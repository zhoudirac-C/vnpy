from vnpy_tradingagents.runtime import (
    SignalStatus,
    TradingAgentsMode,
    TradingAgentsRuntimeController,
    TradingAgentsRuntimeState,
)


def test_runtime_state_defaults_to_disabled():
    """TradingAgents should be disabled by default."""
    state = TradingAgentsRuntimeState()

    assert not state.enabled
    assert not state.live_enabled
    assert state.mode == TradingAgentsMode.REPORT_ONLY
    assert state.signal_status == SignalStatus.DISABLED


def test_runtime_controller_enable_report_only_keeps_live_blocked():
    """Report-only mode should allow AI reports but block live signal use."""
    controller = TradingAgentsRuntimeController()

    controller.enable(mode=TradingAgentsMode.REPORT_ONLY)

    assert controller.state.enabled
    assert not controller.state.live_enabled
    assert controller.state.signal_status == SignalStatus.ACTIVE
    assert controller.can_generate_report()
    assert controller.can_use_signal(live=False)
    assert not controller.can_use_signal(live=True)


def test_runtime_controller_disable_blocks_all_signal_use():
    """Disabling TradingAgents should make all AI signals unavailable."""
    controller = TradingAgentsRuntimeController()
    controller.enable(mode=TradingAgentsMode.PAPER_ONLY)

    controller.disable("user_disabled")

    assert not controller.state.enabled
    assert not controller.state.live_enabled
    assert controller.state.disabled_reason == "user_disabled"
    assert controller.state.signal_status == SignalStatus.DISABLED
    assert not controller.can_generate_report()
    assert not controller.can_use_signal(live=False)
    assert not controller.can_use_signal(live=True)


def test_runtime_controller_live_mode_requires_explicit_live_flag():
    """Live mode should be the only mode that permits live signal use."""
    controller = TradingAgentsRuntimeController()

    controller.enable(mode=TradingAgentsMode.LIVE_ALLOWED, live_enabled=True)

    assert controller.state.enabled
    assert controller.state.live_enabled
    assert controller.can_use_signal(live=True)


def test_tradingagents_engine_exposes_runtime_switches():
    """TradingAgentsEngine should expose switch methods for future UI widgets."""
    from vnpy.event import EventEngine
    from vnpy_tradingagents.engine import TradingAgentsEngine

    engine = TradingAgentsEngine(None, EventEngine())  # type: ignore[arg-type]

    engine.enable(mode=TradingAgentsMode.PAPER_ONLY)
    assert engine.runtime.can_generate_report()
    assert engine.runtime.can_use_signal(live=False)

    engine.disable("front_switch_off")
    assert not engine.runtime.can_generate_report()
    assert engine.runtime.state.disabled_reason == "front_switch_off"


def test_tradingagents_app_metadata_points_to_engine():
    """TradingAgentsApp should be loadable through vn.py BaseApp metadata."""
    from vnpy_tradingagents import TradingAgentsApp
    from vnpy_tradingagents.engine import TradingAgentsEngine

    assert TradingAgentsApp.app_name == "TradingAgents"
    assert TradingAgentsApp.engine_class is TradingAgentsEngine
