from datetime import datetime
from typing import Any

from vnpy.trader.setting import SETTINGS
from vnpy_ctastrategy import BarData, CtaTemplate, TickData

from vnpy_router.peewee import connect_vnpy_postgres_adapter
from vnpy_tradingagents.risk import PostgresDecisionAuditStorage, RiskRuleSet
from vnpy_tradingagents.runtime import TradingAgentsMode, TradingAgentsRuntimeController
from vnpy_tradingagents.storage import PostgresSignalReader
from vnpy_tradingagents.strategies import (
    AiStrategyDecisionContext,
    TradingAgentsSignalStrategy,
)


BUY_ACTIONS: frozenset[str] = frozenset(
    {"buy", "add", "increase", "open_long"}
)
SELL_ACTIONS: frozenset[str] = frozenset(
    {"sell", "reduce", "exit", "close_long"}
)


class TradingAgentsCtaSignalStrategy(CtaTemplate):
    """
    CTA-visible wrapper for the independent TradingAgents AI signal strategy.

    This class exists only to make the AI strategy selectable in vn.py's CTA UI.
    It consumes already persisted TradingAgents trade intents and never calls the
    LLM from the tick/bar callback.
    """

    author = "vn.py TradingAgents"

    signal_volume: float = 100
    max_order_value: float = 100_000
    max_position_volume: float = 1_000
    live: bool = False
    one_order_per_run: bool = True
    close_only_current_position: bool = True

    last_action: str = ""
    last_reason: str = ""
    last_run_id: str = ""
    last_orderids: str = ""
    decision_count: int = 0
    ready: bool = False

    parameters = [
        "signal_volume",
        "max_order_value",
        "max_position_volume",
        "live",
        "one_order_per_run",
        "close_only_current_position",
    ]
    variables = [
        "ready",
        "last_action",
        "last_reason",
        "last_run_id",
        "last_orderids",
        "decision_count",
    ]

    def __init__(
        self,
        cta_engine: Any,
        strategy_name: str,
        vt_symbol: str,
        setting: dict,
    ) -> None:
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)
        self.signal_strategy: TradingAgentsSignalStrategy | None = None

    def on_init(self) -> None:
        """
        Initialize the DB-backed signal reader and risk/audit boundary.
        """
        self.ready = self._ensure_signal_strategy()
        if self.ready:
            self.write_log("TradingAgents CTA AI 策略初始化完成")
        self.put_event()

    def on_start(self) -> None:
        """
        Start consuming already persisted AI trade intents.
        """
        self.ready = self._ensure_signal_strategy()
        if self.ready:
            self.write_log("TradingAgents CTA AI 策略启动")
        self.put_event()

    def on_stop(self) -> None:
        """
        Stop strategy-side AI signal consumption.
        """
        self.write_log("TradingAgents CTA AI 策略停止")
        self.put_event()

    def on_tick(self, tick: TickData) -> None:
        """
        Evaluate stored AI intent on incoming tick data.
        """
        price = tick.last_price or tick.ask_price_1 or tick.bid_price_1
        if price <= 0:
            self._ignore("invalid_tick_price")
            return

        self._evaluate_and_submit(
            trade_time=tick.datetime,
            price=price,
            buy_price=tick.ask_price_1 or price,
            sell_price=tick.bid_price_1 or price,
            limit_up=tick.limit_up or None,
            limit_down=tick.limit_down or None,
        )

    def on_bar(self, bar: BarData) -> None:
        """
        Evaluate stored AI intent on bar close for backtest/simulation style runs.
        """
        price = bar.close_price
        if price <= 0:
            self._ignore("invalid_bar_price")
            return

        self._evaluate_and_submit(
            trade_time=bar.datetime,
            price=price,
            buy_price=price,
            sell_price=price,
            limit_up=None,
            limit_down=None,
        )

    def _ensure_signal_strategy(self) -> bool:
        """
        Lazily build the independent AI strategy from vn.py PostgreSQL settings.
        """
        if self.signal_strategy is not None:
            return True

        try:
            connection = connect_vnpy_postgres_adapter(SETTINGS)
            audit_storage = PostgresDecisionAuditStorage(connection)
            audit_storage.create_schema()
            self.signal_strategy = TradingAgentsSignalStrategy(
                runtime=self._runtime(),
                signal_reader=PostgresSignalReader(connection),
                rules=RiskRuleSet(
                    max_order_value=self.max_order_value,
                    max_position_volume=self.max_position_volume,
                ),
                audit_storage=audit_storage,
            )
        except Exception as exc:
            self.last_reason = f"init_failed:{exc}"
            self.write_log(f"TradingAgents CTA AI 策略初始化失败：{exc}")
            return False

        return True

    def _runtime(self) -> TradingAgentsRuntimeController:
        """
        Prefer the TradingAgents app runtime; fall back to global settings.
        """
        main_engine = getattr(self.cta_engine, "main_engine", None)
        get_engine = getattr(main_engine, "get_engine", None)
        if get_engine is not None:
            tradingagents_engine = get_engine("TradingAgents")
            runtime = getattr(tradingagents_engine, "runtime", None)
            if runtime is not None:
                return runtime

        runtime = TradingAgentsRuntimeController()
        if SETTINGS.get("tradingagents.signal_strategy_enabled", False):
            live_enabled = bool(SETTINGS.get("tradingagents.live_enabled", False))
            mode = TradingAgentsMode.LIVE_ALLOWED if live_enabled else TradingAgentsMode.PAPER_ONLY
            runtime.enable(mode=mode, live_enabled=live_enabled)
        else:
            runtime.disable("tradingagents.signal_strategy_enabled=false")
        return runtime

    def _evaluate_and_submit(
        self,
        trade_time: datetime,
        price: float,
        buy_price: float,
        sell_price: float,
        limit_up: float | None,
        limit_down: float | None,
    ) -> None:
        """
        Read one AI intent, run risk, and submit through CtaTemplate helpers.
        """
        if not self.ready and not self._ensure_signal_strategy():
            self.put_event()
            return

        if self.signal_strategy is None:
            self._ignore("signal_strategy_missing")
            return

        result = self.signal_strategy.evaluate(
            AiStrategyDecisionContext(
                vt_symbol=self.vt_symbol,
                trade_time=trade_time,
                price=price,
                volume=self.signal_volume,
                live=self.live,
                current_position=self.pos,
                limit_up=limit_up,
                limit_down=limit_down,
            )
        )

        if result.ignored_reason:
            self._ignore(result.ignored_reason)
            return

        if result.trade_intent is not None:
            self.last_run_id = result.trade_intent.source_run_id

        if (
            self.one_order_per_run
            and self.last_run_id
            and self.last_run_id == self.last_orderids.split(":", 1)[0]
        ):
            self._ignore("duplicate_ai_run")
            return

        if result.decision is None or not result.decision.submit_allowed:
            failed_rule = ""
            if result.decision is not None:
                failed_rule = result.decision.risk_result.failed_rule
            self._ignore(f"risk_rejected:{failed_rule}")
            return

        action = result.order_intent.action if result.order_intent else ""
        orderids = self._submit_order(action, buy_price, sell_price)
        self.last_action = action
        self.last_reason = "submitted" if orderids else "submit_skipped"
        if orderids:
            self.last_orderids = f"{self.last_run_id}:{','.join(orderids)}"
        self.decision_count += 1
        self.put_event()

    def _submit_order(self, action: str, buy_price: float, sell_price: float) -> list:
        """
        Map AI action into vn.py CTA order helpers.
        """
        action = action.strip().lower()
        volume = float(self.signal_volume)

        if action in BUY_ACTIONS:
            return self.buy(buy_price, volume)

        if action in SELL_ACTIONS:
            if self.close_only_current_position:
                volume = min(max(float(self.pos), 0), volume)
            if volume <= 0:
                self.last_reason = "no_position_to_sell"
                return []
            return self.sell(sell_price, volume)

        if action == "cover":
            if self.close_only_current_position:
                volume = min(abs(min(float(self.pos), 0)), volume)
            if volume <= 0:
                self.last_reason = "no_short_position_to_cover"
                return []
            return self.cover(buy_price, volume)

        self.last_reason = "unsupported_action"
        return []

    def _ignore(self, reason: str) -> None:
        """
        Record why this tick/bar did not submit an order.
        """
        self.last_reason = reason
        self.put_event()
