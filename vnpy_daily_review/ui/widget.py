from datetime import date
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
    "市场信号",
    "验证复盘",
    "配置",
]


def format_report_result_markdown(result: DailyMarketReviewReportResult) -> str:
    """
    Render one report result as Markdown.
    """
    body = result.markdown or "_暂无每日市场复盘报告。_"
    return "\n\n".join(
        [
            f"# {result.title or '每日市场复盘'}",
            f"- trade_date: `{result.trade_date.isoformat()}`",
            f"- status: `{result.status}`",
            body,
        ]
    )


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
        self.report_browser = QtWidgets.QTextBrowser()
        self.report_browser.setOpenExternalLinks(True)

        self.watch_table = QtWidgets.QTableWidget(0, 5)
        self.watch_table.setHorizontalHeaderLabels(["股票", "名称", "角色", "动作", "条件"])
        self.watch_table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.watch_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )

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
                    "5. 完整数据流水线将在 P29 后续任务继续接入。",
                ]
            )
        )

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.addTab(self.create_report_tab(), DAILY_MARKET_REVIEW_TAB_TITLES[0])
        self.tabs.addTab(self.create_watch_tab(), DAILY_MARKET_REVIEW_TAB_TITLES[1])
        self.tabs.addTab(self.create_signal_tab(), DAILY_MARKET_REVIEW_TAB_TITLES[2])
        self.tabs.addTab(self.create_validation_tab(), DAILY_MARKET_REVIEW_TAB_TITLES[3])
        self.tabs.addTab(self.create_config_tab(), DAILY_MARKET_REVIEW_TAB_TITLES[4])

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
        controls.addStretch()

        layout = QtWidgets.QVBoxLayout()
        layout.addLayout(controls)
        layout.addWidget(self.report_browser)
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

    def run_preview(self) -> None:
        """
        Run one preview request.
        """
        trade_date = self._qdate_to_date(self.trade_date_edit.date())
        result = self.engine.run_preview(
            trade_date,
            run_llm=self.run_llm_checkbox.isChecked(),
        )
        self.apply_report_result(result)

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
        self.trade_date_edit.setDate(
            QtCore.QDate(
                result.trade_date.year,
                result.trade_date.month,
                result.trade_date.day,
            )
        )
        self.update_watch_table(result.watch_items)
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
                item.get("entry_condition", ""),
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
            "evidence:",
        ]
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
