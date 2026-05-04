from datetime import datetime
from types import ModuleType

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


def test_qmt_and_xt_providers_degrade_when_dependency_missing(monkeypatch):
    """QMT/XT adapters should be diagnosable when xtquant is not installed."""
    import importlib

    def missing_xtquant(name: str, package: str | None = None):
        if name == "xtquant.xtdata":
            raise ModuleNotFoundError(name)
        return ModuleType(name)

    monkeypatch.setattr(importlib, "import_module", missing_xtquant)

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
    assert any("xtquant.xtdata" in message for message in messages)


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


def test_p9_event_source_quality_migration_is_registered():
    """Default migrations should upgrade existing event tables with P9 source-quality columns."""
    from vnpy_tradingagents.schema_init import DEFAULT_MIGRATIONS

    migrations = {migration.version: migration.sql for migration in DEFAULT_MIGRATIONS}

    assert "0002_event_source_quality" in migrations
    assert "ALTER TABLE news_raw ADD COLUMN IF NOT EXISTS source_quality TEXT" in migrations[
        "0002_event_source_quality"
    ]
    assert "CREATE TABLE IF NOT EXISTS event_quality_report" in migrations[
        "0002_event_source_quality"
    ]


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
