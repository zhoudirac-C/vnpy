def test_source_policy_allows_degraded_news_and_sentiment():
    """SnapshotSourcePolicy should allow optional news/sentiment degradation."""
    from vnpy_tradingagents.source_policy import SnapshotSourcePolicy

    result = SnapshotSourcePolicy.default().evaluate(
        {
            "market": {"bars": [{"close_price": 10}]},
            "fundamentals": {"roe": 0.1},
            "news": {},
            "sentiment": {},
            "degraded_sources": ["news", "sentiment"],
        }
    )

    assert result.allowed
    assert result.degraded_sources == ["news", "sentiment"]
    assert result.blocked_reason == ""


def test_source_policy_blocks_missing_market():
    """SnapshotSourcePolicy should block worker runs without market data."""
    from vnpy_tradingagents.source_policy import SnapshotSourcePolicy

    result = SnapshotSourcePolicy.default().evaluate(
        {
            "market": {"bars": []},
            "fundamentals": {"roe": 0.1},
            "degraded_sources": ["market"],
        }
    )

    assert not result.allowed
    assert result.blocked_reason == "missing_required_source:market"
    assert "market" in result.missing_required_sources


def test_source_policy_blocks_required_fundamentals_by_configuration():
    """SnapshotSourcePolicy should support making fundamentals required."""
    from vnpy_tradingagents.source_policy import SnapshotSourcePolicy

    policy = SnapshotSourcePolicy.required("market", "fundamentals")

    result = policy.evaluate(
        {
            "market": {"bars": [{"close_price": 10}]},
            "fundamentals": {},
        }
    )

    assert not result.allowed
    assert result.blocked_reason == "missing_required_source:fundamentals"
