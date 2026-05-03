from pathlib import Path

from vnpy.trader.app import BaseApp

from .engine import TradingAgentsEngine


APP_NAME: str = "TradingAgents"


class TradingAgentsApp(BaseApp):
    """
    TradingAgents control app metadata for VeighNa.
    """

    app_name: str = APP_NAME
    app_module: str = __module__
    app_path: Path = Path(__file__).parent
    display_name: str = "TradingAgents"
    engine_class: type[TradingAgentsEngine] = TradingAgentsEngine
    widget_name: str = "TradingAgentsWidget"
    icon_name: str = ""
