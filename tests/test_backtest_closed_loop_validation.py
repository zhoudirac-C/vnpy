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


def test_backtest_closed_loop_validation_can_load_datafeed_bars(monkeypatch, tmp_path):
    """P19-T04 should run the same backtest from vn.py Datafeed/provider bars."""
    from datetime import datetime

    from vnpy.trader.constant import Exchange, Interval
    from vnpy.trader.object import BarData
    from tools.production import backtest_closed_loop_validation as validation

    class FakeDatafeed:
        def query_bar_history(self, req, output=print):
            assert req.vt_symbol == "600519.SSE"
            bars = [
                BarData(
                    symbol="600519",
                    exchange=Exchange.SSE,
                    datetime=datetime(2024, 1, 2),
                    interval=Interval.DAILY,
                    open_price=1680,
                    high_price=1690,
                    low_price=1670,
                    close_price=1688,
                    volume=1000,
                    turnover=1688000,
                    gateway_name="akshare",
                ),
                BarData(
                    symbol="600519",
                    exchange=Exchange.SSE,
                    datetime=datetime(2024, 1, 3),
                    interval=Interval.DAILY,
                    open_price=1688,
                    high_price=1700,
                    low_price=1680,
                    close_price=1695,
                    volume=1200,
                    turnover=2034000,
                    gateway_name="akshare",
                ),
            ]
            for bar in bars:
                bar.extra = {"provider_name": "akshare", "provider_endpoint": "stock_zh_a_hist"}
            return bars

    monkeypatch.setattr(validation, "Datafeed", FakeDatafeed)

    result = validation.run_backtest_closed_loop(
        validation.BacktestClosedLoopConfig(
            vt_symbol="600519.SSE",
            data_source="datafeed",
            start=datetime(2024, 1, 2),
            end=datetime(2024, 1, 3),
            output_path=tmp_path / "datafeed.md",
            json_output_path=tmp_path / "datafeed.json",
        )
    )

    assert result.success
    assert result.data_source == "datafeed:akshare"
    assert result.fixture_path == ""
    assert result.provider_names == ["akshare"]
    assert "datafeed:akshare" in validation.render_markdown(result)
