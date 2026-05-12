from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from typing import Any

from vnpy.trader.setting import SETTING_FILENAME, SETTINGS
from vnpy.trader.engine import MainEngine
from vnpy.trader.ui import QtCore, QtWidgets
from vnpy.trader.utility import load_json, save_json
from vnpy.event import EventEngine
from vnpy_router.event_storage import NewsEvent

from ..engine import TradingAgentsEngine
from ..manual_analysis import ManualAnalysisRequest, ManualAnalysisResult
from ..monitoring import ReplayRunStatus
from ..runtime import TradingAgentsMode, TradingAgentsRuntimeState
from ..storage import AgentAnalysisRecord


HISTORY_COLUMNS: list[str] = [
    "时间",
    "代码",
    "模式",
    "评级",
    "动作",
    "置信度",
    "run_id",
    "分析报告",
]
HISTORY_REPORT_COLUMN: int = len(HISTORY_COLUMNS) - 1
REPORT_TAB_TITLE: str = "分析报告"
NEWS_TAB_TITLE: str = "新闻查询"
NEWS_COLUMNS: list[str] = [
    "时间",
    "代码",
    "类型",
    "标题",
    "来源",
    "可信度",
    "相关度",
]
FINANCIAL_TAB_TITLE: str = "财报数据"
FINANCIAL_COLUMNS: list[str] = [
    "报告期",
    "报表",
    "公告日",
    "来源",
    "质量",
]
SEVEN_BOLL_TAB_TITLE: str = "七轨扫描"
SEVEN_BOLL_COLUMNS: list[str] = [
    "股票",
    "信号类型",
    "分数",
    "regime",
    "操作建议",
    "analysis_run_id",
    "analysis_status",
    "查看报告",
]
CONFIG_TAB_TITLE: str = "配置"
TRADINGAGENTS_API_KEY_FIELD: str = "tradingagents.api_key"
TRADINGAGENTS_CONFIG_PREFIXES: tuple[str, ...] = (
    "tradingagents.",
    "news.ingestion.",
    "news.entity.",
    "news.filter.",
    "news.llm_classifier.",
    "financial.ingestion.",
    "financial.context.",
    "seven_boll.",
)


def collect_tradingagents_config_keys() -> list[str]:
    """
    Return TradingAgents-owned settings in vn.py setting order.
    """
    return [
        key
        for key in SETTINGS
        if any(key.startswith(prefix) for prefix in TRADINGAGENTS_CONFIG_PREFIXES)
    ]


TRADINGAGENTS_CONFIG_KEYS: list[str] = collect_tradingagents_config_keys()


def news_symbols_help_text() -> str:
    """
    Explain the symbol-universe behavior for news ingestion.
    """
    return (
        "symbols 是新闻入库关注股票列表。留空不会立刻全市场逐股暴力拉取；"
        "系统会先用 news.entity.catalog_path，其次复用 vn.py 已缓存合约，"
        "最后懒加载 AKShare A 股列表生成股票池并分批轮询，"
        "每轮数量由 news.ingestion.symbol_batch_size 控制。"
    )


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


def build_analysis_record_detail_text(record: AgentAnalysisRecord) -> str:
    """
    Render a compact plain-text detail for the history side panel.
    """
    return "\n".join(
        [
            f"run_id={record.run_id}",
            f"symbol={record.vt_symbol}",
            f"created_at={record.created_at}",
            f"mode={record.mode} trade_date={record.trade_date}",
            f"provider={record.model_provider} model={record.model_name}",
            f"prompt={record.prompt_version}",
            f"rating={record.rating} confidence={_format_optional_float(record.confidence)}",
            f"action={record.action} target_weight={record.target_weight_hint}",
            f"holding_period={record.holding_period_hint}",
            f"risk={record.risk_notes}",
            f"error={record.error_message}",
        ]
    )


def build_analysis_record_markdown(record: AgentAnalysisRecord) -> str:
    """
    Render persisted TradingAgents output as Markdown for the report tab.
    """
    manual_params = record.context.get("manual_analysis", {})
    snapshot_ids = "\n".join(f"- `{snapshot_id}`" for snapshot_id in record.snapshot_ids)
    if not snapshot_ids:
        snapshot_ids = "- 无"

    return "\n\n".join(
        [
            "# TradingAgents 分析报告",
            "\n".join(
                [
                    f"- run_id: `{record.run_id}`",
                    f"- vt_symbol: `{record.vt_symbol}`",
                    f"- trade_date: `{record.trade_date}`",
                    f"- mode: `{record.mode}`",
                    f"- created_at: `{record.created_at}`",
                    f"- provider/model: `{record.model_provider or '-'} / {record.model_name or '-'}`",
                    f"- prompt_version: `{record.prompt_version or '-'}`",
                ]
            ),
            "## 分析参数\n\n```json\n" + _json_text(manual_params) + "\n```",
            "\n".join(
                [
                    "## 结论",
                    f"- rating: {record.rating or '-'}",
                    f"- confidence: {_format_optional_float(record.confidence)}",
                    f"- action: {record.action or '-'}",
                    f"- target_weight: {record.target_weight_hint}",
                    f"- holding_period: {record.holding_period_hint or '-'}",
                    f"- risk: {record.risk_notes or '-'}",
                    f"- error: {record.error_message or '-'}",
                ]
            ),
            "## 快照来源\n\n" + snapshot_ids,
            _build_financial_context_markdown(record.context.get("financials", {})),
            "## AI 返回报告\n\n" + (record.report or "_无报告_"),
            "## 原始状态\n\n```json\n" + _json_text(record.raw_state) + "\n```",
        ]
    )


def build_news_event_detail_text(event: NewsEvent) -> str:
    """
    Render one normalized news event for the search detail panel.
    """
    return "\n".join(
        [
            f"event_id={event.event_id}",
            f"symbol={event.vt_symbol}",
            f"type={event.event_type}",
            f"time={event.occurred_at}",
            f"title={event.title}",
            f"summary={event.summary}",
            f"source={event.source}",
            f"provider={event.provider_name} {event.provider_version}".strip(),
            f"url={event.url}",
            f"trust={_format_optional_float(event.trust_score)}",
            f"relevance={_format_optional_float(event.relevance_score)}",
            f"link_confidence={_format_optional_float(event.link_confidence)}",
            f"link_reason={event.link_reason}",
            f"sector={event.sector}",
            f"topic={event.topic}",
            f"review_status={event.review_status}",
        ]
    )


def build_seven_boll_scan_summary_text(summary: Any) -> str:
    """
    Render a compact seven-boll scan summary for the UI.
    """
    if summary is None:
        return "status=empty"
    run_id = _value(summary, "run_id", "")
    status = _value(summary, "status", "")
    total = _value(summary, "total_symbols", 0)
    scanned = _value(summary, "scanned_symbols", 0)
    buy = len(_value(summary, "buy_candidates", []) or [])
    sell = len(_value(summary, "sell_candidates", []) or [])
    return f"run={run_id} status={status} total={total} scanned={scanned} buy={buy} sell={sell}"


def _build_financial_context_markdown(financials: Any) -> str:
    """
    Render the financial context versions used by an analysis run.
    """
    if not isinstance(financials, dict) or not financials:
        return "## 本次使用的财报上下文\n\n- 无"

    lines = [
        "## 本次使用的财报上下文",
        "",
        f"- quality_status: `{financials.get('quality_status', '-')}`",
    ]
    statements = financials.get("statements") or {}
    if statements:
        lines.append("")
        lines.append("| 报表 | 报告期 | 公告日 | Provider | 质量 |")
        lines.append("| --- | --- | --- | --- | --- |")
        for statement_type, statement in statements.items():
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(statement_type),
                        str(statement.get("report_period", "-")),
                        str(statement.get("announcement_date", "-")),
                        str(statement.get("provider_name", "-")),
                        str(statement.get("quality_status", "-")),
                    ]
                )
                + " |"
            )

    documents = financials.get("documents") or []
    if documents:
        lines.append("")
        lines.append("### 官方报告")
        for document in documents:
            title = document.get("title", "-")
            source = document.get("source", document.get("provider_name", "-"))
            url = document.get("pdf_url", document.get("url", ""))
            if url:
                lines.append(f"- [{title}]({url}) `{source}`")
            else:
                lines.append(f"- {title} `{source}`")
    return "\n".join(lines)


def build_financial_context_detail_text(context: dict[str, Any]) -> str:
    """
    Render structured financial context for the UI detail panel.
    """
    statements = context.get("statements") or {}
    documents = context.get("documents") or []
    lines = [
        f"vt_symbol={context.get('vt_symbol', '-')}",
        f"quality_status={context.get('quality_status', '-')}",
        "statements:",
    ]
    for statement_type, statement in statements.items():
        fields = statement.get("fields") or {}
        lines.extend(
            [
                f"- {statement_type}",
                f"  report_period={statement.get('report_period', '-')}",
                f"  announcement_date={statement.get('announcement_date', '-')}",
                f"  provider={statement.get('provider_name', '-')}",
                f"  quality={statement.get('quality_status', '-')}",
                "  fields=" + _json_text(fields),
            ]
        )

    lines.append("documents:")
    for document in documents:
        lines.extend(
            [
                f"- {document.get('title', '-')}",
                f"  source={document.get('source', document.get('provider_name', '-'))}",
                f"  pdf_url={document.get('pdf_url', document.get('url', '-'))}",
            ]
        )
    return "\n".join(lines)


def build_financial_ingestion_status_text(status: dict[str, Any]) -> str:
    """
    Render financial-ingestion scheduler progress for the UI detail panel.
    """
    summary = status.get("last_summary") or {}
    errors = summary.get("errors") or {}
    lines = [
        f"state={status.get('state', '-')}",
        f"enabled={status.get('enabled', '-')}",
        f"active={status.get('active', '-')}",
        f"symbol_count={status.get('symbol_count', 0)}",
        f"symbol_batch_size={status.get('symbol_batch_size', 0)}",
        "schedule_times=" + ",".join(str(item) for item in status.get("schedule_times", [])),
        "last_symbols=" + ",".join(str(item) for item in status.get("last_symbols", [])),
        "last_failed_symbols="
        + ",".join(str(item) for item in status.get("last_failed_symbols", [])),
        f"last_started_at={status.get('last_started_at', '-')}",
        f"last_finished_at={status.get('last_finished_at', '-')}",
        f"last_error={status.get('last_error', '')}",
        f"cancel_requested={status.get('cancel_requested', False)}",
        "summary:",
        f"  statement_count={summary.get('statement_count', 0)}",
        f"  indicator_count={summary.get('indicator_count', 0)}",
        f"  document_count={summary.get('document_count', 0)}",
        f"  payload_snapshot_count={summary.get('payload_snapshot_count', 0)}",
    ]
    degraded_sources = summary.get("degraded_sources") or []
    if degraded_sources:
        lines.append("  degraded_sources=" + ",".join(str(item) for item in degraded_sources))
    if errors:
        lines.append("errors:")
        for key, value in errors.items():
            lines.append(f"- {key}: {value}")
    return "\n".join(lines)


def _json_text(data: Any) -> str:
    """
    Convert arbitrary JSON-like data to readable text.
    """
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True, default=str)


def _format_optional_float(value: float | None) -> str:
    """
    Format optional confidence values for UI text.
    """
    if value is None:
        return "-"
    return f"{value:.2f}"


def _value(source: Any, name: str, default: Any = None) -> Any:
    if isinstance(source, dict):
        return source.get(name, default)
    return getattr(source, name, default)


def _split_ui_symbols(value: str) -> tuple[str, ...]:
    text = str(value or "")
    for sep in (";", "，", "\n"):
        text = text.replace(sep, ",")
    return tuple(item.strip() for item in text.split(",") if item.strip())


def _set_markdown(widget: QtWidgets.QTextBrowser, markdown: str) -> None:
    """
    Set Markdown when supported by the active Qt binding.
    """
    if hasattr(widget, "setMarkdown"):
        widget.setMarkdown(markdown)
    else:
        widget.setPlainText(markdown)


def _load_merged_settings() -> dict[str, Any]:
    """
    Load vn.py settings with file values overriding defaults.
    """
    settings = dict(SETTINGS)
    settings.update(load_json(SETTING_FILENAME))
    return settings


def _load_setting_help_text() -> dict[str, str]:
    """
    Load global setting help lazily to avoid hard coupling during imports.
    """
    try:
        from vnpy.trader.ui.widget import SETTING_HELP_TEXT

        return SETTING_HELP_TEXT
    except Exception:
        return {}


def _coerce_config_setting_values(
    raw_values: dict[str, str],
    field_types: dict[str, type],
) -> tuple[dict[str, Any], dict[str, str]]:
    """
    Convert TradingAgents config text values while excluding plaintext secrets.
    """
    settings: dict[str, Any] = {}
    secrets: dict[str, str] = {}
    for field_name, value_text in raw_values.items():
        if field_name == TRADINGAGENTS_API_KEY_FIELD:
            if value_text.strip():
                secrets[field_name] = value_text
            continue

        field_type = field_types[field_name]
        if field_type is bool:
            field_value = value_text.strip().lower() in {"1", "true", "yes", "y", "on"}
        else:
            field_value = field_type(value_text)
        settings[field_name] = field_value
    return settings, secrets


class TradingAgentsWidget(QtWidgets.QWidget):
    """
    Standalone TradingAgents runtime and analysis workspace.
    """

    workspace_title: str = "TradingAgents分析管理"
    workspace_minimum_size: tuple[int, int] = (1100, 720)
    workspace_default_size: tuple[int, int] = (1280, 820)

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine) -> None:
        """"""
        super().__init__()
        self.main_engine: MainEngine = main_engine
        self.event_engine: EventEngine = event_engine
        self.engine: TradingAgentsEngine = main_engine.get_engine("TradingAgents")
        self.history_records: list[AgentAnalysisRecord] = []
        self.news_records: list[NewsEvent] = []
        self.financial_context: dict[str, Any] = {}

        self.setWindowTitle(self.workspace_title)
        self.setMinimumSize(*self.workspace_minimum_size)
        self.resize(*self.workspace_default_size)

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

        self.history_symbol_edit = QtWidgets.QLineEdit()
        self.history_symbol_edit.setPlaceholderText("留空查看全部，或输入 600519.SSE")
        self.history_limit_spin = QtWidgets.QSpinBox()
        self.history_limit_spin.setRange(1, 1000)
        self.history_limit_spin.setValue(100)
        self.refresh_history_button = QtWidgets.QPushButton("刷新历史")
        self.refresh_history_button.clicked.connect(self.refresh_analysis_history)
        self.history_table = QtWidgets.QTableWidget(0, len(HISTORY_COLUMNS))
        self.history_table.setHorizontalHeaderLabels(HISTORY_COLUMNS)
        self.history_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.history_table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.history_table.itemSelectionChanged.connect(self.show_selected_history)
        self.history_table.cellClicked.connect(self.handle_history_cell_clicked)
        self.history_detail_text = QtWidgets.QPlainTextEdit()
        self.history_detail_text.setReadOnly(True)
        self.news_keyword_edit = QtWidgets.QLineEdit()
        self.news_keyword_edit.setPlaceholderText("模糊搜索标题/摘要/代码/来源")
        self.news_symbol_edit = QtWidgets.QLineEdit()
        self.news_symbol_edit.setPlaceholderText("可选：600519 或 600519.SSE")
        self.news_event_type_edit = QtWidgets.QLineEdit()
        self.news_event_type_edit.setPlaceholderText("可选：announcement / industry / macro")
        self.news_limit_spin = QtWidgets.QSpinBox()
        self.news_limit_spin.setRange(1, 1000)
        self.news_limit_spin.setValue(100)
        self.news_search_button = QtWidgets.QPushButton("查询新闻")
        self.news_search_button.clicked.connect(self.search_news_events)
        self.news_table = QtWidgets.QTableWidget(0, len(NEWS_COLUMNS))
        self.news_table.setHorizontalHeaderLabels(NEWS_COLUMNS)
        self.news_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.news_table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.news_table.itemSelectionChanged.connect(self.show_selected_news)
        self.news_detail_text = QtWidgets.QPlainTextEdit()
        self.news_detail_text.setReadOnly(True)
        self.financial_symbol_edit = QtWidgets.QLineEdit()
        self.financial_symbol_edit.setPlaceholderText("留空展示最新财报")
        self.financial_periods_spin = QtWidgets.QSpinBox()
        self.financial_periods_spin.setRange(1, 20)
        self.financial_periods_spin.setValue(int(SETTINGS.get("financial.context.max_statement_periods", 4)))
        self.financial_refresh_button = QtWidgets.QPushButton("查询财报")
        self.financial_refresh_button.clicked.connect(self.refresh_financial_context)
        self.financial_trigger_button = QtWidgets.QPushButton("手动回补")
        self.financial_trigger_button.clicked.connect(self.trigger_financial_ingestion)
        self.financial_batch_trigger_button = QtWidgets.QPushButton("按批次回补")
        self.financial_batch_trigger_button.clicked.connect(self.trigger_financial_ingestion_batch)
        self.financial_status_button = QtWidgets.QPushButton("刷新任务状态")
        self.financial_status_button.clicked.connect(self.refresh_financial_ingestion_status)
        self.financial_cancel_button = QtWidgets.QPushButton("取消任务")
        self.financial_cancel_button.clicked.connect(self.cancel_financial_ingestion)
        self.financial_retry_button = QtWidgets.QPushButton("重试失败")
        self.financial_retry_button.clicked.connect(self.retry_failed_financial_ingestion)
        self.financial_table = QtWidgets.QTableWidget(0, len(FINANCIAL_COLUMNS))
        self.financial_table.setHorizontalHeaderLabels(FINANCIAL_COLUMNS)
        self.financial_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.financial_table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.financial_table.itemSelectionChanged.connect(self.show_selected_financial)
        self.financial_detail_text = QtWidgets.QPlainTextEdit()
        self.financial_detail_text.setReadOnly(True)
        self.financial_status_text = QtWidgets.QPlainTextEdit()
        self.financial_status_text.setReadOnly(True)
        self.seven_boll_symbol_edit = QtWidgets.QLineEdit()
        self.seven_boll_symbol_edit.setPlaceholderText("可选：600519.SSE,000001.SZSE")
        self.seven_boll_scan_button = QtWidgets.QPushButton("手动扫描")
        self.seven_boll_scan_button.clicked.connect(self.run_seven_boll_scan)
        self.seven_boll_refresh_button = QtWidgets.QPushButton("刷新结果")
        self.seven_boll_refresh_button.clicked.connect(self.refresh_seven_boll_scan)
        self.seven_boll_analysis_button = QtWidgets.QPushButton("单点分析")
        self.seven_boll_analysis_button.clicked.connect(self.run_selected_seven_boll_analysis)
        self.seven_boll_batch_analysis_button = QtWidgets.QPushButton("批量分析")
        self.seven_boll_batch_analysis_button.clicked.connect(self.run_batch_seven_boll_analysis)
        self.seven_boll_summary_text = QtWidgets.QPlainTextEdit()
        self.seven_boll_summary_text.setReadOnly(True)
        self.seven_boll_buy_table = QtWidgets.QTableWidget(0, len(SEVEN_BOLL_COLUMNS))
        self.seven_boll_buy_table.setHorizontalHeaderLabels(SEVEN_BOLL_COLUMNS)
        self.seven_boll_sell_table = QtWidgets.QTableWidget(0, len(SEVEN_BOLL_COLUMNS))
        self.seven_boll_sell_table.setHorizontalHeaderLabels(SEVEN_BOLL_COLUMNS)
        self.report_browser = QtWidgets.QTextBrowser()
        self.report_browser.setOpenExternalLinks(True)
        self.config_widgets: dict[str, tuple[QtWidgets.QLineEdit, type]] = {}
        self.config_secret_edit = QtWidgets.QLineEdit()
        self.config_secret_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.config_secret_edit.setPlaceholderText("可选：填写真实 LLM API key，不保存到 vt_setting.json")
        self.config_persist_secret_checkbox = QtWidgets.QCheckBox(
            "保存到系统钥匙串（可选 keyring）"
        )
        self.config_status_label = QtWidgets.QLabel()
        self.config_save_button = QtWidgets.QPushButton("保存 TradingAgents 配置")
        self.config_save_button.clicked.connect(self.save_config_settings)
        self.config_reload_button = QtWidgets.QPushButton("重新加载配置")
        self.config_reload_button.clicked.connect(self.reload_config_settings)

        self.tabs = QtWidgets.QTabWidget()
        self.control_tab = self.create_control_tab()
        self.history_tab = self.create_history_tab()
        self.news_tab = self.create_news_tab()
        self.financial_tab = self.create_financial_tab()
        self.seven_boll_tab = self.create_seven_boll_tab()
        self.report_tab = self.create_report_tab()
        self.config_tab = self.create_config_tab()
        self.tabs.addTab(self.control_tab, "运行控制")
        self.tabs.addTab(self.history_tab, "分析历史")
        self.tabs.addTab(self.news_tab, NEWS_TAB_TITLE)
        self.tabs.addTab(self.financial_tab, FINANCIAL_TAB_TITLE)
        self.tabs.addTab(self.seven_boll_tab, SEVEN_BOLL_TAB_TITLE)
        self.tabs.addTab(self.report_tab, REPORT_TAB_TITLE)
        self.tabs.addTab(self.config_tab, CONFIG_TAB_TITLE)

        root = QtWidgets.QVBoxLayout()
        root.addWidget(self.tabs)
        self.setLayout(root)

        self.refresh_state()
        self.refresh_analysis_history()

    def create_control_tab(self) -> QtWidgets.QWidget:
        """
        Create runtime-control and manual-analysis tab.
        """
        widget = QtWidgets.QWidget()
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
        widget.setLayout(form)
        return widget

    def create_history_tab(self) -> QtWidgets.QWidget:
        """
        Create analysis-history browser tab.
        """
        widget = QtWidgets.QWidget()
        filter_layout = QtWidgets.QHBoxLayout()
        filter_layout.addWidget(QtWidgets.QLabel("股票"))
        filter_layout.addWidget(self.history_symbol_edit)
        filter_layout.addWidget(QtWidgets.QLabel("数量"))
        filter_layout.addWidget(self.history_limit_spin)
        filter_layout.addWidget(self.refresh_history_button)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        splitter.addWidget(self.history_table)
        splitter.addWidget(self.history_detail_text)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        layout = QtWidgets.QVBoxLayout()
        layout.addLayout(filter_layout)
        layout.addWidget(splitter)
        widget.setLayout(layout)
        return widget

    def create_report_tab(self) -> QtWidgets.QWidget:
        """
        Create Markdown report display tab.
        """
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.report_browser)
        widget.setLayout(layout)
        return widget

    def create_news_tab(self) -> QtWidgets.QWidget:
        """
        Create fuzzy search tab for normalized news events.
        """
        widget = QtWidgets.QWidget()
        filter_layout = QtWidgets.QHBoxLayout()
        filter_layout.addWidget(QtWidgets.QLabel("关键词"))
        filter_layout.addWidget(self.news_keyword_edit)
        filter_layout.addWidget(QtWidgets.QLabel("股票"))
        filter_layout.addWidget(self.news_symbol_edit)
        filter_layout.addWidget(QtWidgets.QLabel("类型"))
        filter_layout.addWidget(self.news_event_type_edit)
        filter_layout.addWidget(QtWidgets.QLabel("数量"))
        filter_layout.addWidget(self.news_limit_spin)
        filter_layout.addWidget(self.news_search_button)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        splitter.addWidget(self.news_table)
        splitter.addWidget(self.news_detail_text)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        layout = QtWidgets.QVBoxLayout()
        layout.addLayout(filter_layout)
        layout.addWidget(splitter)
        widget.setLayout(layout)
        return widget

    def create_financial_tab(self) -> QtWidgets.QWidget:
        """
        Create structured financial-context query and manual backfill tab.
        """
        widget = QtWidgets.QWidget()
        filter_layout = QtWidgets.QHBoxLayout()
        filter_layout.addWidget(QtWidgets.QLabel("股票"))
        filter_layout.addWidget(self.financial_symbol_edit)
        filter_layout.addWidget(QtWidgets.QLabel("报告期数"))
        filter_layout.addWidget(self.financial_periods_spin)
        filter_layout.addWidget(self.financial_refresh_button)
        filter_layout.addWidget(self.financial_trigger_button)
        filter_layout.addWidget(self.financial_batch_trigger_button)
        filter_layout.addWidget(self.financial_status_button)
        filter_layout.addWidget(self.financial_cancel_button)
        filter_layout.addWidget(self.financial_retry_button)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        splitter.addWidget(self.financial_table)
        splitter.addWidget(self.financial_detail_text)
        splitter.addWidget(self.financial_status_text)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 1)

        layout = QtWidgets.QVBoxLayout()
        layout.addLayout(filter_layout)
        layout.addWidget(splitter)
        widget.setLayout(layout)
        return widget

    def create_seven_boll_tab(self) -> QtWidgets.QWidget:
        """
        Create seven-boll daily scan tab.
        """
        widget = QtWidgets.QWidget()
        filter_layout = QtWidgets.QHBoxLayout()
        filter_layout.addWidget(QtWidgets.QLabel("股票池"))
        filter_layout.addWidget(self.seven_boll_symbol_edit)
        filter_layout.addWidget(self.seven_boll_scan_button)
        filter_layout.addWidget(self.seven_boll_refresh_button)
        filter_layout.addWidget(self.seven_boll_analysis_button)
        filter_layout.addWidget(self.seven_boll_batch_analysis_button)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        splitter.addWidget(self.seven_boll_summary_text)
        splitter.addWidget(self.seven_boll_buy_table)
        splitter.addWidget(self.seven_boll_sell_table)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 3)

        layout = QtWidgets.QVBoxLayout()
        layout.addLayout(filter_layout)
        layout.addWidget(splitter)
        widget.setLayout(layout)
        return widget

    def create_config_tab(self) -> QtWidgets.QWidget:
        """
        Create TradingAgents-owned settings tab.
        """
        widget = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout()
        self._populate_config_form(form)

        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addWidget(self.config_save_button)
        button_layout.addWidget(self.config_reload_button)

        form.addRow("", self.config_secret_edit)
        form.addRow("", self.config_persist_secret_checkbox)
        form.addRow(button_layout)
        form.addRow("状态", self.config_status_label)

        inner = QtWidgets.QWidget()
        inner.setLayout(form)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(scroll)
        widget.setLayout(layout)
        return widget

    def _populate_config_form(self, form: QtWidgets.QFormLayout) -> None:
        """
        Populate editable TradingAgents settings.
        """
        settings = _load_merged_settings()
        help_text = _load_setting_help_text()

        for field_name in TRADINGAGENTS_CONFIG_KEYS:
            field_value = settings.get(field_name, SETTINGS.get(field_name, ""))
            field_type = type(SETTINGS.get(field_name, field_value))
            edit = QtWidgets.QLineEdit(str(field_value))
            form.addRow(f"{field_name} <{field_type.__name__}>", edit)
            self.config_widgets[field_name] = (edit, field_type)

            text = help_text.get(field_name, "")
            if field_name == "news.ingestion.symbols":
                text = f"{text}\n{news_symbols_help_text()}" if text else news_symbols_help_text()
            if text:
                label = QtWidgets.QLabel(text)
                label.setWordWrap(True)
                label.setStyleSheet("color: gray;")
                form.addRow("", label)

            if field_name == "tradingagents.api_key_env_var":
                secret_label = QtWidgets.QLabel(
                    "真实 API key 填下面的安全输入框；这里只保存到当前进程环境变量，"
                    "勾选 keyring 时保存到系统钥匙串。"
                )
                secret_label.setWordWrap(True)
                secret_label.setStyleSheet("color: gray;")
                form.addRow(f"{TRADINGAGENTS_API_KEY_FIELD} <secret>", secret_label)

    def save_config_settings(self) -> None:
        """
        Persist TradingAgents-owned settings to vt_setting.json.
        """
        raw_values: dict[str, str] = {}
        field_types: dict[str, type] = {}
        for field_name, item in self.config_widgets.items():
            widget, field_type = item
            raw_values[field_name] = widget.text()
            field_types[field_name] = field_type

        settings, secrets = _coerce_config_setting_values(raw_values, field_types)
        api_key = self.config_secret_edit.text().strip()
        if api_key:
            secrets[TRADINGAGENTS_API_KEY_FIELD] = api_key

        merged = _load_merged_settings()
        merged.update(settings)
        SETTINGS.update(settings)

        message = "TradingAgents 配置已保存，部分启动项需要重启 vn.py 后生效。"
        if secrets:
            try:
                from vnpy.trader.ui.widget import save_tradingagents_api_key_from_ui

                secret_result = save_tradingagents_api_key_from_ui(
                    merged,
                    secrets,
                    persist=self.config_persist_secret_checkbox.isChecked(),
                )
                if secret_result is not None:
                    message = f"{message}\n{secret_result.message}"
            except Exception as exc:
                message = f"{message}\nAPI key 保存失败：{exc}"

        try:
            apply_result = self.engine.apply_financial_ingestion_settings(merged)
            message = f"{message}\n财报定时任务已热更新：{apply_result}"
            self.refresh_financial_ingestion_status()
        except Exception as exc:
            message = f"{message}\n财报定时任务热更新失败：{exc}"

        save_json(SETTING_FILENAME, merged)
        self.config_secret_edit.clear()
        self.config_status_label.setText(message)

    def reload_config_settings(self) -> None:
        """
        Reload TradingAgents settings from current file/global state.
        """
        settings = _load_merged_settings()
        for field_name, item in self.config_widgets.items():
            widget, _field_type = item
            widget.setText(str(settings.get(field_name, SETTINGS.get(field_name, ""))))
        self.config_status_label.setText("TradingAgents 配置已重新加载。")

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
        if result.response is not None:
            self.history_symbol_edit.setText(result.response.vt_symbol)
            self.refresh_analysis_history(select_run_id=result.response.run_id)
            self.tabs.setCurrentWidget(self.history_tab)

    def load_replay_status(self, storage, run_id: str) -> None:
        """
        Load and display latest replay status by run id.
        """
        self.replay_status_text.setPlainText(
            load_replay_status_panel_text(storage, run_id)
        )

    def run_seven_boll_scan(self) -> None:
        """
        Trigger a manual seven-boll daily scan.
        """
        try:
            from vnpy_seven_boll.scanner import SevenBollScanRequest

            symbols = _split_ui_symbols(self.seven_boll_symbol_edit.text())
            summary = self.engine.run_seven_boll_scan(SevenBollScanRequest(symbols=symbols))
        except Exception as exc:
            self.seven_boll_summary_text.setPlainText(f"status=failed error={exc}")
            return
        self.show_seven_boll_scan(summary)

    def refresh_seven_boll_scan(self) -> None:
        """
        Load the latest persisted seven-boll scan.
        """
        try:
            summary = self.engine.load_latest_seven_boll_scan()
        except Exception as exc:
            self.seven_boll_summary_text.setPlainText(f"status=failed error={exc}")
            return
        self.show_seven_boll_scan(summary)

    def show_seven_boll_scan(self, summary: Any) -> None:
        """
        Render seven-boll scan summary and candidate tables.
        """
        self.seven_boll_summary_text.setPlainText(build_seven_boll_scan_summary_text(summary))
        self._populate_seven_boll_table(self.seven_boll_buy_table, _value(summary, "buy_candidates", []) or [])
        self._populate_seven_boll_table(self.seven_boll_sell_table, _value(summary, "sell_candidates", []) or [])

    def run_selected_seven_boll_analysis(self) -> None:
        """
        Trigger analysis for the selected seven-boll candidate.
        """
        vt_symbol = self._selected_seven_boll_symbol()
        if not vt_symbol:
            self.seven_boll_summary_text.setPlainText("status=invalid error=missing selected symbol")
            return
        try:
            run_id = self.engine.run_scan_analysis(vt_symbol)
        except Exception as exc:
            self.seven_boll_summary_text.setPlainText(f"status=failed error={exc}")
            return
        self.seven_boll_summary_text.setPlainText(f"analysis_status=queued run_id={run_id}")

    def run_batch_seven_boll_analysis(self) -> None:
        """
        Trigger batch analysis for current buy/sell candidates.
        """
        symbols = self._all_visible_seven_boll_symbols()
        try:
            run_ids = self.engine.run_batch_scan_analysis(symbols)
        except Exception as exc:
            self.seven_boll_summary_text.setPlainText(f"status=failed error={exc}")
            return
        self.seven_boll_summary_text.setPlainText("analysis_status=queued run_ids=" + ",".join(run_ids))

    def _populate_seven_boll_table(self, table: QtWidgets.QTableWidget, candidates: list[Any]) -> None:
        table.setRowCount(len(candidates))
        for row, result in enumerate(candidates):
            values = [
                _value(result, "vt_symbol", ""),
                ",".join(_value(result, "signal_types", ()) or ()),
                str(_value(result, "score", "")),
                _value(result, "regime", ""),
                _value(result, "action", ""),
                _value(result, "report_run_id", ""),
                _value(result, "analysis_status", "pending"),
                "查看报告",
            ]
            for column, value in enumerate(values):
                table.setItem(row, column, QtWidgets.QTableWidgetItem(str(value)))
        table.resizeColumnsToContents()

    def _selected_seven_boll_symbol(self) -> str:
        for table in (self.seven_boll_buy_table, self.seven_boll_sell_table):
            row = table.currentRow()
            if row >= 0:
                item = table.item(row, 0)
                return item.text() if item is not None else ""
        return ""

    def _all_visible_seven_boll_symbols(self) -> list[str]:
        symbols: list[str] = []
        for table in (self.seven_boll_buy_table, self.seven_boll_sell_table):
            for row in range(table.rowCount()):
                item = table.item(row, 0)
                if item is not None and item.text():
                    symbols.append(item.text())
        return symbols

    def search_news_events(self) -> None:
        """
        Search normalized news events by keyword/symbol/type.
        """
        try:
            self.news_records = self.engine.search_news_events(
                keyword=self.news_keyword_edit.text().strip(),
                vt_symbol=self.news_symbol_edit.text().strip(),
                event_type=self.news_event_type_edit.text().strip(),
                limit=self.news_limit_spin.value(),
            )
        except Exception as exc:
            self.news_records = []
            self.news_table.setRowCount(0)
            self.news_detail_text.setPlainText(f"status=failed error={exc}")
            return

        self.news_table.setRowCount(len(self.news_records))
        for row, event in enumerate(self.news_records):
            values = [
                str(event.occurred_at),
                event.vt_symbol,
                event.event_type,
                event.title,
                event.source or event.provider_name,
                _format_optional_float(event.trust_score),
                _format_optional_float(event.relevance_score),
            ]
            for column, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(value)
                item.setData(QtCore.Qt.ItemDataRole.UserRole, row)
                self.news_table.setItem(row, column, item)

        self.news_table.resizeColumnsToContents()
        if not self.news_records:
            self.news_detail_text.setPlainText("status=empty")
            return
        self.news_table.selectRow(0)
        self.show_selected_news()

    def show_selected_news(self) -> None:
        """
        Show detail for the selected news row.
        """
        row = self.news_table.currentRow()
        if row < 0 or row >= len(self.news_records):
            return
        self.news_detail_text.setPlainText(
            build_news_event_detail_text(self.news_records[row])
        )

    def refresh_financial_context(self) -> None:
        """
        Load structured financial context for one symbol or latest stored data.
        """
        vt_symbol = self.financial_symbol_edit.text().strip()

        try:
            self.financial_context = self.engine.load_financial_context(
                vt_symbol,
                max_periods=self.financial_periods_spin.value(),
            )
        except Exception as exc:
            self.financial_context = {}
            self.financial_table.setRowCount(0)
            self.financial_detail_text.setPlainText(f"status=failed error={exc}")
            return

        statements = self.financial_context.get("statements") or {}
        rows = list(statements.items())
        self.financial_table.setRowCount(len(rows))
        for row, item in enumerate(rows):
            statement_type, statement = item
            values = [
                str(statement.get("report_period", "")),
                statement_type,
                str(statement.get("announcement_date", "")),
                str(statement.get("provider_name", "")),
                str(statement.get("quality_status", "")),
            ]
            for column, value in enumerate(values):
                table_item = QtWidgets.QTableWidgetItem(value)
                table_item.setData(QtCore.Qt.ItemDataRole.UserRole, row)
                self.financial_table.setItem(row, column, table_item)

        self.financial_table.resizeColumnsToContents()
        self.financial_detail_text.setPlainText(
            build_financial_context_detail_text(self.financial_context)
        )

    def trigger_financial_ingestion(self) -> None:
        """
        Trigger one-off financial ingestion for the input symbol.
        """
        vt_symbol = self.financial_symbol_edit.text().strip()
        symbols = [vt_symbol] if vt_symbol else None
        try:
            message = self.engine.trigger_financial_ingestion(symbols)
        except Exception as exc:
            self.financial_detail_text.setPlainText(f"status=failed error={exc}")
            return
        self.financial_detail_text.setPlainText(f"status=triggered {message}")
        self.refresh_financial_ingestion_status()

    def trigger_financial_ingestion_batch(self) -> None:
        """
        Trigger one scheduler batch from the configured stock pool.
        """
        try:
            message = self.engine.trigger_financial_ingestion(None)
        except Exception as exc:
            self.financial_status_text.setPlainText(f"status=failed error={exc}")
            return
        self.financial_status_text.setPlainText(f"status=triggered {message}")
        self.refresh_financial_ingestion_status()

    def refresh_financial_ingestion_status(self) -> None:
        """
        Refresh financial-ingestion task progress.
        """
        try:
            status = self.engine.get_financial_ingestion_status()
        except Exception as exc:
            self.financial_status_text.setPlainText(f"status=failed error={exc}")
            return
        self.financial_status_text.setPlainText(
            build_financial_ingestion_status_text(status)
        )

    def cancel_financial_ingestion(self) -> None:
        """
        Request cancellation of the current financial-ingestion task.
        """
        result = self.engine.cancel_financial_ingestion()
        self.financial_status_text.setPlainText(f"cancel_requested={result}")
        self.refresh_financial_ingestion_status()

    def retry_failed_financial_ingestion(self) -> None:
        """
        Retry symbols that failed in the previous financial-ingestion task.
        """
        try:
            message = self.engine.retry_failed_financial_ingestion()
        except Exception as exc:
            self.financial_status_text.setPlainText(f"status=failed error={exc}")
            return
        self.financial_status_text.setPlainText(f"status=triggered {message}")
        self.refresh_financial_ingestion_status()

    def show_selected_financial(self) -> None:
        """
        Keep the full context visible when a financial row is selected.
        """
        if not self.financial_context:
            return
        self.financial_detail_text.setPlainText(
            build_financial_context_detail_text(self.financial_context)
        )

    def refresh_analysis_history(self, select_run_id: str = "") -> None:
        """
        Refresh persisted analysis history table.
        """
        vt_symbol = self.history_symbol_edit.text().strip()
        limit = self.history_limit_spin.value()
        try:
            self.history_records = self.engine.load_analysis_history(vt_symbol, limit)
        except Exception as exc:
            self.history_records = []
            self.history_table.setRowCount(0)
            self.history_detail_text.setPlainText(f"status=failed error={exc}")
            _set_markdown(self.report_browser, "")
            return

        self.history_table.setRowCount(len(self.history_records))
        for row, record in enumerate(self.history_records):
            values = [
                str(record.created_at),
                record.vt_symbol,
                record.mode,
                record.rating or "-",
                record.action or "-",
                _format_optional_float(record.confidence),
                record.run_id,
                "查看报告",
            ]
            for column, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(value)
                item.setData(QtCore.Qt.ItemDataRole.UserRole, row)
                self.history_table.setItem(row, column, item)

        self.history_table.resizeColumnsToContents()
        if not self.history_records:
            self.history_detail_text.setPlainText("status=empty")
            _set_markdown(self.report_browser, "")
            return

        selected_row = 0
        if select_run_id:
            for row, record in enumerate(self.history_records):
                if record.run_id == select_run_id:
                    selected_row = row
                    break
        self.history_table.selectRow(selected_row)
        self.show_selected_history()

    def show_selected_history(self) -> None:
        """
        Show details and Markdown report for the selected history row.
        """
        row = self.history_table.currentRow()
        if row < 0 or row >= len(self.history_records):
            return

        self.show_history_record(row)

    def handle_history_cell_clicked(self, row: int, column: int) -> None:
        """
        Jump to the full report only when the report entry is clicked.
        """
        if row < 0 or row >= len(self.history_records):
            return

        self.show_history_record(row)
        if column == HISTORY_REPORT_COLUMN:
            self.tabs.setCurrentWidget(self.report_tab)

    def show_history_record(self, row: int) -> None:
        """
        Render one history record into detail and report panes.
        """
        if row < 0 or row >= len(self.history_records):
            return

        record = self.history_records[row]
        self.history_detail_text.setPlainText(build_analysis_record_detail_text(record))
        _set_markdown(self.report_browser, build_analysis_record_markdown(record))
