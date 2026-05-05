from vnpy_tradingagents.config import TradingAgentsWorkerConfig


def test_context_only_graph_runner_feeds_tools_from_payload_context(tmp_path):
    """Built-in TradingAgents runner should read market/news data only from context."""
    from vnpy_tradingagents.tradingagents_factory import (
        TradingAgentsContextOnlyGraphRunner,
    )

    seen = {}

    def graph_factory(*, selected_analysts, debug, config):
        seen["selected_analysts"] = selected_analysts
        seen["debug"] = debug
        seen["config"] = config
        return FakeTradingAgentsGraph()

    runner = TradingAgentsContextOnlyGraphRunner(graph_factory=graph_factory)

    result = runner.run(
        {
            "run_id": "run-1",
            "symbol": "600519.SSE",
            "trade_date": "2024-01-03",
            "mode": "long_horizon",
            "context": {
                "market": {
                    "bars": [
                        {"datetime": "2024-01-03", "open": 10, "close": 11, "volume": 100}
                    ]
                },
                "news": {"items": [{"title": "local snapshot news", "source": "fixture"}]},
            },
            "llm_provider": "openai",
            "model": "gpt-test",
            "checkpoint_dir": str(tmp_path / "checkpoint"),
            "config": TradingAgentsWorkerConfig(api_key_env_var="TEST_KEY"),
        }
    )

    assert seen["selected_analysts"] == ["market", "news"]
    assert seen["debug"] is False
    assert seen["config"]["data_vendors"] == {
        "core_stock_apis": "context",
        "technical_indicators": "context",
        "fundamental_data": "context",
        "news_data": "context",
    }
    assert result["action"] == "buy"
    assert result["rating"] == "Buy"
    assert "local snapshot news" in result["report"]


def test_context_tools_fail_closed_without_payload_context():
    """Context tools should not fall back to yfinance/Alpha Vantage when context is absent."""
    from vnpy_tradingagents.tradingagents_factory import get_context_stock_data

    text = get_context_stock_data("600519.SSE", "2024-01-01", "2024-01-03")

    assert "No context snapshot is active" in text


def test_context_only_graph_runner_returns_dependency_error_when_upstream_missing():
    """Missing upstream TradingAgents should be diagnosable, not a generic worker crash."""
    from vnpy_tradingagents.tradingagents_factory import TradingAgentsContextOnlyGraphRunner

    def missing_graph_factory(*, selected_analysts, debug, config):
        raise ModuleNotFoundError("tradingagents")

    runner = TradingAgentsContextOnlyGraphRunner(graph_factory=missing_graph_factory)

    result = runner.run(
        {
            "run_id": "run-1",
            "symbol": "600519.SSE",
            "trade_date": "2024-01-03",
            "mode": "long_horizon",
            "context": {"market": {"bars": [{"close": 10}]}},
        }
    )

    assert result["action"] == "hold"
    assert result["raw_state"]["status"] == "failed"
    assert result["raw_state"]["error_type"] == "dependency_error"


class FakeTradingAgentsGraph:
    """Tiny fake of the upstream TradingAgentsGraph."""

    def propagate(self, symbol, trade_date):
        from vnpy_tradingagents.tradingagents_factory import (
            get_context_news,
            get_context_stock_data,
        )

        market_text = get_context_stock_data(symbol, "2024-01-01", trade_date)
        news_text = get_context_news(symbol, "2024-01-01", trade_date)
        return (
            {
                "company_of_interest": symbol,
                "trade_date": trade_date,
                "market_report": market_text,
                "news_report": news_text,
                "final_trade_decision": "BUY",
            },
            {
                "action": "buy",
                "rating": "Buy",
                "confidence": 0.72,
                "report": f"{market_text}\n{news_text}",
                "risk_notes": "context-only",
            },
        )
