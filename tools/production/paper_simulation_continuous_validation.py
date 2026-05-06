from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from vnpy_router.peewee import connect_vnpy_postgres_adapter
from vnpy_router.storage import PostgresSnapshotReader
from vnpy_tradingagents.fusion import RuleSignal, SignalFusionService
from vnpy_tradingagents.gateway_policy import GatewayAiPolicy
from vnpy_tradingagents.monitoring import (
    PostgresReplayRunStatusStorage,
    ReplayRunStatusBuilder,
)
from vnpy_tradingagents.ops_storage import OpsHeartbeat, PostgresOpsStorage
from vnpy_tradingagents.paper_bridge import PaperAccountBridge, PaperAccountSnapshot
from vnpy_tradingagents.paper_smoke import PaperSmokeConfig, TradingAgentsPaperSmoke
from vnpy_tradingagents.performance_feedback import PostgresFeedbackStorage
from vnpy_tradingagents.policy import AiSignalPolicy
from vnpy_tradingagents.replay import IntradayReplayEngine, ReplayStep
from vnpy_tradingagents.risk import OrderIntent, PostgresDecisionAuditStorage, PreOrderDecisionService, RiskRuleSet
from vnpy_tradingagents.runtime import TradingAgentsMode, TradingAgentsRuntimeController
from vnpy_tradingagents.signals import IntradayAdvice, RatingSignal
from vnpy_tradingagents.storage import PostgresAgentStorage
from vnpy_tradingagents.worker import TradingAgentsWorkerRequest, TradingAgentsWorkerResponse


DEFAULT_ACTIONS: tuple[str, ...] = ("buy", "hold", "sell")


@dataclass(frozen=True)
class PaperSimulationContinuousConfig:
    """
    Configuration for one accelerated P16-T06 paper/simulation validation.
    """

    run_id: str
    vt_symbol: str = "600519.SSE"
    cycles: int = 3
    start: datetime = datetime(2024, 1, 3, 9, 35)
    interval_minutes: int = 30
    fill_price: float = 1688
    fill_volume: float = 100
    max_order_value: float = 1_000_000
    output_path: Path | None = None
    json_output_path: Path | None = None


@dataclass(frozen=True)
class PaperSimulationContinuousResult:
    """
    Auditable result for P16-T06 accelerated continuous validation.
    """

    success: bool
    run_id: str
    vt_symbol: str
    cycles: int
    worker_runs: int
    replay_status_saved: bool
    decision_audit_count: int
    trade_feedback_count: int
    performance_feedback_count: int
    ops_heartbeat_saved: bool
    agent_run_count: int
    agent_report_count: int
    rating_signal_count: int
    trade_intent_count: int
    final_position: float
    live_gateway_touched: bool
    notes: list[str]


class DeterministicCycleWorker:
    """
    Deterministic worker used to validate the paper/simulation loop without LLM cost.
    """

    def __init__(self, actions: tuple[str, ...] = DEFAULT_ACTIONS) -> None:
        self.actions: tuple[str, ...] = actions
        self.requests: list[TradingAgentsWorkerRequest] = []

    def run(self, request: TradingAgentsWorkerRequest) -> TradingAgentsWorkerResponse:
        """
        Return a stable worker response for the current cycle.
        """
        self.requests.append(request)
        cycle_index = len(self.requests) - 1
        action = self.actions[cycle_index % len(self.actions)]
        return TradingAgentsWorkerResponse(
            run_id=request.run_id,
            vt_symbol=request.vt_symbol,
            rating=_rating_for_action(action),
            confidence=0.72,
            report=f"P16-T06 deterministic paper simulation cycle {cycle_index + 1}: {action}",
            raw_state={
                "status": "ok",
                "model_provider": "deterministic",
                "model_name": "p16-t06-paper-simulation",
                "prompt_version": "p16-t06-validation-v1",
                "snapshot_ids": request.context.get("snapshot_ids", []),
                "cycle": cycle_index + 1,
                "mode": request.mode,
            },
            action=action,
            target_weight_hint=0.05 if action != "hold" else None,
            holding_period_hint="paper_validation",
            risk_notes="deterministic validation worker",
        )


def run_paper_simulation_continuous(
    config: PaperSimulationContinuousConfig,
) -> PaperSimulationContinuousResult:
    """
    Run an accelerated paper/simulation loop against vn.py PostgreSQL settings.
    """
    connection = connect_vnpy_postgres_adapter()
    reader = PostgresSnapshotReader(connection)
    agent_storage = PostgresAgentStorage(connection)
    feedback_storage = PostgresFeedbackStorage(connection)
    audit_storage = PostgresDecisionAuditStorage(connection)
    replay_storage = PostgresReplayRunStatusStorage(connection)
    ops_storage = PostgresOpsStorage(connection)

    runtime = TradingAgentsRuntimeController()
    paper_bridge = PaperAccountBridge(
        runtime=runtime,
        gateway_policy=GatewayAiPolicy(),
        feedback_storage=feedback_storage,
    )
    worker = DeterministicCycleWorker()
    smoke = TradingAgentsPaperSmoke(
        reader=reader,
        worker=worker,
        agent_storage=agent_storage,
        paper_bridge=paper_bridge,
    )

    cycle_results = []
    cycle_run_ids: list[str] = []
    for index in range(config.cycles):
        cycle_at = config.start + timedelta(minutes=index * config.interval_minutes)
        cycle_run_id = f"{config.run_id}-cycle-{index + 1}"
        cycle_run_ids.append(cycle_run_id)
        result = smoke.run(
            PaperSmokeConfig(
                vt_symbol=config.vt_symbol,
                start=config.start - timedelta(days=1),
                end=cycle_at,
                fill_price=config.fill_price,
                fill_volume=config.fill_volume,
                run_id=cycle_run_id,
                mode="paper_simulation_continuous",
                gateway_name="PAPER_SIM",
            )
        )
        cycle_results.append(result)
        if result.success:
            runtime.mark_success(cycle_run_id)

        paper_bridge.record_account_snapshot(
            PaperAccountSnapshot(
                vt_symbol=config.vt_symbol,
                as_of=cycle_at,
                portfolio_value=1_000_000 + (index + 1) * 100,
                previous_value=1_000_000 + index * 100,
                benchmark_return=0.0002 * index,
                turnover_rate=0.01 * (index + 1),
                max_drawdown=0.001 * index,
            )
        )

    replay_summary = _run_intraday_replay(config, audit_storage, cycle_run_ids)
    replay_status = ReplayRunStatusBuilder(clock=lambda: _last_cycle_at(config)).from_intraday_summary(
        config.run_id,
        replay_summary,
    )
    replay_storage.save_status(replay_status)

    runtime.heartbeat(_last_cycle_at(config))
    ops_storage.save_heartbeat(
        OpsHeartbeat(
            component=f"tradingagents-paper-simulation:{config.run_id}",
            heartbeat_at=_last_cycle_at(config),
            status="ready" if all(result.success for result in cycle_results) else "degraded",
            last_error=_first_error(cycle_results),
            data_latency_seconds=0,
            queue_backlog=0,
            degraded_sources=[],
            payload={
                "run_id": config.run_id,
                "cycle_run_ids": cycle_run_ids,
                "cycles": config.cycles,
                "worker_runs": len(worker.requests),
                "final_position": paper_bridge.positions.get(config.vt_symbol, 0),
                "replay_health": replay_status.health,
                "last_successful_run_id": runtime.state.last_successful_run_id,
            },
        )
    )

    counts = _load_counts(connection, config)
    result = PaperSimulationContinuousResult(
        success=_result_success(cycle_results, counts),
        run_id=config.run_id,
        vt_symbol=config.vt_symbol,
        cycles=config.cycles,
        worker_runs=len(worker.requests),
        replay_status_saved=bool(counts["replay_run_status"]),
        decision_audit_count=counts["decision_audit"],
        trade_feedback_count=counts["agent_trade_feedback"],
        performance_feedback_count=counts["agent_performance_feedback"],
        ops_heartbeat_saved=bool(counts["ops_heartbeat"]),
        agent_run_count=counts["agent_run"],
        agent_report_count=counts["agent_report"],
        rating_signal_count=counts["rating_signal"],
        trade_intent_count=counts["trade_intent"],
        final_position=float(paper_bridge.positions.get(config.vt_symbol, 0)),
        live_gateway_touched=False,
        notes=[
            "accelerated paper/simulation validation",
            "deterministic worker avoids repeated LLM token cost; P16-T05 covers real LLM worker connectivity",
            "long-running multi-day soak remains a separate operational validation window",
        ],
    )
    _write_outputs(config, result)
    return result


def _run_intraday_replay(
    config: PaperSimulationContinuousConfig,
    audit_storage: PostgresDecisionAuditStorage,
    cycle_run_ids: list[str],
):
    """
    Replay one strategy decision per paper cycle and persist decision_audit rows.
    """
    runtime = TradingAgentsRuntimeController()
    runtime.enable(mode=TradingAgentsMode.PAPER_ONLY)
    engine = IntradayReplayEngine(
        fusion_service=SignalFusionService(policy=AiSignalPolicy(runtime)),
        decision_service=PreOrderDecisionService(
            rules=RiskRuleSet(max_order_value=config.max_order_value),
            audit_storage=audit_storage,
            decision_id_factory=_sequence_id_factory(f"{config.run_id}-decision"),
        ),
        live=False,
    )
    steps = [
        _replay_step(config, index, cycle_run_id)
        for index, cycle_run_id in enumerate(cycle_run_ids)
    ]
    return engine.run(steps)


def _replay_step(
    config: PaperSimulationContinuousConfig,
    index: int,
    cycle_run_id: str,
) -> ReplayStep:
    """
    Build one replay step aligned with a paper cycle.
    """
    at = config.start + timedelta(minutes=index * config.interval_minutes)
    action = DEFAULT_ACTIONS[index % len(DEFAULT_ACTIONS)]
    volume = config.fill_volume if action != "hold" else 0
    return ReplayStep(
        at=at,
        rule_signal=RuleSignal(action=action, confidence=0.9, reason="p16_t06_validation"),
        rating=RatingSignal(
            vt_symbol=config.vt_symbol,
            rating=_rating_for_action(action),
            confidence=0.72,
            source_run_id=cycle_run_id,
        ),
        advice=IntradayAdvice(
            vt_symbol=config.vt_symbol,
            action=action,
            confidence=0.72,
            valid_until=at + timedelta(minutes=max(config.interval_minutes, 5)),
            source_run_id=cycle_run_id,
        ),
        intent=OrderIntent(
            vt_symbol=config.vt_symbol,
            action=action,
            price=config.fill_price,
            volume=volume,
        ),
    )


def _load_counts(connection: Any, config: PaperSimulationContinuousConfig) -> dict[str, int]:
    """
    Load validation evidence counts from PostgreSQL.
    """
    run_prefix = f"{config.run_id}%"
    decision_prefix = f"{config.run_id}-decision%"
    component = f"tradingagents-paper-simulation:{config.run_id}"
    start = config.start
    end = _last_cycle_at(config)
    queries: dict[str, tuple[str, Mapping[str, Any]]] = {
        "agent_run": (
            "select count(*) as count from agent_run where run_id like %(run_prefix)s",
            {"run_prefix": run_prefix},
        ),
        "agent_report": (
            "select count(*) as count from agent_report where run_id like %(run_prefix)s",
            {"run_prefix": run_prefix},
        ),
        "rating_signal": (
            "select count(*) as count from rating_signal where run_id like %(run_prefix)s",
            {"run_prefix": run_prefix},
        ),
        "trade_intent": (
            "select count(*) as count from trade_intent where run_id like %(run_prefix)s",
            {"run_prefix": run_prefix},
        ),
        "agent_trade_feedback": (
            "select count(*) as count from agent_trade_feedback where run_id like %(run_prefix)s",
            {"run_prefix": run_prefix},
        ),
        "agent_performance_feedback": (
            """
            select count(*) as count
            from agent_performance_feedback
            where vt_symbol = %(vt_symbol)s
              and as_of between %(start)s and %(end)s
            """,
            {"vt_symbol": config.vt_symbol, "start": start, "end": end},
        ),
        "decision_audit": (
            "select count(*) as count from decision_audit where decision_id like %(decision_prefix)s",
            {"decision_prefix": decision_prefix},
        ),
        "replay_run_status": (
            "select count(*) as count from replay_run_status where run_id = %(run_id)s",
            {"run_id": config.run_id},
        ),
        "ops_heartbeat": (
            "select count(*) as count from ops_heartbeat where component = %(component)s",
            {"component": component},
        ),
    }
    return {
        name: _fetch_count(connection, sql, params)
        for name, (sql, params) in queries.items()
    }


def _fetch_count(connection: Any, sql: str, params: Mapping[str, Any]) -> int:
    """
    Execute one count query.
    """
    cursor = connection.cursor()
    try:
        cursor.execute(sql, dict(params))
        row = cursor.fetchone() or {}
        return int(row.get("count") or 0)
    finally:
        cursor.close()


def _result_success(
    cycle_results: list[Any],
    counts: Mapping[str, int],
) -> bool:
    """
    Return whether every required table has validation evidence.
    """
    return (
        bool(cycle_results)
        and all(result.success for result in cycle_results)
        and counts["agent_run"] >= len(cycle_results)
        and counts["agent_report"] >= len(cycle_results)
        and counts["rating_signal"] >= len(cycle_results)
        and counts["trade_intent"] >= len(cycle_results)
        and counts["decision_audit"] >= len(cycle_results)
        and counts["agent_trade_feedback"] >= 1
        and counts["agent_performance_feedback"] >= len(cycle_results)
        and counts["replay_run_status"] >= 1
        and counts["ops_heartbeat"] >= 1
    )


def _write_outputs(
    config: PaperSimulationContinuousConfig,
    result: PaperSimulationContinuousResult,
) -> None:
    """
    Write Markdown and JSON validation evidence when requested.
    """
    if config.output_path:
        config.output_path.parent.mkdir(parents=True, exist_ok=True)
        config.output_path.write_text(_markdown(result), encoding="utf-8")

    if config.json_output_path:
        config.json_output_path.parent.mkdir(parents=True, exist_ok=True)
        config.json_output_path.write_text(
            json.dumps(asdict(result), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def _markdown(result: PaperSimulationContinuousResult) -> str:
    """
    Render validation result as Markdown.
    """
    status = "通过" if result.success else "未通过"
    lines = [
        "# P16-T06 Paper/Simulation 连续运行验证结果",
        "",
        f"- 结果：`{status}`",
        f"- run_id：`{result.run_id}`",
        f"- 标的：`{result.vt_symbol}`",
        f"- 周期数：`{result.cycles}`",
        f"- worker runs：`{result.worker_runs}`",
        f"- replay status：`{result.replay_status_saved}`",
        f"- decision audit：`{result.decision_audit_count}`",
        f"- trade feedback：`{result.trade_feedback_count}`",
        f"- performance feedback：`{result.performance_feedback_count}`",
        f"- ops heartbeat：`{result.ops_heartbeat_saved}`",
        f"- live_gateway_touched：`{result.live_gateway_touched}`",
        "",
        "## PostgreSQL 证据",
        "",
        "| 表 | 记录数 |",
        "| --- | ---: |",
        f"| agent_run | `{result.agent_run_count}` |",
        f"| agent_report | `{result.agent_report_count}` |",
        f"| rating_signal | `{result.rating_signal_count}` |",
        f"| trade_intent | `{result.trade_intent_count}` |",
        f"| decision_audit | `{result.decision_audit_count}` |",
        f"| agent_trade_feedback | `{result.trade_feedback_count}` |",
        f"| agent_performance_feedback | `{result.performance_feedback_count}` |",
        f"| replay_run_status | `{1 if result.replay_status_saved else 0}` |",
        f"| ops_heartbeat | `{1 if result.ops_heartbeat_saved else 0}` |",
        "",
        "## 备注",
        "",
    ]
    lines.extend(f"- {note}" for note in result.notes)
    return "\n".join(lines) + "\n"


def _sequence_id_factory(prefix: str) -> Callable[[], str]:
    """
    Build stable unique ids for one validation run.
    """
    counter = 0

    def next_id() -> str:
        nonlocal counter
        counter += 1
        return f"{prefix}-{counter}"

    return next_id


def _rating_for_action(action: str) -> str:
    """
    Convert action into a simple rating label.
    """
    normalized = action.strip().lower()
    if normalized in {"sell", "reduce", "decrease", "close_long"}:
        return "Sell"
    if normalized == "hold":
        return "Hold"
    return "Buy"


def _last_cycle_at(config: PaperSimulationContinuousConfig) -> datetime:
    """
    Return timestamp of the final cycle.
    """
    return config.start + timedelta(minutes=(config.cycles - 1) * config.interval_minutes)


def _first_error(cycle_results: list[Any]) -> str:
    """
    Return first smoke error if any.
    """
    for result in cycle_results:
        if not result.success:
            return result.error_message or result.error_type
    return ""


def parse_args() -> argparse.Namespace:
    """
    Parse CLI arguments.
    """
    parser = argparse.ArgumentParser(description="Run P16-T06 paper/simulation continuous validation")
    parser.add_argument("--run-id", default=f"p16-t06-{datetime.now().strftime('%Y%m%d%H%M%S')}")
    parser.add_argument("--vt-symbol", default="600519.SSE")
    parser.add_argument("--cycles", type=int, default=3)
    parser.add_argument("--start", default="2024-01-03T09:35:00")
    parser.add_argument("--interval-minutes", type=int, default=30)
    parser.add_argument("--fill-price", type=float, default=1688)
    parser.add_argument("--fill-volume", type=float, default=100)
    parser.add_argument("--max-order-value", type=float, default=1_000_000)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json-output", type=Path)
    return parser.parse_args()


def main() -> int:
    """
    CLI entrypoint.
    """
    args = parse_args()
    config = PaperSimulationContinuousConfig(
        run_id=args.run_id,
        vt_symbol=args.vt_symbol,
        cycles=args.cycles,
        start=datetime.fromisoformat(args.start),
        interval_minutes=args.interval_minutes,
        fill_price=args.fill_price,
        fill_volume=args.fill_volume,
        max_order_value=args.max_order_value,
        output_path=args.output,
        json_output_path=args.json_output,
    )
    result = run_paper_simulation_continuous(config)
    print(json.dumps(asdict(result), ensure_ascii=False, sort_keys=True))
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
