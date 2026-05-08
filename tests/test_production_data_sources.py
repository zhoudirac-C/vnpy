from datetime import datetime
from types import ModuleType
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import BarData, HistoryRequest


def test_provider_capability_filters_router_candidates():
    """DataProviderRouter should skip providers that cannot satisfy request capabilities."""
    from vnpy_router.providers.capability import ProviderCapability
    from vnpy_router.router import DataProviderRouter

    unsupported = CapabilityFakeProvider(
        "minute_only",
        ProviderCapability(
            name="minute_only",
            intervals=frozenset({Interval.MINUTE}),
            fields=frozenset({"open", "high", "low", "close"}),
        ),
        [_bar(gateway_name="minute_only")],
    )
    supported = CapabilityFakeProvider(
        "daily",
        ProviderCapability(
            name="daily",
            intervals=frozenset({Interval.DAILY}),
            fields=frozenset({"open", "high", "low", "close", "volume"}),
        ),
        [_bar(gateway_name="daily")],
    )
    messages: list[str] = []

    bars = DataProviderRouter([unsupported, supported]).query_bar_history(
        _history_request(),
        output=messages.append,
    )

    assert unsupported.query_count == 0
    assert supported.query_count == 1
    assert bars[0].gateway_name == "daily"
    assert any("capability" in message.lower() for message in messages)


def test_tushare_provider_requires_token_and_sets_metadata(monkeypatch):
    """TuShareProvider should degrade without token and attach metadata with token."""
    import importlib

    from vnpy_router.providers.tushare import TuShareProvider

    messages: list[str] = []
    assert not TuShareProvider(token="").init(output=messages.append)
    assert any("token" in message.lower() for message in messages)

    fake_tushare = FakeTushareModule()
    monkeypatch.setattr(importlib, "import_module", lambda name: fake_tushare)

    provider = TuShareProvider(token="secret-token", provider_version="test-version")
    bars = provider.query_bar_history(_history_request(), output=messages.append)

    assert fake_tushare.token == "secret-token"
    assert fake_tushare.pro_bar_kwargs["ts_code"] == "600519.SH"
    assert fake_tushare.pro_bar_kwargs["adj"] == ""
    assert len(bars) == 1
    assert bars[0].close_price == 1695
    assert bars[0].extra["provider_name"] == "tushare"
    assert bars[0].extra["provider_endpoint"] == "pro_bar"
    assert bars[0].extra["provider_version"] == "test-version"
    assert "secret-token" not in str(bars[0].extra)


def test_akshare_provider_declares_research_only_boundaries(monkeypatch):
    """AKShare provider should expose production boundaries without importing dependency for unsupported requests."""
    from vnpy_router.providers import akshare as akshare_module
    from vnpy_router.providers.akshare import AkshareProvider

    def fail_import(name: str):
        raise AssertionError(f"should not import {name} for unsupported interval")

    monkeypatch.setattr(akshare_module, "import_module", fail_import)

    provider = AkshareProvider()
    metadata = provider.capability.to_metadata()
    messages: list[str] = []
    req = _history_request()
    req.interval = Interval.TICK

    assert provider.query_bar_history(req, output=messages.append) == []
    assert metadata["supports_tick"] is False
    assert metadata["realtime"] is False
    assert metadata["metadata"]["production_scope"] == "research_history"
    assert "minute" in metadata["metadata"]["supported_intervals"]
    assert "tick" in metadata["metadata"]["unsupported_intervals"]
    assert "Gateway" in metadata["realtime_notes"]
    assert any("does not support interval" in message for message in messages)


def test_akshare_provider_supports_minute_history(monkeypatch):
    """AKShare provider should download minute bars for CTA Backtester."""
    from vnpy_router.providers import akshare as akshare_module
    from vnpy_router.providers.akshare import AkshareProvider

    fake_akshare = FakeMinuteAkshareModule()
    monkeypatch.setattr(akshare_module, "import_module", lambda name: fake_akshare)

    req = _history_request()
    req.interval = Interval.MINUTE
    req.start = datetime(2024, 1, 3, 9, 30)
    req.end = datetime(2024, 1, 3, 9, 32)
    messages: list[str] = []

    provider = AkshareProvider(endpoints=["stock_zh_a_hist_min_em"])
    bars = provider.query_bar_history(req, output=messages.append)

    assert fake_akshare.hist_min_kwargs == {
        "symbol": "600519",
        "start_date": "2024-01-03 09:30:00",
        "end_date": "2024-01-03 09:32:00",
        "period": "1",
        "adjust": "",
    }
    assert [bar.datetime for bar in bars] == [
        datetime(2024, 1, 3, 9, 30),
        datetime(2024, 1, 3, 9, 31),
    ]
    assert [bar.interval for bar in bars] == [Interval.MINUTE, Interval.MINUTE]
    assert bars[0].open_price == 1688
    assert bars[1].close_price == 1698
    assert bars[0].extra["provider_endpoint"] == "stock_zh_a_hist_min_em"


def test_akshare_provider_accepts_timezone_aware_backtester_dates(monkeypatch):
    """AKShare provider should compare UI timezone-aware dates with naive AKShare rows."""
    from vnpy_router.providers import akshare as akshare_module
    from vnpy_router.providers.akshare import AkshareProvider

    fake_akshare = FakeMinuteAkshareModule()
    monkeypatch.setattr(akshare_module, "import_module", lambda name: fake_akshare)

    tz = ZoneInfo("Asia/Shanghai")
    req = _history_request()
    req.interval = Interval.MINUTE
    req.start = datetime(2024, 1, 3, 9, 30, tzinfo=tz)
    req.end = datetime(2024, 1, 3, 9, 32, tzinfo=tz)

    bars = AkshareProvider(endpoints=["stock_zh_a_hist_min_em"]).query_bar_history(req)

    assert [bar.datetime for bar in bars] == [
        datetime(2024, 1, 3, 9, 30),
        datetime(2024, 1, 3, 9, 31),
    ]


def test_akshare_provider_falls_back_between_internal_endpoints(monkeypatch):
    """AKShare provider should try secondary public endpoints when the primary endpoint fails."""
    from vnpy_router.providers import akshare as akshare_module
    from vnpy_router.providers.akshare import AkshareProvider

    fake_akshare = FakeAkshareModule()
    monkeypatch.setattr(akshare_module, "import_module", lambda name: fake_akshare)

    messages: list[str] = []
    provider = AkshareProvider(endpoints=["stock_zh_a_hist", "stock_zh_a_hist_tx"])

    bars = provider.query_bar_history(_history_request(), output=messages.append)

    assert fake_akshare.calls == ["stock_zh_a_hist", "stock_zh_a_hist_tx"]
    assert len(bars) == 1
    assert bars[0].close_price == 1695
    assert bars[0].extra["provider_name"] == "akshare"
    assert bars[0].extra["provider_endpoint"] == "stock_zh_a_hist_tx"
    assert any("stock_zh_a_hist query failed" in message for message in messages)


def test_qmt_and_xt_providers_wrap_vnpy_datafeed_plugins(monkeypatch):
    """QMT/XT adapters should route through vn.py datafeed plugins, not xtquant directly."""
    import importlib

    def missing_vnpy_xt(name: str, package: str | None = None):
        if name == "vnpy_xt":
            raise ModuleNotFoundError(name)
        return ModuleType(name)

    monkeypatch.setattr(importlib, "import_module", missing_vnpy_xt)

    from vnpy_router.providers.qmt import QmtProvider
    from vnpy_router.providers.xt import XtProvider

    messages: list[str] = []
    qmt = QmtProvider()
    xt = XtProvider()

    assert not qmt.init(output=messages.append)
    assert not xt.init(output=messages.append)
    assert qmt.query_bar_history(_history_request(), output=messages.append) == []
    assert xt.query_bar_history(_history_request(), output=messages.append) == []
    assert qmt.capability.history
    assert not qmt.capability.realtime
    assert "gateway" in qmt.capability.realtime_notes.lower()
    assert any("vnpy_xt" in message for message in messages)


def test_event_storage_production_columns_and_rejects_source_less_news():
    """Event storage should keep production quality fields and reject source-less raw news."""
    from vnpy_router.event_storage import EVENT_SCHEMA, NewsRaw, PostgresEventStorage

    for column in [
        "source_quality TEXT",
        "trust_score DOUBLE PRECISION",
        "spam_score DOUBLE PRECISION",
        "dedup_window_seconds INTEGER",
        "review_status TEXT",
    ]:
        assert column in EVENT_SCHEMA
    assert "CREATE TABLE IF NOT EXISTS event_quality_report" in EVENT_SCHEMA

    storage = PostgresEventStorage(FakeConnection())
    with pytest.raises(ValueError, match="source"):
        storage.save_news_raw(
            NewsRaw(
                source="",
                url="",
                title="无来源新闻",
                content="不能进入上下文",
                published_at=datetime(2024, 1, 3),
                provider_name="manual",
            )
        )


def test_event_normalizer_rejects_source_less_event():
    """News events without source should not enter TradingAgents context."""
    from vnpy_router.event_normalizer import EventNormalizer
    from vnpy_router.event_storage import NewsEvent

    event = NewsEvent(
        event_id="event-1",
        vt_symbol="600519.SSE",
        title="无来源事件",
        summary="不能进入 TradingAgents",
        event_type="social",
        occurred_at=datetime(2024, 1, 3),
        source="",
        provider_name="manual",
    )

    with pytest.raises(ValueError, match="source"):
        EventNormalizer().build_news_snapshot("600519.SSE", [event])


def test_social_provider_loads_manual_posts_and_degrades_missing_file(tmp_path):
    """SocialProvider should support local/manual labels and degrade when optional file is missing."""
    from vnpy_router.providers.social import SocialProvider

    path = tmp_path / "social.csv"
    path.write_text(
        "\n".join(
            [
                "vt_symbol,source,author,content,published_at,sentiment_score,label,review_status",
                "600519.SSE,manual,user1,白酒情绪回暖,2024-01-03T10:00:00,0.4,bullish,reviewed",
                "000001.SZ,manual,user2,银行波动,2024-01-03T10:01:00,-0.1,bearish,reviewed",
            ]
        ),
        encoding="utf-8",
    )

    provider = SocialProvider(path)
    posts = provider.query_posts("600519.SSE")
    snapshot = provider.score_posts("600519.SSE", posts, datetime(2024, 1, 3))

    assert len(posts) == 1
    assert posts[0].source == "manual"
    assert posts[0].raw_hash
    assert posts[0].review_status == "reviewed"
    assert snapshot.payload["score"] == 0.4
    assert snapshot.payload["post_count"] == 1
    assert snapshot.payload["labels"] == {"bullish": 1}

    messages: list[str] = []
    assert SocialProvider(tmp_path / "missing.csv").query_posts(
        "600519.SSE",
        output=messages.append,
    ) == []
    assert any("missing" in message.lower() for message in messages)


def test_datafeed_builds_configured_production_providers(monkeypatch):
    """Router datafeed should instantiate configured production providers."""
    from vnpy.trader.setting import SETTINGS
    from vnpy_router import datafeed as datafeed_module

    monkeypatch.setitem(
        SETTINGS,
        "router.providers",
        [
            {"name": "tushare", "token": "secret-token"},
            {"name": "qmt"},
            {"name": "xt"},
        ],
    )

    datafeed = datafeed_module.Datafeed()

    assert [provider.name for provider in datafeed.router.providers] == [
        "tushare",
        "qmt",
        "xt",
    ]


def test_readiness_checker_reports_production_provider_diagnostics(tmp_path):
    """Readiness checker should diagnose production providers explicitly."""
    from vnpy_tradingagents.readiness import ProductionReadinessChecker, ReadinessStatus

    report = ProductionReadinessChecker(
        settings={
            "router.providers": f"tushare,qmt,xt,social:{tmp_path / 'missing.csv'}",
            "tradingagents.api_key_env_var": "OPENAI_API_KEY",
            "tradingagents.intraday.enabled": True,
        },
        environ={
            "OPENAI_API_KEY": "llm-key",
            "TUSHARE_TOKEN": "tushare-key",
        },
        module_available=lambda name: name == "tushare",
        path_exists=lambda path: False,
    ).check()

    assert report.by_name("tushare_provider").status == ReadinessStatus.READY
    assert report.by_name("qmt_provider").status == ReadinessStatus.WARNING
    assert report.by_name("xt_provider").status == ReadinessStatus.WARNING
    assert report.by_name("social_provider").status == ReadinessStatus.WARNING
    assert report.by_name("intraday_minute_source").status == ReadinessStatus.WARNING

    ready_report = ProductionReadinessChecker(
        settings={
            "router.providers": "qmt",
            "tradingagents.api_key_env_var": "OPENAI_API_KEY",
            "tradingagents.intraday.enabled": True,
        },
        environ={"OPENAI_API_KEY": "llm-key"},
        module_available=lambda name: name in {"vnpy_xt", "peewee"},
    ).check()

    assert ready_report.by_name("intraday_minute_source").status == ReadinessStatus.READY


def test_p9_event_source_quality_models_are_registered():
    """Peewee extension models should include P9 event source quality fields."""
    from peewee import SqliteDatabase

    from vnpy_router.extension_models import build_router_extension_models

    models = {
        model._meta.table_name: model
        for model in build_router_extension_models(SqliteDatabase(":memory:"))
    }

    assert "event_quality_report" in models
    assert "source_quality" in models["news_raw"]._meta.fields
    assert "trust_score" in models["news_event"]._meta.fields
    assert "review_status" in models["social_post_raw"]._meta.fields


def _history_request() -> HistoryRequest:
    """Build a reusable history request."""
    return HistoryRequest(
        symbol="600519",
        exchange=Exchange.SSE,
        interval=Interval.DAILY,
        start=datetime(2024, 1, 1),
        end=datetime(2024, 1, 3),
    )


def _bar(gateway_name: str = "local_file") -> BarData:
    """Build a reusable bar."""
    bar = BarData(
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
        gateway_name=gateway_name,
    )
    bar.extra = {
        "provider_name": gateway_name,
        "provider_endpoint": "fake",
        "provider_version": "test",
    }
    return bar


class CapabilityFakeProvider:
    """Provider fake with explicit production capability."""

    def __init__(self, name, capability, bars) -> None:
        self.name = name
        self.capability = capability
        self.bars = bars
        self.query_count = 0

    def init(self, output=print) -> bool:
        return True

    def query_bar_history(self, req, output=print):
        self.query_count += 1
        return self.bars


class FakeTushareModule:
    """Tiny TuShare module fake."""

    def __init__(self) -> None:
        self.token = ""
        self.pro_bar_kwargs = {}

    def set_token(self, token: str) -> None:
        self.token = token

    def pro_bar(self, **kwargs):
        self.pro_bar_kwargs = kwargs
        return pd.DataFrame(
            [
                {
                    "trade_date": "20240103",
                    "open": 1688,
                    "high": 1700,
                    "low": 1680,
                    "close": 1695,
                    "vol": 12,
                    "amount": 2034,
                }
            ]
        )


class FakeAkshareModule:
    """Tiny AKShare module that fails primary endpoint and succeeds on fallback."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def stock_zh_a_hist(self, **kwargs):
        self.calls.append("stock_zh_a_hist")
        raise RuntimeError("primary down")

    def stock_zh_a_hist_tx(self, **kwargs):
        self.calls.append("stock_zh_a_hist_tx")
        assert kwargs["symbol"] == "sh600519"
        return pd.DataFrame(
            [
                {
                    "date": "2024-01-03",
                    "open": 1688,
                    "high": 1700,
                    "low": 1680,
                    "close": 1695,
                    "amount": 1200,
                }
            ]
        )


class FakeMinuteAkshareModule:
    """Tiny AKShare module that returns minute history."""

    def __init__(self) -> None:
        self.hist_min_kwargs = {}

    def stock_zh_a_hist_min_em(self, **kwargs):
        self.hist_min_kwargs = kwargs
        return pd.DataFrame(
            [
                {
                    "时间": "2024-01-03 09:30:00",
                    "开盘": 1688,
                    "最高": 1700,
                    "最低": 1680,
                    "收盘": 1695,
                    "成交量": 12,
                    "成交额": 2034,
                },
                {
                    "时间": "2024-01-03 09:31:00",
                    "开盘": 1695,
                    "最高": 1702,
                    "最低": 1690,
                    "收盘": 1698,
                    "成交量": 10,
                    "成交额": 16980,
                },
            ]
        )


class FakeCursor:
    """Tiny DB-API cursor fake."""

    def __init__(self) -> None:
        self.executed = []

    def execute(self, sql, params=None) -> None:
        self.executed.append((sql, params or {}))

    def close(self) -> None:
        return


class FakeConnection:
    """Tiny DB-API connection fake."""

    def __init__(self) -> None:
        self.cursor_obj = FakeCursor()
        self.committed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self) -> None:
        self.committed = True
