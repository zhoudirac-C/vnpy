"""
Peewee models for TradingAgents extension tables.
"""

from typing import Any


TRADINGAGENTS_EXTENSION_TABLE_NAMES: tuple[str, ...] = (
    "agent_run",
    "agent_report",
    "rating_signal",
    "trade_intent",
    "intraday_advice",
    "ai_runtime_state",
    "decision_audit",
    "agent_performance_feedback",
    "agent_trade_feedback",
    "replay_run_status",
    "ops_heartbeat",
    "intraday_snapshot",
)


def build_tradingagents_extension_models(database: Any) -> list[type]:
    """
    Build Peewee models bound to the provided database.
    """
    from peewee import (
        BooleanField,
        CompositeKey,
        DateField,
        DateTimeField,
        FloatField,
        IntegerField,
        Model,
        SQL,
        TextField,
    )
    from playhouse.postgres_ext import BinaryJSONField

    peewee_database = database

    class BaseExtensionModel(Model):
        class Meta:
            database = peewee_database
            legacy_table_names = False

    class AgentRun(BaseExtensionModel):
        run_id = TextField(primary_key=True)
        vt_symbol = TextField()
        trade_date = DateField()
        mode = TextField()
        model_provider = TextField(null=True)
        model_name = TextField(null=True)
        prompt_version = TextField(null=True)
        snapshot_ids = BinaryJSONField(null=True)
        context = BinaryJSONField()
        created_at = DateTimeField(constraints=[SQL("DEFAULT now()")], null=True)

        class Meta:
            table_name = "agent_run"

    class AgentReport(BaseExtensionModel):
        run_id = TextField(primary_key=True)
        vt_symbol = TextField()
        report = TextField()
        raw_state = BinaryJSONField()
        error_message = TextField(null=True)
        created_at = DateTimeField(constraints=[SQL("DEFAULT now()")], null=True)

        class Meta:
            table_name = "agent_report"

    class RatingSignal(BaseExtensionModel):
        run_id = TextField(primary_key=True)
        vt_symbol = TextField()
        trade_date = DateField()
        rating = TextField()
        confidence = FloatField()
        created_at = DateTimeField(constraints=[SQL("DEFAULT now()")], null=True)

        class Meta:
            table_name = "rating_signal"

    class TradeIntent(BaseExtensionModel):
        run_id = TextField(primary_key=True)
        vt_symbol = TextField()
        trade_date = DateField()
        action = TextField()
        target_weight_hint = FloatField(null=True)
        holding_period_hint = TextField(null=True)
        risk_notes = TextField(null=True)
        created_at = DateTimeField(constraints=[SQL("DEFAULT now()")], null=True)

        class Meta:
            table_name = "trade_intent"

    class IntradayAdvice(BaseExtensionModel):
        run_id = TextField(primary_key=True)
        vt_symbol = TextField()
        action = TextField()
        confidence = FloatField()
        valid_until = DateTimeField()
        generated_at = DateTimeField(constraints=[SQL("DEFAULT now()")], null=True)

        class Meta:
            table_name = "intraday_advice"

    class AiRuntimeState(BaseExtensionModel):
        state_id = TextField(primary_key=True)
        enabled = BooleanField()
        mode = TextField()
        live_enabled = BooleanField()
        manual_takeover = BooleanField()
        signal_status = TextField()
        disabled_reason = TextField(null=True)
        last_heartbeat_at = DateTimeField(null=True)
        last_successful_run_id = TextField(null=True)
        updated_at = DateTimeField(constraints=[SQL("DEFAULT now()")], null=True)

        class Meta:
            table_name = "ai_runtime_state"

    class DecisionAudit(BaseExtensionModel):
        decision_id = TextField(primary_key=True)
        created_at = DateTimeField()
        vt_symbol = TextField()
        action = TextField()
        price = FloatField()
        volume = FloatField()
        rule_confidence = FloatField()
        ai_decision = TextField()
        ai_used = BooleanField()
        ai_source_run_ids = BinaryJSONField()
        risk_decision = TextField()
        risk_failed_rule = TextField(null=True)
        risk_reason = TextField(null=True)

        class Meta:
            table_name = "decision_audit"

    class AgentPerformanceFeedback(BaseExtensionModel):
        vt_symbol = TextField()
        as_of = DateTimeField()
        portfolio_return = FloatField()
        benchmark_return = FloatField()
        alpha = FloatField()
        turnover_rate = FloatField()
        max_drawdown = FloatField()
        payload = BinaryJSONField()
        created_at = DateTimeField(constraints=[SQL("DEFAULT now()")], null=True)

        class Meta:
            table_name = "agent_performance_feedback"
            primary_key = CompositeKey("vt_symbol", "as_of")

    class AgentTradeFeedback(BaseExtensionModel):
        run_id = TextField()
        vt_symbol = TextField()
        trade_date = DateField()
        action = TextField()
        filled_volume = FloatField()
        avg_price = FloatField()
        slippage = FloatField()
        pnl = FloatField()
        payload = BinaryJSONField()
        created_at = DateTimeField(constraints=[SQL("DEFAULT now()")], null=True)

        class Meta:
            table_name = "agent_trade_feedback"
            primary_key = CompositeKey("run_id", "vt_symbol", "trade_date")

    class ReplayRunStatus(BaseExtensionModel):
        run_id = TextField(primary_key=True)
        mode = TextField()
        generated_at = DateTimeField()
        health = TextField()
        payload = BinaryJSONField()
        created_at = DateTimeField(constraints=[SQL("DEFAULT now()")], null=True)

        class Meta:
            table_name = "replay_run_status"

    class OpsHeartbeat(BaseExtensionModel):
        component = TextField(primary_key=True)
        heartbeat_at = DateTimeField()
        status = TextField()
        last_error = TextField(null=True)
        data_latency_seconds = FloatField(null=True)
        queue_backlog = IntegerField(null=True)
        degraded_sources = BinaryJSONField(null=True)
        payload = BinaryJSONField(null=True)
        updated_at = DateTimeField(constraints=[SQL("DEFAULT now()")], null=True)

        class Meta:
            table_name = "ops_heartbeat"

    class IntradaySnapshot(BaseExtensionModel):
        vt_symbol = TextField()
        generated_at = DateTimeField()
        interval = TextField()
        context = BinaryJSONField()
        created_at = DateTimeField(constraints=[SQL("DEFAULT now()")], null=True)

        class Meta:
            table_name = "intraday_snapshot"
            primary_key = CompositeKey("vt_symbol", "generated_at")

    return [
        AgentRun,
        AgentReport,
        RatingSignal,
        TradeIntent,
        IntradayAdvice,
        AiRuntimeState,
        DecisionAudit,
        AgentPerformanceFeedback,
        AgentTradeFeedback,
        ReplayRunStatus,
        OpsHeartbeat,
        IntradaySnapshot,
    ]
