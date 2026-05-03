from dataclasses import dataclass

from vnpy.trader.engine import MainEngine
from vnpy.trader.ui import QtWidgets
from vnpy.event import EventEngine

from ..engine import TradingAgentsEngine
from ..runtime import TradingAgentsMode, TradingAgentsRuntimeState


@dataclass(frozen=True)
class TradingAgentsControlState:
    """
    UI switch state for TradingAgents runtime.
    """

    enabled: bool
    mode: TradingAgentsMode
    live_confirmed: bool = False


def apply_control_state(
    engine: TradingAgentsEngine,
    control_state: TradingAgentsControlState,
) -> TradingAgentsRuntimeState:
    """
    Apply frontend switch state to the runtime engine.
    """
    if not control_state.enabled:
        engine.disable("front_switch_off")
        return engine.get_state()

    engine.enable(
        mode=control_state.mode,
        live_enabled=control_state.mode == TradingAgentsMode.LIVE_ALLOWED
        and control_state.live_confirmed,
    )
    return engine.get_state()


class TradingAgentsWidget(QtWidgets.QWidget):
    """
    Minimal TradingAgents runtime control widget.
    """

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine) -> None:
        """"""
        super().__init__()
        self.main_engine: MainEngine = main_engine
        self.event_engine: EventEngine = event_engine
        self.engine: TradingAgentsEngine = main_engine.get_engine("TradingAgents")

        self.enable_checkbox = QtWidgets.QCheckBox("启用")
        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItems([mode.value for mode in TradingAgentsMode])
        self.live_confirm_checkbox = QtWidgets.QCheckBox("Live AI 二次确认")
        self.status_label = QtWidgets.QLabel()
        self.apply_button = QtWidgets.QPushButton("应用")
        self.apply_button.clicked.connect(self.apply_settings)

        form = QtWidgets.QFormLayout()
        form.addRow("TradingAgents", self.enable_checkbox)
        form.addRow("模式", self.mode_combo)
        form.addRow("Live", self.live_confirm_checkbox)
        form.addRow("状态", self.status_label)
        form.addRow(self.apply_button)
        self.setLayout(form)

        self.refresh_state()

    def apply_settings(self) -> None:
        """
        Apply UI switch values to runtime.
        """
        mode = TradingAgentsMode(self.mode_combo.currentText())
        state = apply_control_state(
            self.engine,
            TradingAgentsControlState(
                enabled=self.enable_checkbox.isChecked(),
                mode=mode,
                live_confirmed=self.live_confirm_checkbox.isChecked(),
            ),
        )
        self.set_status_text(state)

    def refresh_state(self) -> None:
        """
        Refresh UI fields from runtime state.
        """
        state = self.engine.get_state()
        self.enable_checkbox.setChecked(state.enabled)
        self.mode_combo.setCurrentText(state.mode.value)
        self.live_confirm_checkbox.setChecked(state.live_enabled)
        self.set_status_text(state)

    def set_status_text(self, state: TradingAgentsRuntimeState) -> None:
        """
        Render runtime status.
        """
        text = f"{state.signal_status.value} / {state.mode.value}"
        if state.disabled_reason:
            text = f"{text} / {state.disabled_reason}"
        self.status_label.setText(text)
