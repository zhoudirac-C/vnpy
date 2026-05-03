from importlib import import_module

from vnpy.event import EventEngine
from vnpy_tradingagents.engine import TradingAgentsEngine
from vnpy_tradingagents.monitoring import ReplayRunStatus
from vnpy_tradingagents.runtime import TradingAgentsMode
from datetime import datetime


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


def test_status_panel_text_uses_replay_status_not_worker_state():
    """Status panel should render replay/audit status fields."""
    from vnpy_tradingagents.ui.widget import build_status_panel_text

    text = build_status_panel_text(
        ReplayRunStatus(
            run_id="gray-1",
            mode="intraday",
            generated_at=datetime(2024, 1, 3, 10),
            health="blocked",
            total_steps=3,
            submit_allowed=1,
            risk_rejected=1,
            ai_blocked=1,
            rating_blocked=0,
            ai_used=2,
            latest_decision_id="decision-1",
            latest_vt_symbol="600519.SSE",
            latest_action="buy",
            latest_ai_decision="allow",
            latest_ai_used=True,
            latest_risk_decision="rejected",
            latest_risk_failed_rule="max_order_value",
            latest_ai_source_run_ids=["rating-1", "advice-1"],
        )
    )

    assert "gray-1" in text
    assert "decision-1" in text
    assert "600519.SSE" in text
    assert "max_order_value" in text
    assert "rating-1,advice-1" in text
