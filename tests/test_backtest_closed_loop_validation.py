import json
from pathlib import Path


def test_backtest_closed_loop_validation_runs_vnpy_engine_and_audit(tmp_path):
    """P19 validation should run vn.py BacktestingEngine with AI audit and no live gateway."""
    from tools.production.backtest_closed_loop_validation import (
        BacktestClosedLoopConfig,
        render_markdown,
        run_backtest_closed_loop,
        write_result_files,
    )

    config = BacktestClosedLoopConfig(
        vt_symbol="600519.SSE",
        fixture_path=Path("tests/fixtures/e2e/600519.SSE_d.csv"),
        output_path=tmp_path / "backtest.md",
        json_output_path=tmp_path / "backtest.json",
    )

    result = run_backtest_closed_loop(config)

    assert result.success
    assert result.engine_name == "vnpy_ctastrategy.BacktestingEngine"
    assert result.live_gateway_touched is False
    assert result.fixture_path.endswith("600519.SSE_d.csv")
    assert result.bar_count == 3
    assert result.trade_count >= 1
    assert result.audit_count >= 1
    assert result.statistics["total_trade_count"] >= 1
    assert result.audit_records[0]["ai_used"] is True
    assert result.audit_records[0]["risk_decision"] == "approved"

    markdown = render_markdown(result)
    assert "# P19 回测闭环验证结果" in markdown
    assert "vnpy_ctastrategy.BacktestingEngine" in markdown
    assert "fixture" in markdown
    assert "未触碰真实 Gateway/MainEngine" in markdown

    write_result_files(result, config)
    assert config.output_path.read_text(encoding="utf-8") == markdown
    payload = json.loads(config.json_output_path.read_text(encoding="utf-8"))
    assert payload["live_gateway_touched"] is False
    assert payload["statistics"]["total_trade_count"] == 1
    assert isinstance(payload["statistics"]["total_trade_count"], int)
