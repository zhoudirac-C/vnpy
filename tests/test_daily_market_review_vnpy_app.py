import ast
from datetime import date
from decimal import Decimal
from importlib import import_module
from pathlib import Path


def make_daily_review_fake_provider():
    from vnpy_daily_review.domain import DailyStockSnapshot
    from vnpy_daily_review.service import DailyReviewDataBundle

    class FakeProvider:
        def load_data_bundle(self, trade_date: date) -> DailyReviewDataBundle:
            return DailyReviewDataBundle(
                trade_date=trade_date,
                stocks=[
                    DailyStockSnapshot(
                        symbol="001267.SZSE",
                        name="汇绿生态",
                        trade_date=trade_date,
                        open_price=Decimal("10"),
                        high_price=Decimal("11"),
                        low_price=Decimal("9.8"),
                        close_price=Decimal("10.8"),
                        pct_change=Decimal("8"),
                        volume=10000,
                        amount=Decimal("10800000"),
                        turnover_rate=Decimal("3.5"),
                        is_limit_up=False,
                        is_limit_down=False,
                        provider="fake",
                        sector="测试板块",
                    ),
                    DailyStockSnapshot(
                        symbol="600519.SSE",
                        name="贵州茅台",
                        trade_date=trade_date,
                        open_price=Decimal("100"),
                        high_price=Decimal("101"),
                        low_price=Decimal("98"),
                        close_price=Decimal("99"),
                        pct_change=Decimal("-1"),
                        volume=100,
                        amount=Decimal("9900000"),
                        turnover_rate=Decimal("0.2"),
                        is_limit_up=False,
                        is_limit_down=False,
                        provider="fake",
                        sector="白酒",
                    ),
                ],
                provider_records=[
                    {"provider": "fake", "data_type": "stock_snapshot", "row_count": 2}
                ],
            )

    return FakeProvider()


def test_daily_market_review_app_metadata_imports_ui_widget():
    """DailyMarketReviewApp should expose a standalone vn.py UI module."""
    from vnpy_daily_review import DailyMarketReviewApp

    ui_module = import_module(DailyMarketReviewApp.app_module + ".ui")

    assert hasattr(ui_module, DailyMarketReviewApp.widget_name)
    assert DailyMarketReviewApp.app_name == "DailyMarketReview"
    assert DailyMarketReviewApp.display_name == "每日市场复盘"
    assert DailyMarketReviewApp.show_on_toolbar is True
    assert DailyMarketReviewApp.icon_name
    assert Path(DailyMarketReviewApp.icon_name).name == "daily_review.svg"
    assert Path(DailyMarketReviewApp.icon_name).exists()


def test_daily_market_review_widget_exposes_required_workspace_tabs():
    """Daily review UI should be independent from TradingAgents and expose core tabs."""
    from vnpy_daily_review.ui.widget import (
        DAILY_MARKET_REVIEW_TAB_TITLES,
        DailyMarketReviewWidget,
    )

    assert DailyMarketReviewWidget.workspace_title == "每日市场复盘"
    assert DailyMarketReviewWidget.workspace_minimum_size == (1100, 720)
    assert DAILY_MARKET_REVIEW_TAB_TITLES == [
        "今日报告",
        "明日观察",
        "历史报告",
        "市场信号",
        "验证复盘",
        "配置",
    ]


def test_daily_market_review_engine_has_safe_not_configured_boundary():
    """Engine should be safe before the full data pipeline is wired."""
    from datetime import date

    from vnpy.event import EventEngine
    from vnpy_daily_review.engine import DailyMarketReviewEngine

    engine = DailyMarketReviewEngine(None, EventEngine())  # type: ignore[arg-type]

    latest = engine.load_latest_report()
    result = engine.run_preview(date(2026, 5, 11), run_llm=False)
    validation = engine.validate_next_day(date(2026, 5, 11), date(2026, 5, 12))

    assert latest.status == "not_configured"
    assert result.status == "not_configured"
    assert result.trade_date == date(2026, 5, 11)
    assert "未接入" in result.markdown
    assert validation.status == "not_configured"


def test_daily_market_review_ui_extracts_readable_ai_report_from_json_payload():
    """AI JSON payloads should be rendered as readable Markdown in the report tab."""
    from vnpy_daily_review.engine import DailyMarketReviewReportResult
    from vnpy_daily_review.ui.widget import (
        extract_report_markdown,
        extract_watch_items,
        format_report_result_markdown,
        format_report_result_raw_text,
    )

    raw_ai_payload = (
        '{"report_markdown":"## AI复盘\\n- 明日只观察分歧低吸。",'
        '"watch_items":[{"symbol":"001267.SZSE","name":"汇绿生态",'
        '"role":"AI风向标","watch_action":"wait_pullback",'
        '"entry_condition":"回踩承接","avoid_condition":"缩量追高",'
        '"position_rule":"轻仓观察","evidence_ids":["EVT-1"]}]}'
    )
    result = DailyMarketReviewReportResult(
        status="completed",
        trade_date=date(2026, 5, 11),
        title="2026-05-11 每日市场复盘",
        markdown=raw_ai_payload,
        watch_items=[],
        message="llm_completed",
    )

    rendered = format_report_result_markdown(result)
    raw_text = format_report_result_raw_text(result)

    assert extract_report_markdown(raw_ai_payload).startswith("## AI复盘")
    assert "report_markdown" not in rendered
    assert "明日只观察分歧低吸" in rendered
    assert extract_watch_items(raw_ai_payload, [])[0]["symbol"] == "001267.SZSE"
    assert "report_markdown" in raw_text


def test_daily_market_review_preview_runs_off_ui_thread():
    """Preview should not run the full AI/data pipeline directly in the Qt UI slot."""
    source = Path("vnpy_daily_review/ui/widget.py").read_text()
    tree = ast.parse(source)
    widget_class = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == "DailyMarketReviewWidget"
    )
    run_preview = next(
        node
        for node in widget_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "run_preview"
    )

    direct_calls = [
        node
        for node in ast.walk(run_preview)
        if isinstance(node, ast.Attribute) and node.attr == "run_preview"
    ]

    assert "class DailyReviewPreviewWorker" in source
    assert not direct_calls


def test_daily_market_review_engine_runs_migrated_pipeline_with_provider():
    """Engine should delegate to the migrated vn.py daily review service."""
    from vnpy.event import EventEngine
    from vnpy_daily_review.engine import DailyMarketReviewEngine
    from vnpy_daily_review.service import DailyReviewService

    engine = DailyMarketReviewEngine(None, EventEngine())  # type: ignore[arg-type]
    class FakeRepository:
        def __init__(self) -> None:
            self.saved = []

        def save_report_result(self, result):
            self.saved.append(result)

        def load_latest_report(self):
            return self.saved[-1] if self.saved else None

        def list_reports(self, limit=50):
            return list(reversed(self.saved[-limit:]))

    repository = FakeRepository()
    engine.set_review_service(
        DailyReviewService(make_daily_review_fake_provider(), repository=repository)
    )

    result = engine.run_preview(date(2026, 5, 11), run_llm=False)

    assert result.status == "completed"
    assert "每日市场复盘" in result.title
    assert "汇绿生态" in result.markdown
    assert result.watch_items
    assert result.evidence
    assert result.audit[0]["mode"] == "deterministic"
    assert repository.saved == [result]
    assert engine.load_latest_report() == result
    assert engine.list_reports(limit=10) == [result]


def test_daily_market_review_ai_orchestrator_overrides_report_with_audited_llm_output():
    """When requested, daily review should run auditable staged LLM composition."""
    from vnpy_daily_review.ai import DailyReviewAIOrchestrator, DailyReviewLLMResponse
    from vnpy_daily_review.service import DailyReviewService
    from vnpy_daily_review.storage import InMemoryDailyReviewRepository

    class FakeClient:
        def __init__(self) -> None:
            self.calls = []
            self.outputs = [
                DailyReviewLLMResponse(
                    content="市场处于修复观察，证据 EVT-20260511-0001。",
                    usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                ),
                DailyReviewLLMResponse(
                    content="主线聚焦测试板块，证据 EVT-20260511-0002。",
                    usage={"prompt_tokens": 11, "completion_tokens": 6, "total_tokens": 17},
                ),
                DailyReviewLLMResponse(
                    content="风向标选择汇绿生态，证据 EVT-20260511-0003。",
                    usage={"prompt_tokens": 12, "completion_tokens": 7, "total_tokens": 19},
                ),
                DailyReviewLLMResponse(
                    content="风险：追高和数据样本不足。",
                    usage={"prompt_tokens": 13, "completion_tokens": 8, "total_tokens": 21},
                ),
                DailyReviewLLMResponse(
                    content=(
                        '{"report_markdown":"## AI复盘\\n- 引用 EVT-20260511-0001。",'
                        '"watch_items":[{"symbol":"001267.SZSE","name":"汇绿生态",'
                        '"role":"AI风向标","watch_action":"分歧低吸观察",'
                        '"entry_condition":"回踩承接稳定","avoid_condition":"高开缩量追高",'
                        '"position_rule":"轻仓观察","evidence_ids":["EVT-20260511-0001"]}]}'
                    ),
                    usage={"prompt_tokens": 14, "completion_tokens": 9, "total_tokens": 23},
                ),
            ]

        def chat(self, messages, timeout_seconds, extra_body=None):
            self.calls.append(
                {
                    "messages": messages,
                    "timeout_seconds": timeout_seconds,
                    "extra_body": extra_body,
                }
            )
            return self.outputs[len(self.calls) - 1]

    client = FakeClient()
    repository = InMemoryDailyReviewRepository()
    service = DailyReviewService(
        make_daily_review_fake_provider(),
        repository=repository,
        ai_orchestrator=DailyReviewAIOrchestrator(
            client=client,
            provider="glm",
            model_name="glm-4.7",
            timeout_seconds=2700,
            max_retries=1,
            extra_body={"thinking": {"type": "enabled"}},
        ),
    )

    result = service.run_preview(date(2026, 5, 11), run_llm=True)

    assert result.status == "completed"
    assert result.message == "llm_completed"
    assert "AI复盘" in result.markdown
    assert result.watch_items[0]["role"] == "AI风向标"
    assert len(client.calls) == 5
    assert {call["timeout_seconds"] for call in client.calls} == {2700}
    assert client.calls[0]["extra_body"] == {"thinking": {"type": "enabled"}}
    llm_audit = [audit for audit in result.audit if audit.get("mode") == "llm"]
    assert [audit["stage"] for audit in llm_audit] == [
        "MarketRegimeAnalyst",
        "ThemeRotationAnalyst",
        "LeaderAnalyst",
        "RiskCritic",
        "WatchPlanWriter",
    ]
    assert all(audit["status"] == "completed" for audit in llm_audit)
    assert llm_audit[-1]["total_tokens"] == 23
    assert repository.load_latest_report() == result


def test_daily_market_review_ai_orchestrator_falls_back_with_failed_audit():
    """LLM failures should keep deterministic report usable and auditable."""
    from vnpy_daily_review.ai import DailyReviewAIOrchestrator
    from vnpy_daily_review.service import DailyReviewService

    class FailingClient:
        def chat(self, messages, timeout_seconds, extra_body=None):
            raise RuntimeError("model timeout")

    service = DailyReviewService(
        make_daily_review_fake_provider(),
        ai_orchestrator=DailyReviewAIOrchestrator(
            client=FailingClient(),
            provider="glm",
            model_name="glm-4.7",
            timeout_seconds=2700,
            max_retries=0,
        ),
    )

    result = service.run_preview(date(2026, 5, 11), run_llm=True)

    assert result.status == "partial"
    assert result.message.startswith("llm_failed_fallback_deterministic")
    assert "AI 编排失败" in result.markdown
    failed_audit = [audit for audit in result.audit if audit.get("status") == "failed"]
    assert failed_audit
    assert failed_audit[0]["stage"] == "MarketRegimeAnalyst"
    assert failed_audit[0]["error_message"] == "model timeout"
    assert result.watch_items


def test_daily_market_review_ai_orchestrator_reuses_tradingagents_llm_settings():
    """Daily review LLM config should reuse the existing vn.py AI provider settings."""
    from vnpy_daily_review.ai import build_daily_review_ai_orchestrator_from_settings

    orchestrator = build_daily_review_ai_orchestrator_from_settings(
        {
            "tradingagents.llm_provider": "zhipu",
            "tradingagents.api_key_env_var": "ZHIPU_API_KEY",
            "tradingagents.model": "glm-4.7",
            "tradingagents.backend_url": "",
            "tradingagents.replay_thinking_type": "enabled",
            "tradingagents.replay_timeout_seconds": 2700,
            "tradingagents.max_retries": 2,
            "tradingagents.max_completion_tokens": 2048,
        },
        environ={"ZHIPU_API_KEY": "secret-value"},
    )

    assert orchestrator is not None
    assert orchestrator.provider == "glm"
    assert orchestrator.model_name == "glm-4.7"
    assert orchestrator.timeout_seconds == 2700
    assert orchestrator.max_retries == 2
    assert orchestrator.extra_body == {"thinking": {"type": "enabled"}}

    missing_key = build_daily_review_ai_orchestrator_from_settings(
        {
            "tradingagents.llm_provider": "zhipu",
            "tradingagents.api_key_env_var": "ZHIPU_API_KEY",
        },
        environ={},
    )
    assert missing_key is None


def test_daily_market_review_provider_retries_and_falls_back_akshare_stock_snapshot(
    monkeypatch,
):
    """Daily review should not fail when the primary AKShare spot endpoint disconnects."""
    import vnpy_daily_review.providers as provider_module
    from vnpy_daily_review.providers import VnpyAkshareDailyReviewProvider

    class FakeMainEngine:
        def get_all_ticks(self):
            return []

        def get_contract(self, vt_symbol):
            del vt_symbol
            return None

    class FakeAkshare:
        def __init__(self) -> None:
            self.calls = []

        def stock_zh_a_spot_em(self):
            self.calls.append("stock_zh_a_spot_em")
            raise ConnectionError("spot disconnected")

        def stock_zh_a_spot(self):
            self.calls.append("stock_zh_a_spot")
            return [
                {
                    "代码": "sz001267",
                    "名称": "汇绿生态",
                    "最新价": 11,
                    "今开": 10,
                    "最高": 11,
                    "最低": 9.8,
                    "涨跌幅": 10,
                    "成交量": 1200,
                    "成交额": 132000,
                    "换手率": 3.1,
                }
            ]

        def stock_board_industry_name_em(self):
            return []

        def stock_zt_pool_em(self, date):
            del date
            return []

        def stock_lhb_detail_em(self, start_date, end_date):
            del start_date, end_date
            return []

    fake_akshare = FakeAkshare()
    monkeypatch.setattr(provider_module, "import_module", lambda name: fake_akshare)
    monkeypatch.setattr(provider_module, "sleep", lambda seconds: None)

    bundle = VnpyAkshareDailyReviewProvider(FakeMainEngine()).load_data_bundle(
        date(2026, 5, 11)
    )

    assert bundle.trade_date == date(2026, 5, 11)
    assert len(bundle.stocks) == 1
    assert bundle.stocks[0].symbol == "001267.SZSE"
    assert bundle.stocks[0].pct_change == Decimal("10")
    assert bundle.stocks[0].provider == "akshare:stock_zh_a_spot"
    assert provider_module._vt_symbol("bj920000") == "920000.BSE"
    assert fake_akshare.calls == [
        "stock_zh_a_spot_em",
        "stock_zh_a_spot_em",
        "stock_zh_a_spot",
    ]
    assert any(
        record["provider"] == "akshare"
        and record["status"] == "success"
        and record["row_count"] == 1
        and record["data_type"] == "stock_snapshot:stock_zh_a_spot"
        for record in bundle.provider_records
    )


def test_daily_market_review_provider_parses_akshare_lhb_amount_columns(monkeypatch):
    """Daily review should parse Eastmoney LHB amount columns from AKShare."""
    import vnpy_daily_review.providers as provider_module
    from vnpy_daily_review.providers import VnpyAkshareDailyReviewProvider

    class FakeMainEngine:
        def get_all_ticks(self):
            return []

        def get_contract(self, vt_symbol):
            del vt_symbol
            return None

    class FakeAkshare:
        def stock_zh_a_spot_em(self):
            return [
                {
                    "代码": "000062",
                    "名称": "深圳华强",
                    "最新价": 39.09,
                    "今开": 38,
                    "最高": 39.09,
                    "最低": 37.5,
                    "涨跌幅": 9.9887,
                    "成交量": 1000,
                    "成交额": 100000,
                }
            ]

        def stock_board_industry_name_em(self):
            return []

        def stock_zt_pool_em(self, date):
            del date
            return []

        def stock_lhb_detail_em(self, start_date, end_date):
            del start_date, end_date
            return [
                {
                    "代码": "000062",
                    "龙虎榜买入额": 673637900,
                    "龙虎榜卖出额": 198561200,
                    "龙虎榜净买额": 475076700,
                    "上榜原因": "日涨幅偏离值达到7%的前5只证券",
                }
            ]

    monkeypatch.setattr(provider_module, "import_module", lambda name: FakeAkshare())

    bundle = VnpyAkshareDailyReviewProvider(FakeMainEngine()).load_data_bundle(
        date(2026, 5, 11)
    )

    assert len(bundle.lhb) == 1
    assert bundle.lhb[0].symbol == "000062.SZSE"
    assert bundle.lhb[0].buy_amount == Decimal("673637900")
    assert bundle.lhb[0].sell_amount == Decimal("198561200")
    assert bundle.lhb[0].net_buy_amount == Decimal("475076700")


def test_daily_market_review_schema_initializer_includes_report_tables():
    """Daily review persistence tables should reuse the existing schema initializer."""
    from vnpy_tradingagents.schema_init import EXTENSION_TABLE_NAMES

    assert "daily_review_report" in EXTENSION_TABLE_NAMES
    assert "daily_review_evidence" in EXTENSION_TABLE_NAMES
    assert "daily_watch_plan" in EXTENSION_TABLE_NAMES
    assert "daily_watch_plan_item" in EXTENSION_TABLE_NAMES


def test_daily_market_review_module_does_not_import_trading_or_order_paths():
    """Daily market review must remain a report/watch-plan module, not an order module."""
    package_files = [
        Path("vnpy_daily_review/app.py"),
        Path("vnpy_daily_review/engine.py"),
        Path("vnpy_daily_review/service.py"),
        Path("vnpy_daily_review/ui/widget.py"),
    ]

    source = "\n".join(path.read_text(encoding="utf-8") for path in package_files)

    assert "send_order" not in source
    assert "OrderRequest" not in source
    assert "TradingAgents" not in source


def test_veighna_trader_example_registers_daily_market_review_app():
    """The local startup example should expose DailyMarketReview in the vn.py UI."""
    tree = ast.parse(Path("examples/veighna_trader/run.py").read_text(encoding="utf-8"))

    imports_app = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "vnpy_daily_review"
        and any(alias.name == "DailyMarketReviewApp" for alias in node.names)
        for node in ast.walk(tree)
    )
    registers_app = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_app"
        and node.args
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == "DailyMarketReviewApp"
        for node in ast.walk(tree)
    )
    configures_service = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "configure_daily_review_services"
        for node in ast.walk(tree)
    )

    assert imports_app
    assert registers_app
    assert configures_service


def test_daily_market_review_docs_are_present_in_vnpy_docs():
    """The migrated docs should live inside the current vn.py docs tree."""
    roadmap = Path("docs/community/info/ai-module-roadmap.md").read_text(encoding="utf-8")
    plan = Path("docs/community/info/daily-market-review-ai-technical-plan.md").read_text(
        encoding="utf-8"
    )
    task = Path(
        "docs/community/tasks/tradingagents_next_steps/29-daily-market-review-vnpy-app.md"
    ).read_text(encoding="utf-8")

    assert "每日市场复盘" in roadmap
    assert "vn.py 版本架构" in plan
    assert "DailyMarketReviewApp" in plan
    assert "DailyReviewService" in plan
    assert "P29" in task
    assert "P29-T06.1" in task
