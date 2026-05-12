from datetime import date
import json
from re import DOTALL, search
from typing import Any

from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine
from vnpy.trader.ui import QtCore, QtWidgets

from ..engine import (
    APP_NAME,
    DailyMarketReviewEngine,
    DailyMarketReviewReportResult,
    DailyMarketReviewValidationResult,
)


DAILY_MARKET_REVIEW_TAB_TITLES: list[str] = [
    "今日报告",
    "明日观察",
    "历史报告",
    "市场信号",
    "验证复盘",
    "配置",
]


def format_report_result_markdown(result: DailyMarketReviewReportResult) -> str:
    """
    Render one report result as Markdown.
    """
    body = extract_report_markdown(result.markdown)
    return "\n\n".join(
        [
            f"# {result.title or '每日市场复盘'}",
            f"- trade_date: `{result.trade_date.isoformat()}`",
            f"- status: `{result.status}`",
            body,
        ]
    )


def extract_report_markdown(raw_text: str) -> str:
    """
    Return human-readable Markdown from an AI result.
    """
    payload = _extract_ai_payload(raw_text)
    if payload:
        markdown = str(payload.get("report_markdown") or "").strip()
        if markdown:
            return markdown

    heuristic_markdown = _extract_report_markdown_field(raw_text)
    if heuristic_markdown:
        return heuristic_markdown

    return raw_text or "_暂无每日市场复盘报告。_"


def extract_watch_items(
    raw_text: str,
    fallback_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Return watch items embedded in raw AI output when available.
    """
    payload = _extract_ai_payload(raw_text)
    if not payload:
        return fallback_items

    items = payload.get("watch_items")
    if not isinstance(items, list):
        return fallback_items
    normalized = [item for item in items if isinstance(item, dict)]
    return normalized or fallback_items


def format_report_result_raw_text(result: DailyMarketReviewReportResult) -> str:
    """
    Render raw report payload for audit/debugging.
    """
    payload = _extract_ai_payload(result.markdown)
    raw_report = (
        json.dumps(payload, ensure_ascii=False, indent=2)
        if payload
        else result.markdown
    )
    raw = {
        "trade_date": result.trade_date.isoformat(),
        "status": result.status,
        "title": result.title,
        "message": result.message,
        "raw_report": raw_report,
        "watch_items": result.watch_items,
        "evidence_count": len(result.evidence),
        "audit": result.audit,
    }
    return json.dumps(raw, ensure_ascii=False, indent=2, default=str)


def format_validation_result_text(result: DailyMarketReviewValidationResult) -> str:
    """
    Render next-day validation output for the UI.
    """
    lines = [
        f"status={result.status}",
        f"trade_date={result.trade_date.isoformat()}",
        f"validation_date={result.validation_date.isoformat()}",
    ]
    if result.message:
        lines.append(f"message={result.message}")
    for item in result.results:
        lines.append(str(item))
    return "\n".join(lines)


class DailyReviewPreviewWorker(QtCore.QThread):
    """
    Background worker for long-running daily review preview.
    """

    result_ready = QtCore.Signal(object)
    error_ready = QtCore.Signal(str)

    def __init__(
        self,
        engine: DailyMarketReviewEngine,
        trade_date: date,
        run_llm: bool,
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.engine: DailyMarketReviewEngine = engine
        self.trade_date: date = trade_date
        self.run_llm: bool = run_llm

    def run(self) -> None:
        """
        Run the blocking provider/AI pipeline outside the UI thread.
        """
        try:
            result = self.engine.run_preview(
                self.trade_date,
                run_llm=self.run_llm,
            )
        except Exception as exc:
            self.error_ready.emit(f"{type(exc).__name__}: {exc}")
            return
        self.result_ready.emit(result)


class DailyMarketReviewWidget(QtWidgets.QWidget):
    """
    Standalone daily market review workspace.
    """

    workspace_title: str = "每日市场复盘"
    workspace_minimum_size: tuple[int, int] = (1100, 720)
    workspace_default_size: tuple[int, int] = (1280, 820)

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine) -> None:
        """"""
        super().__init__()
        self.main_engine: MainEngine = main_engine
        self.event_engine: EventEngine = event_engine
        self.engine: DailyMarketReviewEngine = main_engine.get_engine(APP_NAME)
        self.preview_worker: DailyReviewPreviewWorker | None = None

        self.setWindowTitle(self.workspace_title)
        self.setMinimumSize(*self.workspace_minimum_size)
        self.resize(*self.workspace_default_size)

        self.trade_date_edit = QtWidgets.QDateEdit()
        self.trade_date_edit.setCalendarPopup(True)
        self.trade_date_edit.setDate(QtCore.QDate.currentDate())
        self.run_llm_checkbox = QtWidgets.QCheckBox("运行 AI 编排")
        self.load_latest_button = QtWidgets.QPushButton("加载最新复盘")
        self.load_latest_button.clicked.connect(self.load_latest_report)
        self.run_preview_button = QtWidgets.QPushButton("运行预览")
        self.run_preview_button.clicked.connect(self.run_preview)
        self.preview_status_label = QtWidgets.QLabel("就绪")
        self.report_browser = QtWidgets.QTextBrowser()
        self.report_browser.setOpenExternalLinks(True)
        self.raw_output_text = QtWidgets.QPlainTextEdit()
        self.raw_output_text.setReadOnly(True)
        self.raw_output_text.setLineWrapMode(
            QtWidgets.QPlainTextEdit.LineWrapMode.WidgetWidth
        )

        self.watch_table = QtWidgets.QTableWidget(0, 7)
        self.watch_table.setHorizontalHeaderLabels(
            ["股票", "名称", "角色", "动作", "资金类型", "条件", "龙虎榜摘要"]
        )
        self.watch_table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.watch_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )

        self.history_results: list[DailyMarketReviewReportResult] = []
        self.history_table = QtWidgets.QTableWidget(0, 4)
        self.history_table.setHorizontalHeaderLabels(["交易日", "状态", "标题", "信息"])
        self.history_table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.history_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.history_table.cellDoubleClicked.connect(self.load_history_row)
        self.refresh_history_button = QtWidgets.QPushButton("刷新历史报告")
        self.refresh_history_button.clicked.connect(self.refresh_history_reports)

        self.signal_text = QtWidgets.QPlainTextEdit()
        self.signal_text.setReadOnly(True)
        self.signal_text.setPlainText("市场信号流水线未接入。")

        self.validation_date_edit = QtWidgets.QDateEdit()
        self.validation_date_edit.setCalendarPopup(True)
        self.validation_date_edit.setDate(QtCore.QDate.currentDate())
        self.validate_button = QtWidgets.QPushButton("验证观察计划")
        self.validate_button.clicked.connect(self.validate_next_day)
        self.validation_text = QtWidgets.QPlainTextEdit()
        self.validation_text.setReadOnly(True)

        self.config_text = QtWidgets.QPlainTextEdit()
        self.config_text.setReadOnly(True)
        self.config_text.setPlainText(
            "\n".join(
                [
                    "每日市场复盘配置边界：",
                    "1. 复用 vn.py database.* 和 PostgreSQL。",
                    "2. 行情优先复用 vn.py Gateway/Datafeed；未开通 QMT 时可用 AKShare 研究链路。",
                    "3. 新闻、公告和财报复用当前入库服务。",
                    "4. AI 输出只生成报告和观察计划，不直接创建订单。",
                    "5. 勾选“运行 AI 编排”后，会在 Evidence Pack 之上执行多阶段复盘。",
                    "6. AI provider、model、API key 环境变量、thinking 和超时时间复用全局 AI 配置。",
                    "7. 未配置 key 或模型调用失败时，系统会保留确定性报告并记录审计。",
                ]
            )
        )

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.addTab(self.create_report_tab(), DAILY_MARKET_REVIEW_TAB_TITLES[0])
        self.tabs.addTab(self.create_watch_tab(), DAILY_MARKET_REVIEW_TAB_TITLES[1])
        self.tabs.addTab(self.create_history_tab(), DAILY_MARKET_REVIEW_TAB_TITLES[2])
        self.tabs.addTab(self.create_signal_tab(), DAILY_MARKET_REVIEW_TAB_TITLES[3])
        self.tabs.addTab(self.create_validation_tab(), DAILY_MARKET_REVIEW_TAB_TITLES[4])
        self.tabs.addTab(self.create_config_tab(), DAILY_MARKET_REVIEW_TAB_TITLES[5])

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.tabs)
        self.setLayout(layout)

        self.load_latest_report()

    def create_report_tab(self) -> QtWidgets.QWidget:
        """
        Create report tab.
        """
        widget = QtWidgets.QWidget()
        controls = QtWidgets.QHBoxLayout()
        controls.addWidget(QtWidgets.QLabel("交易日"))
        controls.addWidget(self.trade_date_edit)
        controls.addWidget(self.run_llm_checkbox)
        controls.addWidget(self.load_latest_button)
        controls.addWidget(self.run_preview_button)
        controls.addWidget(self.preview_status_label)
        controls.addStretch()

        layout = QtWidgets.QVBoxLayout()
        layout.addLayout(controls)
        report_tabs = QtWidgets.QTabWidget()
        report_tabs.addTab(self.report_browser, "报告正文")
        report_tabs.addTab(self.raw_output_text, "原始输出")
        layout.addWidget(report_tabs)
        widget.setLayout(layout)
        return widget

    def create_watch_tab(self) -> QtWidgets.QWidget:
        """
        Create watch-plan tab.
        """
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.watch_table)
        widget.setLayout(layout)
        return widget

    def create_history_tab(self) -> QtWidgets.QWidget:
        """
        Create report history tab.
        """
        widget = QtWidgets.QWidget()
        controls = QtWidgets.QHBoxLayout()
        controls.addWidget(self.refresh_history_button)
        controls.addStretch()

        layout = QtWidgets.QVBoxLayout()
        layout.addLayout(controls)
        layout.addWidget(self.history_table)
        widget.setLayout(layout)
        return widget

    def create_signal_tab(self) -> QtWidgets.QWidget:
        """
        Create market-signal tab.
        """
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.signal_text)
        widget.setLayout(layout)
        return widget

    def create_validation_tab(self) -> QtWidgets.QWidget:
        """
        Create next-day validation tab.
        """
        widget = QtWidgets.QWidget()
        controls = QtWidgets.QHBoxLayout()
        controls.addWidget(QtWidgets.QLabel("验证日"))
        controls.addWidget(self.validation_date_edit)
        controls.addWidget(self.validate_button)
        controls.addStretch()

        layout = QtWidgets.QVBoxLayout()
        layout.addLayout(controls)
        layout.addWidget(self.validation_text)
        widget.setLayout(layout)
        return widget

    def create_config_tab(self) -> QtWidgets.QWidget:
        """
        Create config explanation tab.
        """
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.config_text)
        widget.setLayout(layout)
        return widget

    def load_latest_report(self) -> None:
        """
        Load latest report into the workspace.
        """
        self.apply_report_result(self.engine.load_latest_report())
        self.refresh_history_reports()

    def run_preview(self) -> None:
        """
        Run one preview request.
        """
        if self.preview_worker is not None and self.preview_worker.isRunning():
            self.preview_status_label.setText("已有复盘任务运行中，请稍候。")
            return

        trade_date = self._qdate_to_date(self.trade_date_edit.date())
        run_llm = self.run_llm_checkbox.isChecked()
        self.run_preview_button.setEnabled(False)
        self.load_latest_button.setEnabled(False)
        self.run_preview_button.setText("加载中...")
        self.preview_status_label.setText(
            "正在运行 AI 编排，窗口可继续查看历史报告。"
            if run_llm
            else "正在读取数据并生成复盘。"
        )
        self.report_browser.setMarkdown(
            "## 复盘生成中\n\n"
            "- 正在读取全市场数据、新闻、财报和复盘证据。\n"
            "- 勾选 AI 编排时会等待模型返回，完成后自动刷新报告正文。"
        )

        worker = DailyReviewPreviewWorker(
            self.engine,
            trade_date,
            run_llm=run_llm,
            parent=self,
        )
        worker.result_ready.connect(self._on_preview_result)
        worker.error_ready.connect(self._on_preview_error)
        worker.finished.connect(self._on_preview_finished)
        self.preview_worker = worker
        worker.start()

    def _on_preview_result(self, result: DailyMarketReviewReportResult) -> None:
        """
        Render a completed background preview result.
        """
        self.apply_report_result(result)
        self.refresh_history_reports()
        self.preview_status_label.setText(f"完成：{result.status} / {result.message}")

    def _on_preview_error(self, error_message: str) -> None:
        """
        Render background preview failure.
        """
        self.report_browser.setMarkdown(
            "# 每日市场复盘运行失败\n\n"
            "```text\n"
            f"{error_message}\n"
            "```"
        )
        self.raw_output_text.setPlainText(error_message)
        self.preview_status_label.setText("运行失败")

    def _on_preview_finished(self) -> None:
        """
        Restore controls after a background preview.
        """
        self.run_preview_button.setEnabled(True)
        self.load_latest_button.setEnabled(True)
        self.run_preview_button.setText("运行预览")
        if self.preview_worker is not None:
            self.preview_worker.deleteLater()
        self.preview_worker = None

    def refresh_history_reports(self) -> None:
        """
        Refresh report history rows.
        """
        self.history_results = list(self.engine.list_reports(limit=100))
        self.history_table.setRowCount(len(self.history_results))
        for row, result in enumerate(self.history_results):
            values = [
                result.trade_date.isoformat(),
                result.status,
                result.title,
                result.message,
            ]
            for column, value in enumerate(values):
                self.history_table.setItem(row, column, QtWidgets.QTableWidgetItem(str(value)))

    def load_history_row(self, row: int, column: int) -> None:
        """
        Load a selected historical report.
        """
        del column
        if row < 0 or row >= len(self.history_results):
            return
        self.apply_report_result(self.history_results[row])
        self.tabs.setCurrentIndex(0)

    def validate_next_day(self) -> None:
        """
        Validate current watch plan against a later date.
        """
        trade_date = self._qdate_to_date(self.trade_date_edit.date())
        validation_date = self._qdate_to_date(self.validation_date_edit.date())
        result = self.engine.validate_next_day(trade_date, validation_date)
        self.validation_text.setPlainText(format_validation_result_text(result))

    def apply_report_result(self, result: DailyMarketReviewReportResult) -> None:
        """
        Render one report result.
        """
        self.report_browser.setMarkdown(format_report_result_markdown(result))
        self.raw_output_text.setPlainText(format_report_result_raw_text(result))
        self.trade_date_edit.setDate(
            QtCore.QDate(
                result.trade_date.year,
                result.trade_date.month,
                result.trade_date.day,
            )
        )
        self.update_watch_table(extract_watch_items(result.markdown, result.watch_items))
        self.update_signal_text(result)

    def update_watch_table(self, items: list[dict[str, Any]]) -> None:
        """
        Render watch-plan rows.
        """
        self.watch_table.setRowCount(len(items))
        for row, item in enumerate(items):
            values = [
                item.get("symbol", ""),
                item.get("name", ""),
                item.get("role", ""),
                item.get("watch_action", ""),
                item.get("capital_type", ""),
                item.get("entry_condition", ""),
                item.get("lhb_summary", ""),
            ]
            for column, value in enumerate(values):
                self.watch_table.setItem(row, column, QtWidgets.QTableWidgetItem(str(value)))

    def update_signal_text(self, result: DailyMarketReviewReportResult) -> None:
        """
        Render evidence and audit summaries.
        """
        lines = [
            f"status={result.status}",
            f"trade_date={result.trade_date.isoformat()}",
            f"message={result.message}",
            "",
            "lhb:",
        ]
        lines.extend(_format_lhb_signal_lines(result.evidence))
        lines.extend(
            [
                "",
                "evidence:",
            ]
        )
        lines.extend(str(item) for item in result.evidence)
        lines.append("")
        lines.append("audit:")
        lines.extend(str(item) for item in result.audit)
        self.signal_text.setPlainText("\n".join(lines))

    def _qdate_to_date(self, value: QtCore.QDate) -> date:
        """
        Convert QDate to Python date.
        """
        return date(value.year(), value.month(), value.day())


def _extract_ai_payload(raw_text: str) -> dict[str, Any] | None:
    """
    Parse an AI JSON payload from a full text response.
    """
    text = _strip_markdown_fence(raw_text).strip()
    if not text:
        return None

    for candidate in (text, _slice_json_object(text)):
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _format_lhb_signal_lines(evidence: list[dict[str, Any]]) -> list[str]:
    """
    Render a compact dragon-tiger list evidence summary.
    """
    lhb_items = [
        item
        for item in evidence
        if str(item.get("source_type", "")).startswith("lhb_")
    ]
    if not lhb_items:
        return ["- 暂无龙虎榜席位证据"]
    return [
        f"- {item.get('evidence_id', '')} {item.get('source_type', '')}: "
        f"{str(item.get('content', ''))[:180]}"
        for item in lhb_items[:12]
    ]


def _slice_json_object(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return ""
    return text[start : end + 1]


def _strip_markdown_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = [
        line
        for line in stripped.splitlines()
        if not line.strip().startswith("```")
    ]
    return "\n".join(lines).strip()


def _extract_report_markdown_field(raw_text: str) -> str:
    """
    Best-effort fallback for imperfect JSON saved by an LLM response.
    """
    match = search(
        r'"report_markdown"\s*:\s*"(?P<markdown>.*?)"\s*,\s*"watch_items"',
        raw_text,
        flags=DOTALL,
    )
    if not match:
        return ""

    value = match.group("markdown")
    try:
        return str(json.loads(f'"{value}"')).strip()
    except Exception:
        return (
            value.replace(r"\n", "\n")
            .replace(r"\"", '"')
            .replace(r"\\", "\\")
            .strip()
        )
