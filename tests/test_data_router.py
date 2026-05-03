from datetime import datetime

from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import HistoryRequest
from vnpy.trader.setting import SETTINGS


def test_get_datafeed_loads_router_datafeed(monkeypatch):
    """get_datafeed should load vnpy_router when datafeed.name is router."""
    from vnpy.trader import datafeed as datafeed_module

    monkeypatch.setitem(SETTINGS, "datafeed.name", "router")
    monkeypatch.setattr(datafeed_module, "datafeed", None)

    datafeed = datafeed_module.get_datafeed()

    from vnpy_router import Datafeed

    assert isinstance(datafeed, Datafeed)


def test_local_file_provider_returns_bar_data(tmp_path):
    """LocalFileProvider should map CSV rows into vn.py BarData."""
    csv_file = tmp_path / "600519.SSE_d.csv"
    csv_file.write_text(
        "\n".join(
            [
                "datetime,open,high,low,close,volume,turnover,open_interest",
                "2024-01-02,1680,1690,1670,1688,1000,1688000,0",
                "2024-01-03,1688,1700,1680,1695,1200,2034000,0",
            ]
        ),
        encoding="utf-8",
    )

    from vnpy_router.providers.local_file import LocalFileProvider

    provider = LocalFileProvider(base_path=tmp_path)
    req = HistoryRequest(
        symbol="600519",
        exchange=Exchange.SSE,
        interval=Interval.DAILY,
        start=datetime(2024, 1, 3),
        end=datetime(2024, 1, 3),
    )

    bars = provider.query_bar_history(req)

    assert len(bars) == 1
    bar = bars[0]
    assert bar.vt_symbol == "600519.SSE"
    assert bar.interval == Interval.DAILY
    assert bar.datetime == datetime(2024, 1, 3)
    assert bar.open_price == 1688
    assert bar.high_price == 1700
    assert bar.low_price == 1680
    assert bar.close_price == 1695
    assert bar.volume == 1200
    assert bar.turnover == 2034000
    assert bar.gateway_name == "local_file"
    assert bar.extra["provider_name"] == "local_file"
    assert bar.extra["provider_endpoint"].endswith("600519.SSE_d.csv")


def test_quality_checker_reports_invalid_bar():
    """DataQualityChecker should flag impossible OHLC relationships."""
    from vnpy.trader.object import BarData
    from vnpy_router.quality import QualityStatus, check_bar_data

    bar = BarData(
        symbol="600519",
        exchange=Exchange.SSE,
        datetime=datetime(2024, 1, 2),
        interval=Interval.DAILY,
        open_price=10,
        high_price=9,
        low_price=8,
        close_price=10,
        volume=100,
        gateway_name="local_file",
    )

    report = check_bar_data("local_file", [bar])

    assert report.status == QualityStatus.FAILED
    assert report.issues[0].code == "invalid_high_price"


def test_akshare_provider_missing_dependency_degrades(monkeypatch):
    """AkshareProvider should degrade to empty data when akshare is missing."""
    import importlib

    real_import_module = importlib.import_module

    def fake_import_module(name: str, package: str | None = None):
        if name == "akshare":
            raise ModuleNotFoundError(name)
        return real_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    from vnpy_router.providers.akshare import AkshareProvider

    messages: list[str] = []
    provider = AkshareProvider()
    req = HistoryRequest(
        symbol="600519",
        exchange=Exchange.SSE,
        interval=Interval.DAILY,
        start=datetime(2024, 1, 1),
        end=datetime(2024, 1, 3),
    )

    assert not provider.init(output=messages.append)
    assert provider.query_bar_history(req, output=messages.append) == []
    assert any("akshare" in message.lower() for message in messages)
