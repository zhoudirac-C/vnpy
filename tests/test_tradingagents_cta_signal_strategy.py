from datetime import datetime

from vnpy.trader.constant import Direction, Exchange, Offset
from vnpy.trader.object import TickData
from vnpy_ctastrategy import CtaTemplate

from vnpy_tradingagents.risk import RiskRuleSet
from vnpy_tradingagents.runtime import TradingAgentsMode, TradingAgentsRuntimeController
from vnpy_tradingagents.signals import PortfolioIntent
from vnpy_tradingagents.strategies import TradingAgentsSignalStrategy


def test_tradingagents_cta_signal_strategy_is_visible_to_cta_loader():
    """The independent AI strategy needs a CTA wrapper so it appears in UI."""
    from strategies.tradingagents_cta_signal_strategy import (
        TradingAgentsCtaSignalStrategy,
    )

    assert issubclass(TradingAgentsCtaSignalStrategy, CtaTemplate)
    assert "signal_volume" in TradingAgentsCtaSignalStrategy.parameters
    assert "max_order_value" in TradingAgentsCtaSignalStrategy.parameters


def test_vnpy_cta_engine_scans_tradingagents_cta_signal_strategy():
    """vn.py CTA engine should discover the wrapper from root strategies/."""
    from pathlib import Path

    from vnpy_ctastrategy.engine import CtaEngine

    logs = []
    cta_engine = object.__new__(CtaEngine)
    cta_engine.classes = {}
    cta_engine.write_log = logs.append

    cta_engine.load_strategy_class_from_folder(Path("strategies"), "strategies")

    assert "TradingAgentsCtaSignalStrategy" in cta_engine.classes
    assert logs == []


def test_tradingagents_cta_signal_strategy_submits_approved_buy_intent():
    """CTA wrapper should consume stored AI intent and submit through vn.py order API."""
    from strategies.tradingagents_cta_signal_strategy import (
        TradingAgentsCtaSignalStrategy,
    )

    runtime = TradingAgentsRuntimeController()
    runtime.enable(mode=TradingAgentsMode.PAPER_ONLY)

    cta_engine = FakeCtaEngine()
    strategy = TradingAgentsCtaSignalStrategy(
        cta_engine=cta_engine,
        strategy_name="ai",
        vt_symbol="600519.SSE",
        setting={
            "signal_volume": 100,
            "live": False,
            "max_order_value": 100_000,
        },
    )
    strategy.signal_strategy = TradingAgentsSignalStrategy(
        runtime=runtime,
        signal_reader=FakeSignalReader(make_intent("buy")),
        rules=RiskRuleSet(max_order_value=100_000),
        audit_storage=FakeAuditStorage(),
    )
    strategy.ready = True
    strategy.inited = True
    strategy.trading = True

    strategy.on_tick(
        TickData(
            gateway_name="AKSHARE",
            symbol="600519",
            exchange=Exchange.SSE,
            datetime=datetime(2026, 5, 8, 10),
            last_price=100,
            ask_price_1=100.1,
            bid_price_1=99.9,
            limit_up=110,
            limit_down=90,
        )
    )

    assert cta_engine.orders == [
        {
            "direction": Direction.LONG,
            "offset": Offset.OPEN,
            "price": 100.1,
            "volume": 100,
            "stop": False,
        }
    ]
    assert strategy.last_action == "buy"
    assert strategy.last_reason == "submitted"


def test_tradingagents_cta_signal_strategy_ignores_missing_ai_signal():
    """No stored AI intent means no order, while the strategy remains visible."""
    from strategies.tradingagents_cta_signal_strategy import (
        TradingAgentsCtaSignalStrategy,
    )

    runtime = TradingAgentsRuntimeController()
    runtime.enable(mode=TradingAgentsMode.PAPER_ONLY)

    cta_engine = FakeCtaEngine()
    strategy = TradingAgentsCtaSignalStrategy(
        cta_engine=cta_engine,
        strategy_name="ai",
        vt_symbol="600519.SSE",
        setting={"signal_volume": 100, "live": False},
    )
    strategy.signal_strategy = TradingAgentsSignalStrategy(
        runtime=runtime,
        signal_reader=FakeSignalReader(None),
        rules=RiskRuleSet(),
        audit_storage=FakeAuditStorage(),
    )
    strategy.ready = True
    strategy.inited = True
    strategy.trading = True

    strategy.on_tick(
        TickData(
            gateway_name="AKSHARE",
            symbol="600519",
            exchange=Exchange.SSE,
            datetime=datetime(2026, 5, 8, 10),
            last_price=100,
        )
    )

    assert cta_engine.orders == []
    assert strategy.last_reason == "no_ai_signal"


def make_intent(action: str) -> PortfolioIntent:
    """Create a stored TradingAgents trade intent."""
    return PortfolioIntent(
        vt_symbol="600519.SSE",
        trade_date="2026-05-08",
        action=action,
        target_weight_hint=0.1,
        holding_period_hint="intraday",
        risk_notes="test",
        source_run_id=f"run-{action}",
    )


class FakeSignalReader:
    """Signal reader fake for stored AI intent."""

    def __init__(self, intent: PortfolioIntent | None) -> None:
        self.intent = intent

    def load_latest_trade_intent(self, vt_symbol: str, trade_date: str):
        return self.intent


class FakeAuditStorage:
    """Audit storage fake."""

    def save_decision(self, record) -> None:
        pass


class FakeCtaEngine:
    """Small CTA engine fake recording orders."""

    def __init__(self) -> None:
        self.orders = []
        self.logs = []

    def send_order(self, strategy, direction, offset, price, volume, stop, lock, net):
        self.orders.append(
            {
                "direction": direction,
                "offset": offset,
                "price": price,
                "volume": volume,
                "stop": stop,
            }
        )
        return ["AKSHARE.1"]

    def write_log(self, msg, strategy) -> None:
        self.logs.append((strategy.strategy_name, msg))

    def put_strategy_event(self, strategy) -> None:
        pass
