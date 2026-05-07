from types import SimpleNamespace

import pandas as pd

from vnpy.event import Event
from vnpy.trader.constant import Exchange, Product
from vnpy.trader.object import SubscribeRequest


def test_akshare_gateway_loads_contracts_and_polls_subscribed_ticks(monkeypatch):
    """AKShare Gateway should expose A-share contracts and push ticks for subscribed symbols."""
    import vnpy_akshare_gateway.gateway as gateway_module
    from vnpy_akshare_gateway import AkshareGateway

    fake_akshare = FakeAkshare(
        pd.DataFrame(
            [
                {
                    "代码": "600519",
                    "名称": "贵州茅台",
                    "最新价": 1688.0,
                    "成交量": 1000,
                    "成交额": 1688000,
                    "今开": 1680.0,
                    "最高": 1699.0,
                    "最低": 1678.0,
                    "昨收": 1670.0,
                },
                {
                    "代码": "000001",
                    "名称": "平安银行",
                    "最新价": 10.5,
                    "成交量": 2000,
                    "成交额": 21000,
                    "今开": 10.2,
                    "最高": 10.6,
                    "最低": 10.1,
                    "昨收": 10.0,
                },
            ]
        )
    )
    monkeypatch.setattr(gateway_module, "import_module", lambda name: fake_akshare)

    gateway = AkshareGateway(FakeEventEngine(), "AKSHARE")
    contracts = []
    ticks = []
    gateway.on_contract = contracts.append
    gateway.on_tick = ticks.append

    gateway.connect(
        {
            "轮询间隔秒数": 5,
            "订阅代码": "600519.SSE",
            "连接后加载全市场合约": "是",
            "订阅全市场行情": "否",
        }
    )
    gateway.poll_once()

    assert [(contract.vt_symbol, contract.name, contract.product) for contract in contracts] == [
        ("600519.SSE", "贵州茅台", Product.EQUITY),
        ("000001.SZSE", "平安银行", Product.EQUITY),
    ]
    assert [tick.vt_symbol for tick in ticks] == ["600519.SSE"]
    assert ticks[0].last_price == 1688.0
    assert ticks[0].open_price == 1680.0
    assert ticks[0].high_price == 1699.0
    assert ticks[0].low_price == 1678.0
    assert ticks[0].pre_close == 1670.0


def test_akshare_gateway_subscribe_adds_symbol_and_rejects_trading(monkeypatch):
    """Manual UI subscription should work, while trading requests remain disabled."""
    import vnpy_akshare_gateway.gateway as gateway_module
    from vnpy_akshare_gateway import AkshareGateway

    fake_akshare = FakeAkshare(
        pd.DataFrame(
            [
                {
                    "代码": "000001",
                    "名称": "平安银行",
                    "最新价": 10.5,
                    "成交量": 2000,
                    "成交额": 21000,
                    "今开": 10.2,
                    "最高": 10.6,
                    "最低": 10.1,
                    "昨收": 10.0,
                }
            ]
        )
    )
    monkeypatch.setattr(gateway_module, "import_module", lambda name: fake_akshare)

    gateway = AkshareGateway(FakeEventEngine(), "AKSHARE")
    contracts = []
    ticks = []
    logs = []
    gateway.on_contract = contracts.append
    gateway.on_tick = ticks.append
    gateway.write_log = logs.append

    gateway.connect(
        {
            "轮询间隔秒数": 5,
            "订阅代码": "",
            "连接后加载全市场合约": "否",
            "订阅全市场行情": "否",
        }
    )
    gateway.subscribe(SubscribeRequest(symbol="000001", exchange=Exchange.SZSE))
    gateway.poll_once()

    assert [contract.vt_symbol for contract in contracts] == ["000001.SZSE"]
    assert [tick.vt_symbol for tick in ticks] == ["000001.SZSE"]
    assert gateway.send_order(SimpleNamespace()) == ""
    assert any("只读" in message for message in logs)


def test_akshare_gateway_connect_subscription_pushes_only_matching_contracts(monkeypatch):
    """Connection-time subscriptions should work without loading the full market contract list."""
    import vnpy_akshare_gateway.gateway as gateway_module
    from vnpy_akshare_gateway import AkshareGateway

    fake_akshare = FakeAkshare(
        pd.DataFrame(
            [
                {"代码": "600519", "名称": "贵州茅台", "最新价": 1688.0},
                {"代码": "000001", "名称": "平安银行", "最新价": 10.5},
            ]
        )
    )
    monkeypatch.setattr(gateway_module, "import_module", lambda name: fake_akshare)

    gateway = AkshareGateway(FakeEventEngine(), "AKSHARE")
    contracts = []
    ticks = []
    gateway.on_contract = contracts.append
    gateway.on_tick = ticks.append

    gateway.connect(
        {
            "轮询间隔秒数": 5,
            "订阅代码": "600519.SH",
            "连接后加载全市场合约": "否",
            "订阅全市场行情": "否",
        }
    )
    gateway.poll_once()

    assert [contract.vt_symbol for contract in contracts] == ["600519.SSE"]
    assert [tick.vt_symbol for tick in ticks] == ["600519.SSE"]


def test_akshare_gateway_falls_back_and_normalizes_prefixed_codes(monkeypatch):
    """Gateway should fall back to AKShare legacy spot data and parse sh/sz/bj prefixes."""
    import vnpy_akshare_gateway.gateway as gateway_module
    from vnpy_akshare_gateway import AkshareGateway

    fake_akshare = FakeAkshare(
        pd.DataFrame(
            [
                {
                    "代码": "sh600519",
                    "名称": "贵州茅台",
                    "最新价": 1688.0,
                    "成交量": 1000,
                    "成交额": 1688000,
                    "今开": 1680.0,
                    "最高": 1699.0,
                    "最低": 1678.0,
                    "昨收": 1670.0,
                    "买入": 1687.9,
                    "卖出": 1688.1,
                },
                {
                    "代码": "sz000001",
                    "名称": "平安银行",
                    "最新价": 10.5,
                    "成交量": 2000,
                    "成交额": 21000,
                },
                {
                    "代码": "bj920000",
                    "名称": "北证样例",
                    "最新价": 8.8,
                    "成交量": 300,
                    "成交额": 2640,
                },
            ]
        ),
        primary_error=RuntimeError("primary disconnected"),
    )
    monkeypatch.setattr(gateway_module, "import_module", lambda name: fake_akshare)

    gateway = AkshareGateway(FakeEventEngine(), "AKSHARE")
    contracts = []
    ticks = []
    logs = []
    gateway.on_contract = contracts.append
    gateway.on_tick = ticks.append
    gateway.write_log = logs.append

    gateway.connect(
        {
            "轮询间隔秒数": 5,
            "订阅代码": "SH600519",
            "连接后加载全市场合约": "是",
            "订阅全市场行情": "否",
            "快照接口顺序": "stock_zh_a_spot_em,stock_zh_a_spot",
        }
    )
    gateway.poll_once()

    assert fake_akshare.calls == [
        "stock_zh_a_spot_em",
        "stock_zh_a_spot",
        "stock_zh_a_spot_em",
        "stock_zh_a_spot",
    ]
    assert [contract.vt_symbol for contract in contracts] == [
        "600519.SSE",
        "000001.SZSE",
        "920000.BSE",
    ]
    assert [tick.vt_symbol for tick in ticks] == ["600519.SSE"]
    assert ticks[0].bid_price_1 == 1687.9
    assert ticks[0].ask_price_1 == 1688.1
    assert any("stock_zh_a_spot_em 查询失败" in message for message in logs)


class FakeEventEngine:
    """Small event engine fake with timer registration tracking."""

    def __init__(self) -> None:
        self.handlers = []

    def put(self, event: Event) -> None:
        pass

    def register(self, event_type, handler) -> None:
        self.handlers.append((event_type, handler))

    def unregister(self, event_type, handler) -> None:
        if (event_type, handler) in self.handlers:
            self.handlers.remove((event_type, handler))


class FakeAkshare:
    """AKShare module fake."""

    def __init__(self, snapshot: pd.DataFrame, primary_error: Exception | None = None) -> None:
        self.snapshot = snapshot
        self.primary_error = primary_error
        self.calls = []

    def stock_zh_a_spot_em(self) -> pd.DataFrame:
        self.calls.append("stock_zh_a_spot_em")
        if self.primary_error:
            raise self.primary_error
        return self.snapshot

    def stock_zh_a_spot(self) -> pd.DataFrame:
        self.calls.append("stock_zh_a_spot")
        return self.snapshot
