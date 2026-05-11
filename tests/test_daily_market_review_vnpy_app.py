import ast
from importlib import import_module
from pathlib import Path


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


def test_daily_market_review_module_does_not_import_trading_or_order_paths():
    """Daily market review must remain a report/watch-plan module, not an order module."""
    package_files = [
        Path("vnpy_daily_review/app.py"),
        Path("vnpy_daily_review/engine.py"),
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

    assert imports_app
    assert registers_app


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
    assert "P29" in task
