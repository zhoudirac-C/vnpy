"""
Global setting of the trading platform.
"""

from logging import INFO
from tzlocal import get_localzone_name

from .utility import load_json


SETTINGS: dict = {
    "font.family": "微软雅黑",
    "font.size": 12,

    "log.active": True,
    "log.level": INFO,
    "log.console": True,
    "log.file": True,

    "email.server": "smtp.qq.com",
    "email.port": 465,
    "email.username": "",
    "email.password": "",
    "email.sender": "",
    "email.receiver": "",

    "datafeed.name": "",
    "datafeed.username": "",
    "datafeed.password": "",
    "router.providers": "local_file,akshare",
    "router.local_path": "",
    "tradingagents.llm_provider": "openai",
    "tradingagents.api_key_env_var": "OPENAI_API_KEY",
    "tradingagents.worker_factory": "vnpy_tradingagents.tradingagents_factory:build",
    "tradingagents.signal_strategy_enabled": False,
    "tradingagents.live_enabled": False,
    "tradingagents.model": "gpt-4o-mini",
    "tradingagents.backend_url": "",
    "tradingagents.thinking_type": "auto",
    "tradingagents.timeout_seconds": 1800,
    "tradingagents.intraday_thinking_type": "disabled",
    "tradingagents.intraday_timeout_seconds": 360,
    "tradingagents.long_horizon_thinking_type": "enabled",
    "tradingagents.long_horizon_timeout_seconds": 2700,
    "tradingagents.replay_thinking_type": "enabled",
    "tradingagents.replay_timeout_seconds": 2700,
    "tradingagents.max_retries": 1,
    "tradingagents.max_completion_tokens": 1536,
    "tradingagents.checkpoint_dir": ".tradingagents/checkpoints",
    "news.ingestion.enabled": True,
    "news.ingestion.providers": "cninfo_announcement,sse_announcement,gdelt_global_news,akshare_stock_news",
    "news.ingestion.interval_seconds": 900,
    "news.ingestion.lookback_minutes": 1440,
    "news.ingestion.max_items_per_symbol": 50,
    "news.ingestion.symbols": "",
    "news.ingestion.symbol_source": "auto",
    "news.ingestion.symbol_batch_size": 50,
    "news.ingestion.local_path": "",
    "news.ingestion.akshare.endpoints": "stock_news_em,stock_info_global_cls",
    "news.ingestion.gdelt_query": "China economy OR China market OR tariff OR exports",
    "news.ingestion.timeout_seconds": 30,
    "news.ingestion.enabled_in_live": False,
    "financial.ingestion.enabled": True,
    "financial.ingestion.providers": (
        "akshare_sina,akshare_eastmoney,akshare_indicator,cninfo_report,exchange_report"
    ),
    "financial.ingestion.symbols": "",
    "financial.ingestion.catalog_path": "",
    "financial.ingestion.lookback_years": 5,
    "financial.ingestion.schedule": "20:30",
    "financial.ingestion.morning_retry_enabled": True,
    "financial.ingestion.morning_retry_schedule": "08:30",
    "financial.ingestion.full_market_backfill_enabled": False,
    "financial.ingestion.max_workers": 2,
    "financial.ingestion.request_timeout": 30,
    "financial.ingestion.symbol_batch_size": 20,
    "financial.context.max_statement_periods": 4,
    "financial.context.require_announced_only": True,
    "news.entity.catalog_path": "",
    "news.entity.refresh_interval_hours": 24,
    "news.filter.min_trust_score": 0.70,
    "news.filter.min_link_confidence": 0.75,
    "news.filter.max_items_per_symbol": 20,
    "news.filter.allowed_event_types": "announcement,earnings,regulatory,buyback,holding_change,industry,macro",
    "news.filter.intraday_window_days": 3,
    "news.filter.research_window_days": 180,
    "news.llm_classifier.enabled": False,
    "news.llm_classifier.model": "glm-4.7",
    "news.llm_classifier.api_key_env_var": "ZHIPU_API_KEY",
    "news.llm_classifier.intraday_thinking_type": "disabled",
    "news.llm_classifier.scheduled_thinking_type": "disabled",
    "news.llm_classifier.research_thinking_type": "enabled",
    "news.llm_classifier.replay_thinking_type": "enabled",
    "news.llm_classifier.batch_thinking_type": "enabled",
    "news.llm_classifier.fast_timeout_seconds": 360,
    "news.llm_classifier.deep_timeout_seconds": 2700,
    "news.llm_classifier.min_confidence": 0.65,
    "seven_boll.scan.enabled": True,
    "seven_boll.scan.schedule": "11:35,15:05",

    "database.timezone": get_localzone_name(),
    "database.name": "sqlite",
    "database.database": "database.db",
    "database.host": "",
    "database.port": 0,
    "database.user": "",
    "database.password": ""
}


# Load global setting from json file.
SETTING_FILENAME: str = "vt_setting.json"
SETTINGS.update(load_json(SETTING_FILENAME))
