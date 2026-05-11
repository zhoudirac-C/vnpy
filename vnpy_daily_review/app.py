from pathlib import Path

from vnpy.trader.app import BaseApp

from .engine import APP_NAME, DailyMarketReviewEngine


class DailyMarketReviewApp(BaseApp):
    """
    Daily market review app metadata for VeighNa.
    """

    app_name: str = APP_NAME
    app_module: str = "vnpy_daily_review"
    app_path: Path = Path(__file__).parent
    display_name: str = "每日市场复盘"
    engine_class: type[DailyMarketReviewEngine] = DailyMarketReviewEngine
    widget_name: str = "DailyMarketReviewWidget"
    icon_name: str = str(Path(__file__).parent / "ui" / "daily_review.svg")
    show_on_toolbar: bool = True
