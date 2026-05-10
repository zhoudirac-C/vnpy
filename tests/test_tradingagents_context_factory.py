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
            "backend_url": "https://example.test/v1",
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
    assert seen["config"]["backend_url"] == "https://example.test/v1"
    assert seen["config"]["max_completion_tokens"] == 1536
    assert result["action"] == "buy"
    assert result["rating"] == "Buy"
    assert "local snapshot news" in result["report"]


def test_context_only_graph_runner_ignores_empty_optional_sections(tmp_path):
    """Empty optional snapshots should not activate heavier TradingAgents analysts."""
    from vnpy_tradingagents.tradingagents_factory import (
        TradingAgentsContextOnlyGraphRunner,
    )

    seen = {}

    def graph_factory(*, selected_analysts, debug, config):
        seen["selected_analysts"] = selected_analysts
        return FakeTradingAgentsGraph()

    runner = TradingAgentsContextOnlyGraphRunner(graph_factory=graph_factory)

    runner.run(
        {
            "run_id": "run-1",
            "symbol": "600519.SSE",
            "trade_date": "2024-01-03",
            "mode": "intraday",
            "context": {
                "market": {"bars": [{"datetime": "2024-01-03", "close": 11}]},
                "news": [],
                "sentiment": {},
                "fundamentals": None,
            },
            "checkpoint_dir": str(tmp_path / "checkpoint"),
        }
    )

    assert seen["selected_analysts"] == ["market"]


def test_context_only_graph_runner_disables_glm_forced_thinking_in_auto_mode():
    """GLM thinking models should disable thinking by default for structured output."""
    from vnpy_tradingagents.tradingagents_factory import _provider_extra_body

    extra_body = _provider_extra_body(
        {
            "llm_provider": "glm",
            "deep_think_llm": "glm-4.7",
            "quick_think_llm": "glm-4.7",
            "thinking_type": "auto",
        }
    )

    assert extra_body == {"thinking": {"type": "disabled"}}


def test_context_only_graph_runner_allows_explicit_glm_thinking_enabled():
    """Explicit UI settings should override the GLM auto default."""
    from vnpy_tradingagents.tradingagents_factory import _provider_extra_body

    extra_body = _provider_extra_body(
        {
            "llm_provider": "glm",
            "deep_think_llm": "glm-4.7",
            "quick_think_llm": "glm-4.7",
            "thinking_type": "enabled",
        }
    )

    assert extra_body == {"thinking": {"type": "enabled"}}


def test_context_only_graph_runner_passes_llm_runtime_limits():
    """Context runner should cap each upstream LLM call for predictable latency."""
    from vnpy_tradingagents.tradingagents_factory import (
        TradingAgentsContextOnlyGraphRunner,
    )

    seen = {}

    def graph_factory(*, selected_analysts, debug, config):
        seen["config"] = config
        return FakeTradingAgentsGraph()

    runner = TradingAgentsContextOnlyGraphRunner(graph_factory=graph_factory)

    runner.run(
        {
            "run_id": "run-1",
            "symbol": "600519.SSE",
            "trade_date": "2024-01-03",
            "context": {"market": {"bars": [{"close": 10}]}},
            "timeout_seconds": 42,
            "max_retries": 0,
            "max_completion_tokens": 512,
        }
    )

    assert seen["config"]["timeout"] == 42
    assert seen["config"]["max_retries"] == 0
    assert seen["config"]["max_completion_tokens"] == 512


def test_context_only_graph_runner_defaults_timeout_to_ui_default():
    """Context runner should not fall back to the upstream 120 second default."""
    from vnpy_tradingagents.tradingagents_factory import (
        TradingAgentsContextOnlyGraphRunner,
    )

    seen = {}

    def graph_factory(*, selected_analysts, debug, config):
        seen["config"] = config
        return FakeTradingAgentsGraph()

    runner = TradingAgentsContextOnlyGraphRunner(graph_factory=graph_factory)

    runner.run(
        {
            "run_id": "run-1",
            "symbol": "600519.SSE",
            "trade_date": "2024-01-03",
            "context": {"market": {"bars": [{"close": 10}]}},
        }
    )

    assert seen["config"]["timeout"] == 1800.0


def test_context_only_graph_runner_extracts_free_text_fallback_fields(tmp_path):
    """Free-text TradingAgents fallback should still produce useful auditable fields."""
    from vnpy_tradingagents.tradingagents_factory import (
        TradingAgentsContextOnlyGraphRunner,
    )

    runner = TradingAgentsContextOnlyGraphRunner(
        graph_factory=lambda **_: FreeTextFallbackTradingAgentsGraph()
    )

    result = runner.run(
        {
            "run_id": "run-1",
            "symbol": "002636.SZSE",
            "trade_date": "2026-05-09",
            "mode": "manual_analysis",
            "context": {"market": {"bars": [{"close": 47.5}]}},
            "checkpoint_dir": str(tmp_path / "checkpoint"),
        }
    )

    assert result["rating"] == "Hold"
    assert result["action"] == "hold"
    assert result["confidence"] == 0.61
    assert "技术止损" in result["risk_notes"]
    assert result["raw_state"]["text_output_parsed"] is True


def test_context_only_graph_runner_registers_domestic_openai_providers():
    """Domestic provider names should be runnable through upstream TradingAgents."""
    from vnpy_tradingagents.tradingagents_factory import (
        OPENAI_COMPATIBLE_PROVIDER_CONFIG,
        _register_openai_compatible_providers,
    )

    _register_openai_compatible_providers()

    from tradingagents.llm_clients import factory, openai_client

    assert "kimi" in factory._OPENAI_COMPATIBLE
    assert openai_client._PROVIDER_CONFIG["kimi"] == (
        "https://api.moonshot.cn/v1",
        "MOONSHOT_API_KEY",
    )
    assert openai_client._PROVIDER_CONFIG["qianfan"] == (
        "https://qianfan.baidubce.com/v2",
        "QIANFAN_API_KEY",
    )
    assert "siliconflow" in OPENAI_COMPATIBLE_PROVIDER_CONFIG
    assert openai_client._PROVIDER_CONFIG["modelscope"] == (
        "https://api-inference.modelscope.cn/v1",
        "MODELSCOPE_API_KEY",
    )
    assert "openai_compatible" in factory._OPENAI_COMPATIBLE


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


class FreeTextFallbackTradingAgentsGraph:
    """Fake upstream graph that returns markdown after structured output fallback."""

    def propagate(self, symbol, trade_date):
        return (
            {"company_of_interest": symbol, "trade_date": trade_date},
            """
**Rating**: Hold
**Confidence**: 61%

**Executive Summary**: 维持当前002636.SZSE持仓，不增加新头寸。技术止损设于40.67元。

**Investment Thesis**: 基本面改善但短期追涨风险仍然偏高。
""",
        )
