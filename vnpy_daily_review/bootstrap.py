"""
Bootstrap helpers for wiring the daily market review service into vn.py.
"""

from typing import Any

from vnpy.trader.engine import MainEngine

from .engine import APP_NAME
from .providers import VnpyAkshareDailyReviewProvider
from .service import DailyReviewService


def configure_daily_review_services(main_engine: MainEngine) -> DailyReviewService | None:
    """
    Attach the migrated daily review service to DailyMarketReviewEngine.
    """
    engine: Any = main_engine.get_engine(APP_NAME)
    if engine is None:
        return None

    service = DailyReviewService(VnpyAkshareDailyReviewProvider(main_engine))
    engine.set_review_service(service)
    return service
