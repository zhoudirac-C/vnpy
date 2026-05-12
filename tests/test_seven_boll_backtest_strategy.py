from __future__ import annotations


def test_seven_boll_backtest_validation_runs_three_daily_scenarios(tmp_path) -> None:
    from vnpy_seven_boll.backtest_validation import (
        render_validation_markdown,
        run_seven_boll_backtest_validation,
        write_validation_report,
    )

    results = run_seven_boll_backtest_validation()

    assert {result.scenario for result in results} == {
        "trend_pullback",
        "squeeze_breakout",
        "mean_reversion",
    }
    for result in results:
        assert result.interval == "d"
        assert result.engine_name == "vnpy_ctastrategy.BacktestingEngine"
        assert result.bar_count >= 40
        assert result.metrics["trade_count"] >= 0
        assert "win_rate" in result.metrics
        assert "profit_loss_ratio" in result.metrics
        assert "max_drawdown" in result.metrics
        assert "false_breakout_rate" in result.metrics

    markdown = render_validation_markdown(results)
    assert "# P31 七轨布林线回测验证结果" in markdown
    assert "仅用于验证逻辑，不代表生产收益" in markdown
    assert "trend_pullback" in markdown
    assert "squeeze_breakout" in markdown
    assert "mean_reversion" in markdown
    assert "interval=d" in markdown

    output_path = tmp_path / "seven-boll-backtest.md"
    write_validation_report(results, output_path)
    assert output_path.read_text(encoding="utf-8") == markdown
