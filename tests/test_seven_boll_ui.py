from __future__ import annotations

from pathlib import Path


def test_tradingagents_ui_declares_seven_boll_scan_tab_and_columns() -> None:
    from vnpy.trader.setting import SETTINGS
    from vnpy_tradingagents.ui.widget import (
        SEVEN_BOLL_ANALYSIS_RUN_COLUMN,
        SEVEN_BOLL_ANALYSIS_STATUS_COLUMN,
        SEVEN_BOLL_BUY_TABLE_TITLE,
        SEVEN_BOLL_COLUMNS,
        SEVEN_BOLL_CONCEPT_COLUMN,
        SEVEN_BOLL_CONFIG_HELP_TEXT,
        SEVEN_BOLL_NAME_COLUMN,
        SEVEN_BOLL_REPORT_COLUMN,
        SEVEN_BOLL_RUNNING_STATUSES,
        SEVEN_BOLL_SYMBOL_COLUMN,
        SEVEN_BOLL_SELL_TABLE_TITLE,
        SEVEN_BOLL_TAB_TITLE,
        TRADINGAGENTS_CONFIG_PREFIXES,
        build_seven_boll_progress_text,
        build_seven_boll_scan_summary_text,
        format_regime_display,
        format_signal_types_display,
        format_stock_display,
    )

    assert SEVEN_BOLL_TAB_TITLE == "七轨扫描"
    assert SEVEN_BOLL_BUY_TABLE_TITLE == "买点候选"
    assert SEVEN_BOLL_SELL_TABLE_TITLE == "卖点候选"
    assert SEVEN_BOLL_COLUMNS[:3] == ["股票", "名称", "最相关概念"]
    assert SEVEN_BOLL_SYMBOL_COLUMN == 0
    assert SEVEN_BOLL_NAME_COLUMN == 1
    assert SEVEN_BOLL_CONCEPT_COLUMN == 2
    assert "信号类型" in SEVEN_BOLL_COLUMNS
    assert "analysis_status" in SEVEN_BOLL_COLUMNS
    assert SEVEN_BOLL_ANALYSIS_RUN_COLUMN == SEVEN_BOLL_COLUMNS.index("analysis_run_id")
    assert SEVEN_BOLL_ANALYSIS_STATUS_COLUMN == SEVEN_BOLL_COLUMNS.index("analysis_status")
    assert SEVEN_BOLL_REPORT_COLUMN == SEVEN_BOLL_COLUMNS.index("查看报告")
    assert SEVEN_BOLL_RUNNING_STATUSES == {"queued", "running"}
    assert "seven_boll." in TRADINGAGENTS_CONFIG_PREFIXES
    assert SETTINGS["seven_boll.scan.schedule"] == "11:35,15:05"
    assert SETTINGS["seven_boll.scan.lookback_bars"] == 250
    assert SETTINGS["seven_boll.indicator.window"] == 20
    assert SETTINGS["seven_boll.indicator.trend_slope_window"] == 5
    assert "0 表示不限制" in SEVEN_BOLL_CONFIG_HELP_TEXT["seven_boll.scan.max_symbols"]
    assert "留空" in SEVEN_BOLL_CONFIG_HELP_TEXT["seven_boll.scan.symbols"]
    assert "趋势斜率" in SEVEN_BOLL_CONFIG_HELP_TEXT["seven_boll.indicator.trend_slope_window"]
    assert format_stock_display("600519.SSE", "贵州茅台") == "600519.SSE 贵州茅台"
    assert format_stock_display("600519.SSE", "") == "600519.SSE"
    assert format_signal_types_display(("trend_pullback_long", "squeeze_breakout_long")) == "趋势回踩做多,收口突破做多"
    assert format_signal_types_display(("unknown_signal",)) == "unknown_signal"
    assert format_regime_display("trend_up") == "上升趋势"
    assert format_regime_display("extreme_overbought") == "极端超买"
    assert format_regime_display("unknown_regime") == "unknown_regime"

    text = build_seven_boll_scan_summary_text(
        {
            "run_id": "scan-1",
            "status": "completed",
            "total_symbols": 10,
            "scanned_symbols": 9,
            "buy_candidates": [object(), object()],
            "sell_candidates": [object()],
        }
    )
    assert "run=scan-1" in text
    assert "buy=2" in text
    assert "sell=1" in text
    progress_text = build_seven_boll_progress_text(
        {
            "run_id": "scan-2",
            "status": "running",
            "total_symbols": 100,
            "scanned_symbols": 7,
            "skipped_symbols": 1,
            "buy_count": 2,
            "sell_count": 3,
            "current_symbol": "600519.SSE",
        }
    )
    assert "scan_status=running" in progress_text
    assert "scanned=7/100" in progress_text
    assert "current=600519.SSE" in progress_text


def test_tradingagents_widget_wires_seven_boll_scan_tab() -> None:
    source = Path("vnpy_tradingagents/ui/widget.py").read_text(encoding="utf-8")

    assert "self.seven_boll_tab = self.create_seven_boll_tab()" in source
    assert "self.tabs.addTab(self.seven_boll_tab, SEVEN_BOLL_TAB_TITLE)" in source
    assert "self.seven_boll_scan_button.clicked.connect(self.run_seven_boll_scan)" in source
    assert "self.seven_boll_cancel_button.clicked.connect(self.cancel_seven_boll_scan)" in source
    assert "self.seven_boll_analysis_button.clicked.connect(self.run_selected_seven_boll_analysis)" in source
    assert "self.seven_boll_batch_analysis_button.clicked.connect(self.run_batch_seven_boll_analysis)" in source
    assert "self._create_titled_section(SEVEN_BOLL_BUY_TABLE_TITLE" in source
    assert "self._create_titled_section(SEVEN_BOLL_SELL_TABLE_TITLE" in source
    assert "cellClicked.connect(self.handle_seven_boll_cell_clicked)" in source
    assert "SEVEN_BOLL_CONFIG_HELP_TEXT.get(field_name" in source
    assert "field_layout.addWidget(help_label" in source
    assert "self.tabs.setCurrentWidget(self.report_tab)" in source
    assert "analysis_status=running" in source
    assert "analysis_status=completed" in source
    assert "SEVEN_BOLL_RUNNING_STATUSES" in source
    assert "format_signal_types_display(" in source
    assert "format_regime_display(" in source
    assert "class SevenBollScanWorker" in source
    assert "progress_ready = QtCore.Signal(object)" in source
    assert "self.seven_boll_scan_worker" in source
    assert "worker.start()" in source
    assert "def cancel_seven_boll_scan" in source
    assert "SEVEN_BOLL_CONCEPT_COLUMN" in source
