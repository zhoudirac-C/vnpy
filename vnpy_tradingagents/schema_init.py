"""
Peewee-based initialization for TradingAgents/router extension tables.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from vnpy.trader.setting import SETTINGS
from vnpy_router.extension_models import (
    ROUTER_EXTENSION_TABLE_NAMES,
    build_router_extension_models,
)
from vnpy_router.peewee import create_vnpy_postgres_database
from vnpy_daily_review.models import (
    DAILY_REVIEW_EXTENSION_TABLE_NAMES,
    build_daily_review_extension_models,
)
from vnpy_seven_boll.models import (
    SEVEN_BOLL_EXTENSION_TABLE_NAMES,
    build_seven_boll_extension_models,
)

from .models import (
    TRADINGAGENTS_EXTENSION_TABLE_NAMES,
    build_tradingagents_extension_models,
)


EXTENSION_TABLE_NAMES: tuple[str, ...] = (
    ROUTER_EXTENSION_TABLE_NAMES
    + TRADINGAGENTS_EXTENSION_TABLE_NAMES
    + DAILY_REVIEW_EXTENSION_TABLE_NAMES
    + SEVEN_BOLL_EXTENSION_TABLE_NAMES
)


ADDITIVE_SCHEMA_UPGRADE_SQL: str = """
ALTER TABLE news_raw ADD COLUMN IF NOT EXISTS source_quality TEXT;
ALTER TABLE news_raw ADD COLUMN IF NOT EXISTS trust_score DOUBLE PRECISION;
ALTER TABLE news_raw ADD COLUMN IF NOT EXISTS relevance_score DOUBLE PRECISION;
ALTER TABLE news_raw ADD COLUMN IF NOT EXISTS spam_score DOUBLE PRECISION;
ALTER TABLE news_raw ADD COLUMN IF NOT EXISTS cluster_id TEXT;
ALTER TABLE news_raw ADD COLUMN IF NOT EXISTS dedup_window_seconds INTEGER;
ALTER TABLE news_raw ADD COLUMN IF NOT EXISTS review_status TEXT;

ALTER TABLE news_event ADD COLUMN IF NOT EXISTS source_quality TEXT;
ALTER TABLE news_event ADD COLUMN IF NOT EXISTS trust_score DOUBLE PRECISION;
ALTER TABLE news_event ADD COLUMN IF NOT EXISTS relevance_score DOUBLE PRECISION;
ALTER TABLE news_event ADD COLUMN IF NOT EXISTS spam_score DOUBLE PRECISION;
ALTER TABLE news_event ADD COLUMN IF NOT EXISTS cluster_id TEXT;
ALTER TABLE news_event ADD COLUMN IF NOT EXISTS dedup_window_seconds INTEGER;
ALTER TABLE news_event ADD COLUMN IF NOT EXISTS review_status TEXT;

ALTER TABLE event_symbol_link ADD COLUMN IF NOT EXISTS relevance_score DOUBLE PRECISION;
ALTER TABLE event_symbol_link ADD COLUMN IF NOT EXISTS link_reason TEXT;

ALTER TABLE social_post_raw ADD COLUMN IF NOT EXISTS source_quality TEXT;
ALTER TABLE social_post_raw ADD COLUMN IF NOT EXISTS trust_score DOUBLE PRECISION;
ALTER TABLE social_post_raw ADD COLUMN IF NOT EXISTS spam_score DOUBLE PRECISION;
ALTER TABLE social_post_raw ADD COLUMN IF NOT EXISTS dedup_window_seconds INTEGER;
ALTER TABLE social_post_raw ADD COLUMN IF NOT EXISTS review_status TEXT;
"""


@dataclass(frozen=True)
class SchemaInitResult:
    """
    Result of idempotent Peewee create_tables initialization.
    """

    created_or_existing_tables: list[str]


@dataclass(frozen=True)
class SchemaStatus:
    """
    Extension table presence status.
    """

    tables: dict[str, str]


def initialize_postgres_schema(
    database: Any | None = None,
    settings: Mapping[str, Any] | None = None,
) -> SchemaInitResult:
    """
    Idempotently create all TradingAgents and router extension tables.
    """
    db = database or create_vnpy_postgres_database(settings or SETTINGS)
    _connect(db)
    models: list[type] = _build_extension_models(db)
    db.create_tables(models, safe=True)
    _apply_additive_schema_upgrades(db)
    return SchemaInitResult(created_or_existing_tables=_table_names(models))


def schema_status(
    database: Any | None = None,
    settings: Mapping[str, Any] | None = None,
) -> SchemaStatus:
    """
    Return ready/missing status for every extension table.
    """
    db = database or create_vnpy_postgres_database(settings or SETTINGS)
    _connect(db)
    existing_tables: set[str] = set(db.get_tables())
    return SchemaStatus(
        tables={
            table_name: "ready" if table_name in existing_tables else "missing"
            for table_name in EXTENSION_TABLE_NAMES
        }
    )


def _build_extension_models(database: Any) -> list[type]:
    """
    Build all router and TradingAgents extension models for one database.
    """
    return (
        build_router_extension_models(database)
        + build_tradingagents_extension_models(database)
        + build_daily_review_extension_models(database)
        + build_seven_boll_extension_models(database)
    )


def _connect(database: Any) -> None:
    """
    Connect a Peewee database or compatible fake.
    """
    connect = getattr(database, "connect", None)
    if connect is not None:
        connect(reuse_if_open=True)


def _apply_additive_schema_upgrades(database: Any) -> None:
    """
    Add columns introduced after an extension table already exists.
    """
    execute_sql = getattr(database, "execute_sql", None)
    if execute_sql is not None:
        execute_sql(ADDITIVE_SCHEMA_UPGRADE_SQL)


def _table_names(models: list[type]) -> list[str]:
    """
    Return table names in create order.
    """
    return [model._meta.table_name for model in models]
