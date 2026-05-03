from importlib import import_module

from vnpy.event import EventEngine
from vnpy_tradingagents.engine import TradingAgentsEngine
from vnpy_tradingagents.runtime import TradingAgentsMode


def test_tradingagents_app_metadata_imports_ui_widget():
    """TradingAgentsApp metadata should point vn.py main window to the UI module."""
    from vnpy_tradingagents import TradingAgentsApp

    ui_module = import_module(TradingAgentsApp.app_module + ".ui")

    assert hasattr(ui_module, TradingAgentsApp.widget_name)


def test_ui_control_state_disables_runtime():
    """Frontend switch off should disable AI runtime cleanly."""
    from vnpy_tradingagents.ui.widget import TradingAgentsControlState, apply_control_state

    engine = TradingAgentsEngine(None, EventEngine())  # type: ignore[arg-type]
    engine.enable(mode=TradingAgentsMode.PAPER_ONLY)

    state = apply_control_state(
        engine,
        TradingAgentsControlState(enabled=False, mode=TradingAgentsMode.PAPER_ONLY),
    )

    assert not state.enabled
    assert state.disabled_reason == "front_switch_off"


def test_ui_live_allowed_requires_explicit_confirmation():
    """live_allowed mode should not enable live signal use without confirmation."""
    from vnpy_tradingagents.ui.widget import TradingAgentsControlState, apply_control_state

    engine = TradingAgentsEngine(None, EventEngine())  # type: ignore[arg-type]

    state = apply_control_state(
        engine,
        TradingAgentsControlState(
            enabled=True,
            mode=TradingAgentsMode.LIVE_ALLOWED,
            live_confirmed=False,
        ),
    )

    assert state.enabled
    assert not state.live_enabled
    assert not engine.runtime.can_use_signal(live=True)

    confirmed = apply_control_state(
        engine,
        TradingAgentsControlState(
            enabled=True,
            mode=TradingAgentsMode.LIVE_ALLOWED,
            live_confirmed=True,
        ),
    )

    assert confirmed.live_enabled
    assert engine.runtime.can_use_signal(live=True)
