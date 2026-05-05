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
    "tradingagents.model": "gpt-4o-mini",
    "tradingagents.timeout_seconds": 120,
    "tradingagents.max_retries": 1,
    "tradingagents.checkpoint_dir": ".tradingagents/checkpoints",

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
