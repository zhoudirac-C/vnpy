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


def test_tradingagents_engine_persists_runtime_state():
    """TradingAgentsEngine should restore and persist runtime switch state."""
    from vnpy.event import EventEngine
    from vnpy_tradingagents.engine import TradingAgentsEngine

    storage = RuntimeStorageFake(
        TradingAgentsRuntimeState(
            enabled=True,
            mode=TradingAgentsMode.PAPER_ONLY,
            signal_status=SignalStatus.ACTIVE,
        )
    )
    engine = TradingAgentsEngine(None, EventEngine())  # type: ignore[arg-type]

    engine.set_state_storage(storage)
    engine.disable("front_switch_off")

    assert engine.runtime.state.mode == TradingAgentsMode.PAPER_ONLY
    assert storage.saved[-1].disabled_reason == "front_switch_off"


def test_postgres_runtime_state_storage_round_trip_sql():
    """PostgresRuntimeStateStorage should save and restore runtime switch state."""
    from vnpy_tradingagents.storage import PostgresRuntimeStateStorage

    connection = RuntimeConnection(
        fetchone_result={
            "enabled": True,
            "mode": "paper_only",
            "live_enabled": False,
            "manual_takeover": False,
            "signal_status": "active",
            "disabled_reason": "",
            "last_heartbeat_at": None,
            "last_successful_run_id": "run-1",
        }
    )
    storage = PostgresRuntimeStateStorage(connection)
    state = TradingAgentsRuntimeState(
        enabled=True,
        mode=TradingAgentsMode.PAPER_ONLY,
        signal_status=SignalStatus.ACTIVE,
        last_successful_run_id="run-1",
    )

    storage.save_state(state)
    loaded = storage.load_state()

    assert "INSERT INTO ai_runtime_state" in connection.cursor_obj.executed[0][0]
    assert loaded is not None
    assert loaded.enabled
    assert loaded.mode == TradingAgentsMode.PAPER_ONLY
    assert loaded.last_successful_run_id == "run-1"


def test_tradingagents_app_metadata_points_to_engine():
    """TradingAgentsApp should be loadable through vn.py BaseApp metadata."""
    from vnpy_tradingagents import TradingAgentsApp
    from vnpy_tradingagents.engine import TradingAgentsEngine

    assert TradingAgentsApp.app_name == "TradingAgents"
    assert TradingAgentsApp.engine_class is TradingAgentsEngine


class RuntimeStorageFake:
    """In-memory runtime storage fake."""

    def __init__(self, state=None) -> None:
        self.state = state
        self.saved = []

    def load_state(self):
        return self.state

    def save_state(self, state):
        self.saved.append(state)


class RuntimeCursor:
    """Tiny DB cursor for runtime state tests."""

    def __init__(self, fetchone_result=None) -> None:
        self.executed = []
        self.fetchone_result = fetchone_result

    def execute(self, sql, params=None) -> None:
        self.executed.append((sql, params or {}))

    def fetchone(self):
        return self.fetchone_result

    def close(self) -> None:
        return


class RuntimeConnection:
    """Tiny DB connection for runtime state tests."""

    def __init__(self, fetchone_result=None) -> None:
        self.cursor_obj = RuntimeCursor(fetchone_result)

    def cursor(self):
        return self.cursor_obj

    def commit(self) -> None:
        return
