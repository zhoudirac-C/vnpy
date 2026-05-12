from __future__ import annotations

from pathlib import Path


def test_tradingagents_ui_declares_seven_boll_scan_tab_and_columns() -> None:
    from vnpy.trader.setting import SETTINGS
    from vnpy_tradingagents.ui.widget import (
        SEVEN_BOLL_ANALYSIS_RUN_COLUMN,
        SEVEN_BOLL_ANALYSIS_STATUS_COLUMN,
        SEVEN_BOLL_COLUMNS,
        SEVEN_BOLL_REPORT_COLUMN,
        SEVEN_BOLL_RUNNING_STATUSES,
        SEVEN_BOLL_TAB_TITLE,
        TRADINGAGENTS_CONFIG_PREFIXES,
        build_seven_boll_scan_summary_text,
    )

    assert SEVEN_BOLL_TAB_TITLE == "七轨扫描"
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


def test_tradingagents_widget_wires_seven_boll_scan_tab() -> None:
    source = Path("vnpy_tradingagents/ui/widget.py").read_text(encoding="utf-8")

    assert "self.seven_boll_tab = self.create_seven_boll_tab()" in source
    assert "self.tabs.addTab(self.seven_boll_tab, SEVEN_BOLL_TAB_TITLE)" in source
    assert "self.seven_boll_scan_button.clicked.connect(self.run_seven_boll_scan)" in source
    assert "self.seven_boll_analysis_button.clicked.connect(self.run_selected_seven_boll_analysis)" in source
    assert "self.seven_boll_batch_analysis_button.clicked.connect(self.run_batch_seven_boll_analysis)" in source
    assert "cellClicked.connect(self.handle_seven_boll_cell_clicked)" in source
    assert "self.tabs.setCurrentWidget(self.report_tab)" in source
    assert "analysis_status=running" in source
    assert "analysis_status=completed" in source
    assert "SEVEN_BOLL_RUNNING_STATUSES" in source
