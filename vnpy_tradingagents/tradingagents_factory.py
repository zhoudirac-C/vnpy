import json
from collections.abc import Callable, Mapping, Sequence
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from .native_context_runner import AShareContextOnlyRunner


GraphFactory = Callable[..., Any]

_CURRENT_CONTEXT: ContextVar[Mapping[str, Any] | None] = ContextVar(
    "tradingagents_context",
    default=None,
)


class TradingAgentsContextOnlyGraphRunner:
    """
    Native runner that drives TradingAgents with vn.py-provided context only.

    The upstream TradingAgents package exposes ``TradingAgentsGraph.propagate`` as
    its public API. This runner keeps that graph inside a ``run(native_input)``
    boundary and replaces graph tool execution with context tools, so analysts
    cannot fall back to yfinance, Alpha Vantage, Gateway, or MainEngine.
    """

    def __init__(
        self,
        graph_factory: GraphFactory | None = None,
        config_template: Mapping[str, Any] | None = None,
        selected_analysts: Sequence[str] | None = None,
        debug: bool = False,
    ) -> None:
        self.graph_factory: GraphFactory = graph_factory or _default_graph_factory
        self.config_template: dict[str, Any] = dict(config_template or {})
        self.selected_analysts: tuple[str, ...] | None = (
            tuple(selected_analysts) if selected_analysts is not None else None
        )
        self.debug: bool = debug

    def run(self, native_input: Mapping[str, Any]) -> Mapping[str, Any]:
        """
        Execute TradingAgents using only the supplied context snapshots.
        """
        context: Mapping[str, Any] = dict(native_input.get("context") or {})
        config: dict[str, Any] = self._build_config(native_input)
        selected_analysts: list[str] = self._select_analysts(context)

        try:
            graph = self.graph_factory(
                selected_analysts=selected_analysts,
                debug=self.debug,
                config=config,
            )
        except ModuleNotFoundError:
            return _dependency_failure(native_input)

        token = _CURRENT_CONTEXT.set(context)
        try:
            final_state, decision = graph.propagate(
                str(native_input["symbol"]),
                str(native_input["trade_date"]),
            )
        finally:
            _CURRENT_CONTEXT.reset(token)

        return _normalize_graph_result(final_state, decision)

    def _build_config(self, native_input: Mapping[str, Any]) -> dict[str, Any]:
        """
        Build TradingAgents config while forcing all data vendors to context.
        """
        config: dict[str, Any] = dict(self.config_template)
        checkpoint_dir = Path(str(native_input.get("checkpoint_dir") or ".tradingagents/checkpoints"))
        config.update(
            {
                "llm_provider": str(native_input.get("llm_provider") or "openai"),
                "deep_think_llm": str(native_input.get("model") or "gpt-4o-mini"),
                "quick_think_llm": str(native_input.get("model") or "gpt-4o-mini"),
                "data_cache_dir": str(checkpoint_dir / "cache"),
                "results_dir": str(checkpoint_dir / "results"),
                "memory_log_path": str(checkpoint_dir / "memory" / "trading_memory.md"),
                "checkpoint_enabled": False,
                "output_language": str(native_input.get("output_language") or "Chinese"),
                "data_vendors": {
                    "core_stock_apis": "context",
                    "technical_indicators": "context",
                    "fundamental_data": "context",
                    "news_data": "context",
                },
                "tool_vendors": {},
            }
        )
        config.setdefault("max_debate_rounds", 1)
        config.setdefault("max_risk_discuss_rounds", 1)
        config.setdefault("max_recur_limit", 80)
        return config

    def _select_analysts(self, context: Mapping[str, Any]) -> list[str]:
        """
        Pick analysts based on available context sections.
        """
        if self.selected_analysts is not None:
            return list(self.selected_analysts)

        analysts: list[str] = ["market"]
        if any(key in context for key in ("social", "sentiment")):
            analysts.append("social")
        if any(key in context for key in ("news", "events", "announcements")):
            analysts.append("news")
        if any(
            key in context
            for key in ("fundamental", "fundamentals", "financials", "valuation")
        ):
            analysts.append("fundamentals")
        return analysts


def build() -> AShareContextOnlyRunner:
    """
    Factory used by ``TRADINGAGENTS_WORKER_FACTORY``.
    """
    return AShareContextOnlyRunner(
        native_runner=TradingAgentsContextOnlyGraphRunner(),
        required_context_sections=("market",),
    )


def get_context_stock_data(symbol: str, start_date: str, end_date: str) -> str:
    """
    Return OHLCV data from the active context snapshot.
    """
    context = _active_context()
    if context is None:
        return "No context snapshot is active; external market data fallback is disabled."

    market = context.get("market") or {}
    bars = _lookup(market, "bars", "bar_snapshots", "ohlcv", default=[])
    return _format_tool_payload(
        "market",
        {
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
            "bars": bars,
        },
    )


def get_context_indicators(
    symbol: str,
    indicator: str,
    curr_date: str,
    look_back_days: int = 30,
) -> str:
    """
    Return technical indicators from the active context snapshot.
    """
    context = _active_context()
    if context is None:
        return "No context snapshot is active; external indicator fallback is disabled."

    indicators = _lookup(
        context,
        "indicators",
        "technical",
        "alpha_factors",
        default={},
    )
    return _format_tool_payload(
        "indicators",
        {
            "symbol": symbol,
            "indicator": indicator,
            "curr_date": curr_date,
            "look_back_days": look_back_days,
            "values": indicators,
        },
    )


def get_context_news(ticker: str, start_date: str, end_date: str) -> str:
    """
    Return company news/events from the active context snapshot.
    """
    context = _active_context()
    if context is None:
        return "No context snapshot is active; external news fallback is disabled."

    news = _lookup(context, "news", "events", "announcements", default={})
    return _format_tool_payload(
        "news",
        {
            "ticker": ticker,
            "start_date": start_date,
            "end_date": end_date,
            "items": news,
        },
    )


def get_context_global_news(
    curr_date: str,
    look_back_days: int = 7,
    limit: int = 5,
) -> str:
    """
    Return global/macro event context.
    """
    context = _active_context()
    if context is None:
        return "No context snapshot is active; external global news fallback is disabled."

    macro = _lookup(context, "macro", "benchmark", "global_news", default={})
    return _format_tool_payload(
        "global_news",
        {
            "curr_date": curr_date,
            "look_back_days": look_back_days,
            "limit": limit,
            "items": macro,
        },
    )


def get_context_fundamentals(ticker: str, curr_date: str) -> str:
    """
    Return fundamentals from the active context snapshot.
    """
    context = _active_context()
    if context is None:
        return "No context snapshot is active; external fundamentals fallback is disabled."

    fundamentals = _lookup(
        context,
        "fundamental",
        "fundamentals",
        "financials",
        "valuation",
        default={},
    )
    return _format_tool_payload(
        "fundamentals",
        {
            "ticker": ticker,
            "curr_date": curr_date,
            "data": fundamentals,
        },
    )


def get_context_balance_sheet(
    ticker: str,
    freq: str = "quarterly",
    curr_date: str | None = None,
) -> str:
    """
    Return balance sheet context.
    """
    return _context_financial_statement("balance_sheet", ticker, freq, curr_date)


def get_context_cashflow(
    ticker: str,
    freq: str = "quarterly",
    curr_date: str | None = None,
) -> str:
    """
    Return cash flow context.
    """
    return _context_financial_statement("cashflow", ticker, freq, curr_date)


def get_context_income_statement(
    ticker: str,
    freq: str = "quarterly",
    curr_date: str | None = None,
) -> str:
    """
    Return income statement context.
    """
    return _context_financial_statement("income_statement", ticker, freq, curr_date)


def get_context_insider_transactions(ticker: str) -> str:
    """
    Return local insider/holder change context if present.
    """
    context = _active_context()
    if context is None:
        return "No context snapshot is active; external insider fallback is disabled."

    data = _lookup(context, "insider_transactions", "holder_changes", default={})
    return _format_tool_payload("insider_transactions", {"ticker": ticker, "data": data})


def _context_financial_statement(
    statement_name: str,
    ticker: str,
    freq: str,
    curr_date: str | None,
) -> str:
    context = _active_context()
    if context is None:
        return "No context snapshot is active; external financial fallback is disabled."

    financials = _lookup(context, "financials", "fundamental", "fundamentals", default={})
    statement = _lookup(financials, statement_name, default={})
    return _format_tool_payload(
        statement_name,
        {
            "ticker": ticker,
            "freq": freq,
            "curr_date": curr_date,
            "data": statement,
        },
    )


def _default_graph_factory(*, selected_analysts: Sequence[str], debug: bool, config: Mapping[str, Any]) -> Any:
    """
    Build an upstream TradingAgentsGraph with context-only tool nodes.
    """
    try:
        from langgraph.prebuilt import ToolNode
        from tradingagents.graph.trading_graph import TradingAgentsGraph
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError("tradingagents") from exc

    tools = _context_tools()

    class ContextOnlyTradingAgentsGraph(TradingAgentsGraph):
        def _create_tool_nodes(self) -> dict[str, Any]:
            return {
                "market": ToolNode(
                    [
                        tools["get_stock_data"],
                        tools["get_indicators"],
                    ]
                ),
                "social": ToolNode([tools["get_news"]]),
                "news": ToolNode(
                    [
                        tools["get_news"],
                        tools["get_global_news"],
                        tools["get_insider_transactions"],
                    ]
                ),
                "fundamentals": ToolNode(
                    [
                        tools["get_fundamentals"],
                        tools["get_balance_sheet"],
                        tools["get_cashflow"],
                        tools["get_income_statement"],
                    ]
                ),
            }

        def _resolve_pending_entries(self, ticker: str) -> None:
            return None

    return ContextOnlyTradingAgentsGraph(
        selected_analysts=list(selected_analysts),
        debug=debug,
        config=dict(config),
    )


def _context_tools() -> dict[str, Any]:
    """
    Wrap context helpers as LangChain tools when available.
    """
    try:
        from langchain_core.tools import tool
    except ModuleNotFoundError:
        return {
            "get_stock_data": get_context_stock_data,
            "get_indicators": get_context_indicators,
            "get_news": get_context_news,
            "get_global_news": get_context_global_news,
            "get_insider_transactions": get_context_insider_transactions,
            "get_fundamentals": get_context_fundamentals,
            "get_balance_sheet": get_context_balance_sheet,
            "get_cashflow": get_context_cashflow,
            "get_income_statement": get_context_income_statement,
        }

    return {
        "get_stock_data": tool("get_stock_data")(get_context_stock_data),
        "get_indicators": tool("get_indicators")(get_context_indicators),
        "get_news": tool("get_news")(get_context_news),
        "get_global_news": tool("get_global_news")(get_context_global_news),
        "get_insider_transactions": tool("get_insider_transactions")(
            get_context_insider_transactions
        ),
        "get_fundamentals": tool("get_fundamentals")(get_context_fundamentals),
        "get_balance_sheet": tool("get_balance_sheet")(get_context_balance_sheet),
        "get_cashflow": tool("get_cashflow")(get_context_cashflow),
        "get_income_statement": tool("get_income_statement")(
            get_context_income_statement
        ),
    }


def _active_context() -> Mapping[str, Any] | None:
    return _CURRENT_CONTEXT.get()


def _lookup(mapping: Any, *keys: str, default: Any) -> Any:
    if not isinstance(mapping, Mapping):
        return default
    for key in keys:
        value = mapping.get(key)
        if value not in (None, {}, []):
            return value
    return default


def _format_tool_payload(name: str, payload: Mapping[str, Any]) -> str:
    return f"{name} context snapshot:\n" + json.dumps(
        payload,
        ensure_ascii=False,
        default=str,
        indent=2,
    )


def _normalize_graph_result(final_state: Any, decision: Any) -> Mapping[str, Any]:
    decision_mapping = dict(decision) if isinstance(decision, Mapping) else {}
    final_mapping = dict(final_state) if isinstance(final_state, Mapping) else {}

    action = str(
        decision_mapping.get("action")
        or decision_mapping.get("decision")
        or decision_mapping.get("final_trade_decision")
        or final_mapping.get("final_trade_decision")
        or decision
        or "hold"
    )
    report = str(
        decision_mapping.get("report")
        or final_mapping.get("final_trade_decision")
        or final_mapping.get("investment_plan")
        or decision
        or ""
    )
    normalized_action = _action_from_text(action)
    return {
        "rating": str(decision_mapping.get("rating") or _rating_from_action(normalized_action)),
        "confidence": float(decision_mapping.get("confidence") or 0),
        "report": report,
        "action": normalized_action,
        "risk_notes": str(decision_mapping.get("risk_notes") or ""),
        "raw_state": {
            "status": "ok",
            "native_output_type": type(final_state).__name__,
            "final_trade_decision": final_mapping.get("final_trade_decision"),
        },
    }


def _dependency_failure(native_input: Mapping[str, Any]) -> Mapping[str, Any]:
    message = "TradingAgents dependency is not available in the worker environment"
    return {
        "rating": "Unavailable",
        "confidence": 0,
        "report": f"TradingAgents runner failed: {message}",
        "action": "hold",
        "risk_notes": message,
        "raw_state": {
            "status": "failed",
            "error_type": "dependency_error",
            "error_message": message,
            "run_id": native_input.get("run_id"),
            "vt_symbol": native_input.get("symbol"),
            "trade_date": native_input.get("trade_date"),
        },
    }


def _action_from_text(text: str) -> str:
    upper = text.upper()
    if "SELL" in upper:
        return "sell"
    if "REDUCE" in upper or "UNDERWEIGHT" in upper:
        return "reduce"
    if "BUY" in upper or "OVERWEIGHT" in upper:
        return "buy"
    if "WATCH" in upper:
        return "watch"
    return "hold"


def _rating_from_action(action: str) -> str:
    if action == "buy":
        return "Buy"
    if action == "sell":
        return "Sell"
    if action == "reduce":
        return "Underweight"
    if action in {"hold", "watch"}:
        return "Hold"
    return "Unavailable"
