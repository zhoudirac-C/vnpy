from pathlib import Path


def test_tradingagents_signal_strategy_is_not_a_traditional_strategy_mixin():
    """Independent AI strategy should not be hidden inside traditional rule strategies."""
    from vnpy_tradingagents.strategies import TradingAgentsSignalStrategy
    from vnpy_tradingagents.strategy_mixin import TradingAgentsStrategyMixin

    assert not issubclass(TradingAgentsSignalStrategy, TradingAgentsStrategyMixin)


def test_tradingagents_strategy_module_does_not_patch_named_rule_strategies():
    """This fork should not silently change DoubleMa/Turtle/AtrRsi strategy semantics."""
    source = Path("vnpy_tradingagents/strategies.py").read_text(encoding="utf-8")

    assert "DoubleMaStrategy" not in source
    assert "TurtleSignalStrategy" not in source
    assert "AtrRsiStrategy" not in source
