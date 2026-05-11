import ast
from importlib import import_module
from pathlib import Path

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
    assert TradingAgentsApp.display_name == "TradingAgents分析管理"
    assert TradingAgentsApp.show_on_toolbar is True
    assert TradingAgentsApp.icon_name
    assert Path(TradingAgentsApp.icon_name).name == "tradingagents_analysis.svg"
    assert Path(TradingAgentsApp.icon_name).exists()


def test_tradingagents_widget_opens_as_standalone_workspace_window():
    """TradingAgents should open like CTA as a large standalone app window."""
    from vnpy_tradingagents.ui.widget import TradingAgentsWidget

    assert not getattr(TradingAgentsWidget, "dock_widget", False)
    assert TradingAgentsWidget.workspace_minimum_size == (1100, 720)
    assert TradingAgentsWidget.workspace_title == "TradingAgents分析管理"

    source = Path("vnpy/trader/ui/mainwindow.py").read_text(encoding="utf-8")
    assert "app_docks" not in source
    assert "dock_widget" not in source


def test_main_window_can_pin_tradingagents_on_left_toolbar():
    """TradingAgents analysis should be pinnable on the left toolbar."""
    source = Path("vnpy/trader/ui/mainwindow.py").read_text(encoding="utf-8")

    assert 'getattr(app, "show_on_toolbar", True)' in source


def test_analysis_history_table_has_report_jump_entry():
    """History table should expose an explicit report jump column."""
    from vnpy_tradingagents.ui.widget import (
        HISTORY_COLUMNS,
        HISTORY_REPORT_COLUMN,
        REPORT_TAB_TITLE,
    )

    assert HISTORY_COLUMNS[-1] == "分析报告"
    assert HISTORY_REPORT_COLUMN == len(HISTORY_COLUMNS) - 1
    assert REPORT_TAB_TITLE == "分析报告"


def test_news_search_tab_has_fuzzy_query_controls():
    """TradingAgents workspace should expose a normalized news fuzzy-search tab."""
    from vnpy_tradingagents.ui.widget import (
        NEWS_COLUMNS,
        NEWS_TAB_TITLE,
        build_news_event_detail_text,
    )
    from vnpy_router.event_storage import NewsEvent

    assert NEWS_TAB_TITLE == "新闻查询"
    assert "标题" in NEWS_COLUMNS
    assert "可信度" in NEWS_COLUMNS

    detail = build_news_event_detail_text(
        NewsEvent(
            event_id="event-1",
            vt_symbol="600519.SSE",
            title="贵州茅台分红公告",
            summary="现金分红预案",
            event_type="announcement",
            occurred_at=datetime(2024, 1, 3),
            source="cninfo",
            provider_name="manual",
            url="https://example.test/1",
            trust_score=0.95,
            relevance_score=0.8,
        )
    )

    assert "贵州茅台分红公告" in detail
    assert "600519.SSE" in detail
    assert "https://example.test/1" in detail


def test_financial_context_tab_has_refresh_and_trigger_helpers():
    """TradingAgents workspace should expose financial context query and backfill controls."""
    from vnpy_tradingagents.ui.widget import (
        FINANCIAL_COLUMNS,
        FINANCIAL_TAB_TITLE,
        build_financial_context_detail_text,
        build_financial_ingestion_status_text,
    )

    assert FINANCIAL_TAB_TITLE == "财报数据"
    assert "报表" in FINANCIAL_COLUMNS
    assert "质量" in FINANCIAL_COLUMNS

    detail = build_financial_context_detail_text(
        {
            "vt_symbol": "600519.SSE",
            "quality_status": "primary",
            "statements": {
                "income_statement": {
                    "report_period": "2024-12-31",
                    "announcement_date": "2025-04-01",
                    "provider_name": "akshare_sina",
                    "quality_status": "primary",
                    "fields": {"营业收入": 1200.0, "净利润": 320.0},
                }
            },
            "documents": [
                {
                    "title": "贵州茅台2024年年度报告",
                    "source": "cninfo",
                    "pdf_url": "https://static.cninfo.com.cn/finalpage.pdf",
                }
            ],
        }
    )

    assert "vt_symbol=600519.SSE" in detail
    assert "quality_status=primary" in detail
    assert "income_statement" in detail
    assert "营业收入" in detail
    assert "贵州茅台2024年年度报告" in detail

    status_text = build_financial_ingestion_status_text(
        {
            "state": "completed",
            "enabled": True,
            "last_symbols": ["600519.SSE", "000001.SZSE"],
            "last_summary": {
                "statement_count": 3,
                "indicator_count": 2,
                "document_count": 1,
                "payload_snapshot_count": 2,
                "errors": {"600519.SSE": "timeout"},
            },
        }
    )
    assert "state=completed" in status_text
    assert "600519.SSE,000001.SZSE" in status_text
    assert "statement_count=3" in status_text
    assert "600519.SSE: timeout" in status_text


def test_tradingagents_config_tab_collects_related_settings_only():
    """TradingAgents workspace should own AI and news-related settings."""
    from vnpy_tradingagents.ui.widget import (
        CONFIG_TAB_TITLE,
        TRADINGAGENTS_CONFIG_KEYS,
        collect_tradingagents_config_keys,
        news_symbols_help_text,
    )

    keys = collect_tradingagents_config_keys()

    assert CONFIG_TAB_TITLE == "配置"
    assert "tradingagents.llm_provider" in keys
    assert "news.ingestion.enabled" in keys
    assert "news.ingestion.symbols" in keys
    assert "news.ingestion.symbol_batch_size" in keys
    assert "database.name" not in keys
    assert keys == TRADINGAGENTS_CONFIG_KEYS

    help_text = news_symbols_help_text()
    assert "留空" in help_text
    assert "全市场逐股" in help_text
    assert "vn.py 已缓存合约" in help_text
    assert "AKShare A 股列表" in help_text
    assert "分批轮询" in help_text


def test_analysis_record_markdown_renders_params_and_report():
    """History detail should produce Markdown suitable for QTextBrowser display."""
    from vnpy_tradingagents.storage import AgentAnalysisRecord
    from vnpy_tradingagents.ui.widget import build_analysis_record_markdown

    record = AgentAnalysisRecord(
        run_id="manual-1",
        vt_symbol="600519.SSE",
        trade_date="2026-05-08",
        mode="manual_analysis",
        model_provider="zhipu",
        model_name="glm-4.7",
        prompt_version="ashare-context-v1",
        snapshot_ids=["bar:600519.SSE:20260508"],
        context={"manual_analysis": {"start": "2026-05-01", "end": "2026-05-08"}},
        created_at="2026-05-08 11:00:00",
        report="## 原始报告\nAI 观点",
        raw_state={"status": "completed"},
        error_message="",
        rating="Buy",
        confidence=0.82,
        action="buy",
        target_weight_hint=0.15,
        holding_period_hint="20d",
        risk_notes="回撤风险",
    )

    markdown = build_analysis_record_markdown(record)

    assert markdown.startswith("# TradingAgents 分析报告")
    assert "600519.SSE" in markdown
    assert "glm-4.7" in markdown
    assert "rating: Buy" in markdown
    assert "action: buy" in markdown
    assert "2026-05-01" in markdown
    assert "## 原始报告" in markdown


def test_analysis_record_markdown_includes_financial_context_versions():
    """Report tab should show the financial statement versions used by that run."""
    from vnpy_tradingagents.storage import AgentAnalysisRecord
    from vnpy_tradingagents.ui.widget import build_analysis_record_markdown

    record = AgentAnalysisRecord(
        run_id="manual-financial-1",
        vt_symbol="600519.SSE",
        trade_date="2026-05-08",
        mode="manual_analysis",
        model_provider="zhipu",
        model_name="glm-4.7",
        prompt_version="ashare-context-v1",
        snapshot_ids=[],
        context={
            "financials": {
                "quality_status": "primary",
                "statements": {
                    "income_statement": {
                        "report_period": "2024-12-31",
                        "announcement_date": "2025-04-01",
                        "provider_name": "akshare_sina",
                        "quality_status": "primary",
                    }
                },
                "documents": [
                    {
                        "title": "贵州茅台2024年年度报告",
                        "source": "cninfo",
                        "pdf_url": "https://static.cninfo.com.cn/finalpage.pdf",
                    }
                ],
            }
        },
        created_at="2026-05-08 11:00:00",
        report="AI 观点",
        raw_state={},
        error_message="",
        rating=None,
        confidence=None,
        action=None,
        target_weight_hint=None,
        holding_period_hint=None,
        risk_notes=None,
    )

    markdown = build_analysis_record_markdown(record)

    assert "## 本次使用的财报上下文" in markdown
    assert "income_statement" in markdown
    assert "2024-12-31" in markdown
    assert "贵州茅台2024年年度报告" in markdown


def test_engine_delegates_analysis_history_reader():
    """TradingAgentsEngine should expose persisted analysis history to the UI."""
    engine = TradingAgentsEngine(None, EventEngine())  # type: ignore[arg-type]
    reader = FakeAnalysisHistoryReader()

    engine.set_analysis_history_reader(reader)
    records = engine.load_analysis_history("600519.SSE", limit=3)

    assert records == ["record-1"]
    assert reader.calls == [("600519.SSE", 3)]


def test_engine_delegates_news_event_search_reader():
    """TradingAgentsEngine should expose normalized news search to the UI."""
    engine = TradingAgentsEngine(None, EventEngine())  # type: ignore[arg-type]
    reader = FakeNewsEventSearchReader()

    engine.set_news_event_reader(reader)
    records = engine.search_news_events(
        keyword="分红",
        vt_symbol="600519",
        event_type="announcement",
        limit=20,
    )

    assert records == ["news-1"]
    assert reader.calls == [("分红", "600519", "announcement", 20)]


def test_veighna_trader_example_registers_tradingagents_app():
    """The source startup example should expose TradingAgents in the vn.py UI."""
    tree = ast.parse(Path("examples/veighna_trader/run.py").read_text(encoding="utf-8"))

    imports_app = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "vnpy_tradingagents"
        and any(alias.name == "TradingAgentsApp" for alias in node.names)
        for node in ast.walk(tree)
    )
    registers_app = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_app"
        and node.args
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == "TradingAgentsApp"
        for node in ast.walk(tree)
    )

    assert imports_app
    assert registers_app


def test_veighna_trader_example_registers_akshare_gateway():
    """The local startup example should expose AKShare read-only quotes in the vn.py UI."""
    tree = ast.parse(Path("examples/veighna_trader/run.py").read_text(encoding="utf-8"))

    registers_gateway = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "add_optional_gateway"
        and len(node.args) == 2
        and isinstance(node.args[1], ast.Call)
        and isinstance(node.args[1].func, ast.Name)
        and node.args[1].func.id == "optional_class"
        and len(node.args[1].args) == 2
        and isinstance(node.args[1].args[0], ast.Constant)
        and node.args[1].args[0].value == "vnpy_akshare_gateway"
        and isinstance(node.args[1].args[1], ast.Constant)
        and node.args[1].args[1].value == "AkshareGateway"
        for node in ast.walk(tree)
    )

    assert registers_gateway


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


class FakeAnalysisHistoryReader:
    """Fake history reader for engine/UI delegation tests."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def load_analysis_history(self, vt_symbol: str = "", limit: int = 100):
        self.calls.append((vt_symbol, limit))
        return ["record-1"]


class FakeNewsEventSearchReader:
    """Fake news search reader for engine/UI delegation tests."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, int]] = []

    def search_news_events(
        self,
        keyword: str = "",
        vt_symbol: str = "",
        event_type: str = "",
        limit: int = 100,
    ):
        self.calls.append((keyword, vt_symbol, event_type, limit))
        return ["news-1"]
