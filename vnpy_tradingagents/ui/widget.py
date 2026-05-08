from dataclasses import dataclass
from datetime import datetime, timedelta

from vnpy.trader.engine import MainEngine
from vnpy.trader.ui import QtWidgets
from vnpy.event import EventEngine

from ..engine import TradingAgentsEngine
from ..manual_analysis import ManualAnalysisRequest, ManualAnalysisResult
from ..monitoring import ReplayRunStatus
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


def build_status_panel_text(status: ReplayRunStatus) -> str:
    """
    Render latest replay/audit status for the UI panel.
    """
    source_run_ids: str = ",".join(status.latest_ai_source_run_ids or [])
    return "\n".join(
        [
            f"run={status.run_id} mode={status.mode} health={status.health}",
            f"steps={status.total_steps} allowed={status.submit_allowed} rejected={status.risk_rejected}",
            f"decision={status.latest_decision_id} symbol={status.latest_vt_symbol}",
            f"action={status.latest_action} ai={status.latest_ai_decision} used={status.latest_ai_used}",
            f"risk={status.latest_risk_decision} failed_rule={status.latest_risk_failed_rule}",
            f"sources={source_run_ids}",
        ]
    )


def apply_manual_takeover(
    engine: TradingAgentsEngine,
    reason: str = "manual_takeover",
) -> TradingAgentsRuntimeState:
    """
    Pause TradingAgents immediately for manual operator takeover.
    """
    runtime = getattr(engine, "runtime", None)
    if runtime is not None:
        runtime.pause_manual_takeover(reason)
    else:
        engine.disable(reason)
    return engine.get_state()


def load_replay_status_panel_text(storage, run_id: str) -> str:
    """
    Load replay/gray-run status from storage and render the UI text.
    """
    status = storage.load_latest_status(run_id)
    if status is None:
        return f"run={run_id} status=missing"
    return build_status_panel_text(status)


def build_manual_analysis_summary_text(result: ManualAnalysisResult) -> str:
    """
    Render manual analysis result without implying that an order was submitted.
    """
    if result.response is None:
        return f"status={result.status} error={result.error_message}"

    response = result.response
    return "\n".join(
        [
            f"status={result.status} run={response.run_id} symbol={response.vt_symbol}",
            f"rating={response.rating} confidence={response.confidence:.2f}",
            f"action={response.action} target_weight={response.target_weight_hint}",
            f"holding_period={response.holding_period_hint} risk={response.risk_notes}",
            response.report,
        ]
    )


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
        self.replay_status_text = QtWidgets.QPlainTextEdit()
        self.replay_status_text.setReadOnly(True)
        self.manual_symbol_edit = QtWidgets.QLineEdit()
        self.manual_symbol_edit.setPlaceholderText("600519.SSE")
        self.manual_window_days_spin = QtWidgets.QSpinBox()
        self.manual_window_days_spin.setRange(1, 3650)
        self.manual_window_days_spin.setValue(60)
        self.manual_result_text = QtWidgets.QPlainTextEdit()
        self.manual_result_text.setReadOnly(True)
        self.manual_analysis_button = QtWidgets.QPushButton("运行手动分析")
        self.manual_analysis_button.clicked.connect(self.run_manual_analysis)
        self.apply_button = QtWidgets.QPushButton("应用")
        self.apply_button.clicked.connect(self.apply_settings)
        self.manual_takeover_button = QtWidgets.QPushButton("手工接管")
        self.manual_takeover_button.clicked.connect(self.manual_takeover)

        form = QtWidgets.QFormLayout()
        form.addRow("TradingAgents", self.enable_checkbox)
        form.addRow("模式", self.mode_combo)
        form.addRow("Live", self.live_confirm_checkbox)
        form.addRow("状态", self.status_label)
        form.addRow("Replay/Gray", self.replay_status_text)
        form.addRow("手动分析标的", self.manual_symbol_edit)
        form.addRow("分析窗口天数", self.manual_window_days_spin)
        form.addRow("手动分析结果", self.manual_result_text)
        form.addRow(self.manual_analysis_button)
        form.addRow(self.apply_button)
        form.addRow(self.manual_takeover_button)
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

    def set_replay_status(self, status: ReplayRunStatus) -> None:
        """
        Display latest replay or gray-run status.
        """
        self.replay_status_text.setPlainText(build_status_panel_text(status))

    def manual_takeover(self) -> None:
        """
        Pause AI signal usage from the UI.
        """
        state = apply_manual_takeover(self.engine)
        self.set_status_text(state)

    def run_manual_analysis(self) -> None:
        """
        Trigger report-only TradingAgents analysis from the UI.
        """
        vt_symbol = self.manual_symbol_edit.text().strip()
        if not vt_symbol:
            self.manual_result_text.setPlainText("status=invalid error=missing vt_symbol")
            return

        end = datetime.now()
        start = end - timedelta(days=self.manual_window_days_spin.value())
        try:
            result = self.engine.run_manual_analysis(
                ManualAnalysisRequest(
                    vt_symbol=vt_symbol,
                    start=start,
                    end=end,
                )
            )
        except Exception as exc:
            self.manual_result_text.setPlainText(f"status=failed error={exc}")
            return

        self.manual_result_text.setPlainText(build_manual_analysis_summary_text(result))

    def load_replay_status(self, storage, run_id: str) -> None:
        """
        Load and display latest replay status by run id.
        """
        self.replay_status_text.setPlainText(
            load_replay_status_panel_text(storage, run_id)
        )
