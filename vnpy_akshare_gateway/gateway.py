from datetime import datetime
from importlib import import_module
from typing import Any

import pandas as pd

from vnpy.event import EVENT_TIMER, Event, EventEngine
from vnpy.trader.constant import Exchange, Product
from vnpy.trader.gateway import BaseGateway
from vnpy.trader.object import (
    AccountData,
    BarData,
    CancelRequest,
    ContractData,
    HistoryRequest,
    OrderRequest,
    SubscribeRequest,
    TickData,
)


SETTING_POLL_INTERVAL: str = "轮询间隔秒数"
SETTING_SYMBOLS: str = "订阅代码"
SETTING_LOAD_CONTRACTS: str = "连接后加载全市场合约"
SETTING_SUBSCRIBE_ALL: str = "订阅全市场行情"
SETTING_SNAPSHOT_ENDPOINTS: str = "快照接口顺序"
SETTING_INDIVIDUAL_QUOTE_ENDPOINT: str = "单票行情接口"
DEFAULT_SNAPSHOT_ENDPOINTS: tuple[str, ...] = ("stock_zh_a_spot_em", "stock_zh_a_spot")
DEFAULT_INDIVIDUAL_QUOTE_ENDPOINT: str = "stock_bid_ask_em"
MAX_INDIVIDUAL_QUOTE_SYMBOLS: int = 50


class AkshareGateway(BaseGateway):
    """
    Read-only A-share quote gateway backed by AKShare spot snapshots.
    """

    default_name: str = "AKSHARE"
    default_setting: dict[str, str | int | float | bool | list] = {
        SETTING_POLL_INTERVAL: 15,
        SETTING_SYMBOLS: "",
        SETTING_LOAD_CONTRACTS: ["是", "否"],
        SETTING_SUBSCRIBE_ALL: ["否", "是"],
        SETTING_SNAPSHOT_ENDPOINTS: ",".join(DEFAULT_SNAPSHOT_ENDPOINTS),
        SETTING_INDIVIDUAL_QUOTE_ENDPOINT: DEFAULT_INDIVIDUAL_QUOTE_ENDPOINT,
    }
    exchanges: list[Exchange] = [Exchange.SSE, Exchange.SZSE, Exchange.BSE]

    def __init__(self, event_engine: EventEngine, gateway_name: str) -> None:
        """"""
        super().__init__(event_engine, gateway_name)
        self.akshare: Any | None = None
        self.active: bool = False
        self.subscribed: set[str] = set()
        self.contracts: dict[str, ContractData] = {}
        self.latest_snapshot: pd.DataFrame = pd.DataFrame()
        self.poll_interval_seconds: int = 15
        self.snapshot_endpoints: list[str] = list(DEFAULT_SNAPSHOT_ENDPOINTS)
        self.individual_quote_endpoint: str = DEFAULT_INDIVIDUAL_QUOTE_ENDPOINT
        self.subscribe_all: bool = False
        self._elapsed_seconds: int = 0
        self._timer_registered: bool = False

    def connect(self, setting: dict) -> None:
        """
        Load AKShare, optionally push contracts, then start timer polling.
        """
        self.poll_interval_seconds = max(1, int(setting.get(SETTING_POLL_INTERVAL) or 15))
        self.snapshot_endpoints = _parse_snapshot_endpoints(
            setting.get(SETTING_SNAPSHOT_ENDPOINTS), DEFAULT_SNAPSHOT_ENDPOINTS
        )
        self.individual_quote_endpoint = str(
            setting.get(SETTING_INDIVIDUAL_QUOTE_ENDPOINT) or DEFAULT_INDIVIDUAL_QUOTE_ENDPOINT
        ).strip()
        self.subscribe_all = _is_enabled(setting.get(SETTING_SUBSCRIBE_ALL, "否"))
        self.subscribed.update(_split_symbols(str(setting.get(SETTING_SYMBOLS) or "")))

        if not self._init_akshare():
            return

        snapshot = self._query_snapshot()
        self.latest_snapshot = snapshot
        if _is_enabled(setting.get(SETTING_LOAD_CONTRACTS, "是")):
            self._push_contracts(snapshot)
        elif self.subscribed:
            self._push_missing_contracts(snapshot)

        if self.subscribe_all:
            if not self.contracts:
                self._push_contracts(snapshot)
            self.subscribed.update(self.contracts)

        self._push_subscribed_ticks(snapshot)
        self.active = True
        self._register_timer()
        self.write_log(
            f"AKShare只读行情已连接：合约 {len(self.contracts)} 个，订阅 {len(self.subscribed)} 个"
        )

    def close(self) -> None:
        """
        Stop timer polling.
        """
        self.active = False
        if self._timer_registered:
            self.event_engine.unregister(EVENT_TIMER, self.process_timer_event)
            self._timer_registered = False

    def subscribe(self, req: SubscribeRequest) -> None:
        """
        Subscribe one symbol for snapshot polling.
        """
        symbol, exchange = _symbol_exchange_from_subscribe_request(req)
        vt_symbol = f"{symbol}.{exchange.value}"
        self.subscribed.add(vt_symbol)
        if vt_symbol not in self.contracts:
            contract = ContractData(
                symbol=symbol,
                exchange=exchange,
                name="",
                product=Product.EQUITY,
                size=1,
                pricetick=0.01,
                min_volume=100,
                gateway_name=self.gateway_name,
            )
            self.contracts[vt_symbol] = contract
            self.on_contract(contract)
        self._push_missing_contracts(self.latest_snapshot)
        self._push_subscribed_ticks(self.latest_snapshot, subscribed={vt_symbol})
        self.write_log(f"AKShare订阅行情：{vt_symbol}")

    def send_order(self, req: OrderRequest) -> str:
        """
        Reject trading because this gateway is market-data only.
        """
        self.write_log("AKShare Gateway 是只读行情接口，不支持委托下单")
        return ""

    def cancel_order(self, req: CancelRequest) -> None:
        """
        Reject cancel because this gateway is market-data only.
        """
        self.write_log("AKShare Gateway 是只读行情接口，不支持撤单")

    def query_account(self) -> None:
        """
        Publish an empty account snapshot for UI friendliness.
        """
        account = AccountData(accountid="AKSHARE_READONLY", gateway_name=self.gateway_name)
        self.on_account(account)

    def query_position(self) -> None:
        """
        No positions exist for read-only market data.
        """
        self.write_log("AKShare Gateway 是只读行情接口，不提供持仓查询")

    def query_history(self, req: HistoryRequest) -> list[BarData]:
        """
        Keep history on vn.py Datafeed/router path.
        """
        self.write_log("AKShare历史K线请通过 datafeed.name=router + router.providers=akshare 使用")
        return []

    def process_timer_event(self, event: Event) -> None:
        """
        Poll subscribed symbols on vn.py timer events.
        """
        if not self.active or event.type != EVENT_TIMER:
            return

        self._elapsed_seconds += 1
        if self._elapsed_seconds < self.poll_interval_seconds:
            return

        self._elapsed_seconds = 0
        self.poll_once()

    def poll_once(self) -> None:
        """
        Query one AKShare spot snapshot and push ticks for subscribed symbols.
        """
        if not self.akshare or not self.subscribed:
            return

        if len(self.subscribed) <= MAX_INDIVIDUAL_QUOTE_SYMBOLS and not self.subscribe_all:
            pushed = self._push_individual_quote_ticks()
            missing = self.subscribed.difference(pushed)
            if not missing:
                return
        else:
            missing = self.subscribed

        snapshot = self._query_snapshot()
        self.latest_snapshot = snapshot
        self._push_missing_contracts(snapshot)
        self._push_subscribed_ticks(snapshot, subscribed=missing)

    def _push_individual_quote_ticks(self) -> set[str]:
        """
        Query fast per-symbol quotes and push ticks for subscribed symbols.
        """
        pushed: set[str] = set()
        for vt_symbol in sorted(self.subscribed):
            tick = self._query_individual_quote_tick(vt_symbol)
            if not tick:
                continue
            self.on_tick(tick)
            pushed.add(vt_symbol)
        return pushed

    def _query_individual_quote_tick(self, vt_symbol: str) -> TickData | None:
        """
        Query one subscribed symbol using AKShare's single-stock bid/ask endpoint.
        """
        if not self.akshare or not self.individual_quote_endpoint:
            return None

        query = getattr(self.akshare, self.individual_quote_endpoint, None)
        if not callable(query):
            return None

        symbol, exchange = _symbol_exchange_from_value(vt_symbol)
        if not symbol:
            return None

        try:
            data = query(symbol=symbol)
        except Exception as exc:
            self.write_log(f"AKShare单票行情接口 {self.individual_quote_endpoint} 查询失败：{vt_symbol} {exc}")
            return None

        quote = data if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
        if quote.empty:
            return None

        name = self.contracts.get(vt_symbol).name if vt_symbol in self.contracts else symbol
        row = _row_from_individual_quote(quote, symbol=symbol, name=name)
        if not row:
            return None

        return _tick_from_row(row, gateway_name=self.gateway_name, timestamp=datetime.now())

    def _init_akshare(self) -> bool:
        """
        Import AKShare lazily.
        """
        if self.akshare:
            return True
        try:
            self.akshare = import_module("akshare")
            return True
        except ModuleNotFoundError:
            self.write_log("无法加载 AKShare，请先安装 akshare")
            return False

    def _query_snapshot(self) -> pd.DataFrame:
        """
        Query full A-share spot snapshot with endpoint fallback.
        """
        if not self.akshare:
            return pd.DataFrame()

        for endpoint in self.snapshot_endpoints:
            query = getattr(self.akshare, endpoint, None)
            if not callable(query):
                self.write_log(f"AKShare行情接口不存在：{endpoint}")
                continue

            try:
                data = query()
            except Exception as exc:
                self.write_log(f"AKShare行情接口 {endpoint} 查询失败：{exc}")
                continue

            snapshot = data if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
            if snapshot.empty:
                self.write_log(f"AKShare行情接口 {endpoint} 返回空数据")
                continue

            return snapshot

        return pd.DataFrame()

    def _push_contracts(self, snapshot: pd.DataFrame) -> None:
        """
        Push all valid contracts from snapshot.
        """
        for row in _iter_rows(snapshot):
            contract = _contract_from_row(row, self.gateway_name)
            if not contract:
                continue
            self.contracts[contract.vt_symbol] = contract
            self.on_contract(contract)

    def _push_missing_contracts(self, snapshot: pd.DataFrame) -> None:
        """
        Push newly seen contracts for subscribed symbols.
        """
        for row in _iter_rows(snapshot):
            contract = _contract_from_row(row, self.gateway_name)
            if not contract or contract.vt_symbol in self.contracts:
                continue
            if contract.vt_symbol in self.subscribed:
                self.contracts[contract.vt_symbol] = contract
                self.on_contract(contract)

    def _push_subscribed_ticks(
        self,
        snapshot: pd.DataFrame,
        subscribed: set[str] | None = None,
    ) -> None:
        """
        Push ticks for subscribed symbols from an already fetched snapshot.
        """
        target_symbols = subscribed or self.subscribed
        if snapshot.empty or not target_symbols:
            return

        rows = _rows_by_vt_symbol(snapshot)
        now = datetime.now()
        for vt_symbol in sorted(target_symbols):
            row = rows.get(vt_symbol)
            if row is None:
                continue
            tick = _tick_from_row(row, gateway_name=self.gateway_name, timestamp=now)
            self.on_tick(tick)

    def _register_timer(self) -> None:
        """
        Register one timer handler.
        """
        if self._timer_registered:
            return
        self.event_engine.register(EVENT_TIMER, self.process_timer_event)
        self._timer_registered = True


def _iter_rows(snapshot: pd.DataFrame) -> list[dict[str, Any]]:
    """
    Convert snapshot data to row dictionaries.
    """
    if snapshot.empty:
        return []
    return [dict(row) for row in snapshot.to_dict(orient="records")]


def _rows_by_vt_symbol(snapshot: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """
    Index snapshot rows by vn.py vt_symbol.
    """
    result: dict[str, dict[str, Any]] = {}
    for row in _iter_rows(snapshot):
        symbol, exchange = _symbol_exchange_from_value(_first_text(row, "代码", "symbol", "code"))
        if not symbol:
            continue
        vt_symbol = f"{symbol}.{exchange.value}"
        result[vt_symbol] = row
    return result


def _contract_from_row(row: dict[str, Any], gateway_name: str) -> ContractData | None:
    """
    Convert an AKShare spot row to ContractData.
    """
    symbol, exchange = _symbol_exchange_from_value(_first_text(row, "代码", "symbol", "code"))
    if not symbol:
        return None
    return ContractData(
        symbol=symbol,
        exchange=exchange,
        name=_first_text(row, "名称", "name") or symbol,
        product=Product.EQUITY,
        size=1,
        pricetick=0.01,
        min_volume=100,
        history_data=False,
        gateway_name=gateway_name,
    )


def _tick_from_row(row: dict[str, Any], gateway_name: str, timestamp: datetime) -> TickData:
    """
    Convert an AKShare spot row to TickData.
    """
    symbol, exchange = _symbol_exchange_from_value(_first_text(row, "代码", "symbol", "code"))
    tick = TickData(
        symbol=symbol,
        exchange=exchange,
        datetime=timestamp,
        name=_first_text(row, "名称", "name") or symbol,
        volume=_float(row, "成交量", "volume", "总手"),
        turnover=_float(row, "成交额", "turnover", "amount", "金额"),
        last_price=_float(row, "最新价", "最新", "last_price", "price"),
        limit_up=_float(row, "涨停", "limit_up"),
        limit_down=_float(row, "跌停", "limit_down"),
        open_price=_float(row, "今开", "open", "open_price"),
        high_price=_float(row, "最高", "high", "high_price"),
        low_price=_float(row, "最低", "low", "low_price"),
        pre_close=_float(row, "昨收", "pre_close", "pre_close_price"),
        bid_price_1=_float(row, "买入", "bid_price_1", "bid", "buy_1"),
        bid_price_2=_float(row, "bid_price_2", "buy_2"),
        bid_price_3=_float(row, "bid_price_3", "buy_3"),
        bid_price_4=_float(row, "bid_price_4", "buy_4"),
        bid_price_5=_float(row, "bid_price_5", "buy_5"),
        ask_price_1=_float(row, "卖出", "ask_price_1", "ask", "sell_1"),
        ask_price_2=_float(row, "ask_price_2", "sell_2"),
        ask_price_3=_float(row, "ask_price_3", "sell_3"),
        ask_price_4=_float(row, "ask_price_4", "sell_4"),
        ask_price_5=_float(row, "ask_price_5", "sell_5"),
        bid_volume_1=_float(row, "bid_volume_1", "buy_1_vol"),
        bid_volume_2=_float(row, "bid_volume_2", "buy_2_vol"),
        bid_volume_3=_float(row, "bid_volume_3", "buy_3_vol"),
        bid_volume_4=_float(row, "bid_volume_4", "buy_4_vol"),
        bid_volume_5=_float(row, "bid_volume_5", "buy_5_vol"),
        ask_volume_1=_float(row, "ask_volume_1", "sell_1_vol"),
        ask_volume_2=_float(row, "ask_volume_2", "sell_2_vol"),
        ask_volume_3=_float(row, "ask_volume_3", "sell_3_vol"),
        ask_volume_4=_float(row, "ask_volume_4", "sell_4_vol"),
        ask_volume_5=_float(row, "ask_volume_5", "sell_5_vol"),
        gateway_name=gateway_name,
    )
    return tick


def _row_from_individual_quote(quote: pd.DataFrame, symbol: str, name: str) -> dict[str, Any]:
    """
    Convert AKShare stock_bid_ask_em item/value data into the common row shape.
    """
    if {"item", "value"}.issubset(quote.columns):
        row = {
            str(item).strip(): value
            for item, value in zip(quote["item"], quote["value"], strict=False)
            if str(item).strip()
        }
    elif not quote.empty:
        row = dict(quote.iloc[0])
    else:
        row = {}

    if not row:
        return {}

    row["代码"] = symbol
    row["名称"] = name
    return row


def _split_symbols(raw: str) -> set[str]:
    """
    Split comma/semicolon separated vt_symbol text.
    """
    symbols: set[str] = set()
    for item in raw.replace("，", ",").replace(";", ",").split(","):
        text = item.strip().upper()
        if not text:
            continue
        normalized = _normalize_vt_symbol(text)
        if normalized:
            symbols.add(normalized)
    return symbols


def _normalize_vt_symbol(vt_symbol: str) -> str:
    """
    Normalize common A-share suffixes into vn.py exchange names.
    """
    text = vt_symbol.strip().upper()
    symbol, exchange = _symbol_exchange_from_value(text)
    if symbol:
        return f"{symbol}.{exchange.value}"
    return text


def _exchange_from_symbol(symbol: str) -> Exchange:
    """
    Guess A-share exchange from code prefix.
    """
    clean_symbol, exchange = _symbol_exchange_from_value(symbol)
    if clean_symbol:
        return exchange
    return Exchange.SZSE


def _symbol_exchange_from_subscribe_request(req: SubscribeRequest) -> tuple[str, Exchange]:
    """
    Normalize UI subscribe input while keeping vn.py vt_symbol format.
    """
    symbol, exchange = _symbol_exchange_from_value(req.symbol)
    if symbol:
        return symbol, exchange
    return req.symbol, req.exchange


def _symbol_exchange_from_value(value: str) -> tuple[str, Exchange]:
    """
    Parse AKShare/vn.py A-share codes such as 600519, sh600519 or 600519.SSE.
    """
    text = str(value or "").strip().upper()
    exchange: Exchange | None = None

    if "." in text:
        symbol_part, suffix = text.split(".", 1)
        text = symbol_part
        suffix_exchange = {
            "SH": Exchange.SSE,
            "SSE": Exchange.SSE,
            "SZ": Exchange.SZSE,
            "SZSE": Exchange.SZSE,
            "BJ": Exchange.BSE,
            "BSE": Exchange.BSE,
        }.get(suffix)
        if suffix_exchange:
            exchange = suffix_exchange

    for prefix, prefix_exchange in (
        ("SSE", Exchange.SSE),
        ("SZSE", Exchange.SZSE),
        ("BSE", Exchange.BSE),
        ("SH", Exchange.SSE),
        ("SZ", Exchange.SZSE),
        ("BJ", Exchange.BSE),
    ):
        if text.startswith(prefix):
            text = text[len(prefix) :]
            exchange = exchange or prefix_exchange
            break

    symbol = _clean_symbol(text)
    if not symbol or not symbol.isdigit():
        return "", exchange or Exchange.SZSE

    return symbol, exchange or _infer_exchange_from_clean_symbol(symbol)


def _infer_exchange_from_clean_symbol(symbol: str) -> Exchange:
    """
    Guess A-share exchange from a normalized six-digit code.
    """
    text = symbol.strip()
    if text.startswith(("6", "9")):
        return Exchange.SSE
    if text.startswith(("8", "4")):
        return Exchange.BSE
    return Exchange.SZSE


def _clean_symbol(value: str) -> str:
    """
    Keep a six-digit A-share code.
    """
    text = str(value or "").strip().upper()
    if "." in text:
        text = text.split(".", 1)[0]
    return text.zfill(6) if text.isdigit() and len(text) <= 6 else text


def _first_text(row: dict[str, Any], *keys: str) -> str:
    """
    Return first non-empty text from a row.
    """
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _float(row: dict[str, Any], *keys: str) -> float:
    """
    Return first numeric value from a row.
    """
    for key in keys:
        value = row.get(key)
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0


def _parse_snapshot_endpoints(value: Any, default: tuple[str, ...]) -> list[str]:
    """
    Parse editable AKShare endpoint order from UI settings.
    """
    if isinstance(value, (list, tuple, set)):
        raw_items = [str(item) for item in value]
    else:
        raw_items = str(value or "").replace("，", ",").replace(";", ",").split(",")

    endpoints = [item.strip() for item in raw_items if item.strip()]
    return endpoints or list(default)


def _is_enabled(value: Any) -> bool:
    """
    Parse yes/no style gateway settings.
    """
    return str(value).strip().lower() in {"1", "true", "yes", "y", "是", "开启"}
