"""
Bootstrap helpers for wiring the daily market review service into vn.py.
"""

from typing import Any

from vnpy.trader.engine import MainEngine
from vnpy.trader.setting import SETTINGS
from vnpy_router.event_storage import PostgresEventStorage
from vnpy_router.financial_storage import PostgresFinancialStorage
from vnpy_router.peewee import PeeweeConnectionAdapter, create_vnpy_postgres_database

from .ai import build_daily_review_ai_orchestrator_from_settings
from .engine import APP_NAME
from .providers import VnpyAkshareDailyReviewProvider
from .service import DailyReviewService
from .storage import InMemoryDailyReviewRepository, PeeweeDailyReviewRepository


def configure_daily_review_services(main_engine: MainEngine) -> DailyReviewService | None:
    """
    Attach the migrated daily review service to DailyMarketReviewEngine.
    """
    engine: Any = main_engine.get_engine(APP_NAME)
    if engine is None:
        return None

    repository: Any
    event_storage: Any | None = None
    financial_storage: Any | None = None
    try:
        database = create_vnpy_postgres_database(SETTINGS)
        database.connect(reuse_if_open=True)
        repository = PeeweeDailyReviewRepository(database)
        repository.create_schema()
        connection = PeeweeConnectionAdapter(database)
        event_storage = PostgresEventStorage(connection)
        event_storage.create_schema()
        financial_storage = PostgresFinancialStorage(connection)
        financial_storage.create_schema()
    except Exception:
        repository = InMemoryDailyReviewRepository()

    service = DailyReviewService(
        VnpyAkshareDailyReviewProvider(
            main_engine,
            event_storage=event_storage,
            financial_storage=financial_storage,
        ),
        repository=repository,
        ai_orchestrator=build_daily_review_ai_orchestrator_from_settings(SETTINGS),
    )
    engine.set_review_service(service)
    return service
