from dataclasses import dataclass
from datetime import datetime

from .gateway_policy import GatewayAccountMode, GatewayProfile
from .paper_bridge import PaperAccountBridge, SimulatedTrade
from .runner_smoke import RunnerSmokeConfig, TradingAgentsRunnerSmoke, Worker, Storage
from .toolkit import SnapshotReader
from .worker import TradingAgentsWorkerRequest, TradingAgentsWorkerResponse


@dataclass(frozen=True)
class PaperSmokeConfig:
    """
    One end-to-end paper smoke run.
    """

    vt_symbol: str
    start: datetime
    end: datetime
    fill_price: float
    fill_volume: float
    run_id: str = ""
    mode: str = "paper_smoke"
    gateway_name: str = "PAPER"


@dataclass(frozen=True)
class PaperSmokeResult:
    """
    Paper smoke result.
    """

    success: bool
    request: TradingAgentsWorkerRequest | None = None
    response: TradingAgentsWorkerResponse | None = None
    live_gateway_touched: bool = False
    error_type: str = ""
    error_message: str = ""


class TradingAgentsPaperSmoke:
    """
    Run snapshot -> worker -> signal persistence -> paper fill -> feedback once.
    """

    def __init__(
        self,
        reader: SnapshotReader,
        worker: Worker,
        agent_storage: Storage,
        paper_bridge: PaperAccountBridge,
    ) -> None:
        """"""
        self.runner_smoke: TradingAgentsRunnerSmoke = TradingAgentsRunnerSmoke(
            reader=reader,
            worker=worker,
            storage=agent_storage,
        )
        self.paper_bridge: PaperAccountBridge = paper_bridge

    def run(self, config: PaperSmokeConfig) -> PaperSmokeResult:
        """
        Execute one paper-only smoke run.
        """
        self.paper_bridge.configure(
            GatewayProfile(
                gateway_name=config.gateway_name,
                account_mode=GatewayAccountMode.SIMULATION,
            ),
            ai_enabled=True,
        )
        smoke_result = self.runner_smoke.run(
            RunnerSmokeConfig(
                vt_symbol=config.vt_symbol,
                start=config.start,
                end=config.end,
                mode=config.mode,
                run_id=config.run_id,
            )
        )
        if not smoke_result.success or smoke_result.response is None:
            return PaperSmokeResult(
                success=False,
                request=smoke_result.request,
                error_type=smoke_result.error_type,
                error_message=smoke_result.error_message,
            )

        response = smoke_result.response
        self.paper_bridge.record_fill(
            SimulatedTrade(
                source_run_id=response.run_id,
                vt_symbol=response.vt_symbol,
                trade_date=smoke_result.request.trade_date if smoke_result.request else "",
                action=response.action,
                volume=config.fill_volume,
                price=config.fill_price,
                slippage=0,
                pnl=0,
            )
        )
        return PaperSmokeResult(
            success=True,
            request=smoke_result.request,
            response=response,
            live_gateway_touched=False,
        )
