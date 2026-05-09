from pathlib import Path

from vnpy.trader.app import BaseApp

from .engine import TradingAgentsEngine


APP_NAME: str = "TradingAgents"


class TradingAgentsApp(BaseApp):
    """
    TradingAgents control app metadata for VeighNa.
    """

    app_name: str = APP_NAME
    app_module: str = "vnpy_tradingagents"
    app_path: Path = Path(__file__).parent
    display_name: str = "TradingAgents分析管理"
    engine_class: type[TradingAgentsEngine] = TradingAgentsEngine
    widget_name: str = "TradingAgentsWidget"
    icon_name: str = str(Path(__file__).parent / "ui" / "tradingagents_analysis.svg")
    show_on_toolbar: bool = True
