"""
Peewee models for daily market review persistence.
"""

from typing import Any


DAILY_REVIEW_EXTENSION_TABLE_NAMES: tuple[str, ...] = (
    "daily_review_report",
    "daily_review_evidence",
    "daily_watch_plan",
    "daily_watch_plan_item",
    "daily_review_model_audit",
)


def build_daily_review_extension_models(database: Any) -> list[type]:
    """
    Build daily review models bound to a Peewee database.
    """
    from peewee import DateField, DateTimeField, Model, SQL, TextField
    from playhouse.postgres_ext import BinaryJSONField

    peewee_database = database

    class BaseDailyReviewModel(Model):
        class Meta:
            database = peewee_database
            legacy_table_names = False

    class DailyReviewReport(BaseDailyReviewModel):
        report_id = TextField(primary_key=True)
        trade_date = DateField(index=True)
        status = TextField(index=True)
        title = TextField()
        markdown = TextField()
        structured = BinaryJSONField()
        evidence_ids = BinaryJSONField()
        model_name = TextField()
        created_at = DateTimeField(constraints=[SQL("DEFAULT now()")], index=True)

        class Meta:
            table_name = "daily_review_report"

    class DailyReviewEvidence(BaseDailyReviewModel):
        evidence_id = TextField(primary_key=True)
        trade_date = DateField(index=True)
        source = TextField()
        source_type = TextField(index=True)
        content = TextField()
        trust_score = TextField()
        data_time = DateTimeField(index=True)
        content_hash = TextField(index=True)
        metadata = BinaryJSONField()
        created_at = DateTimeField(constraints=[SQL("DEFAULT now()")], index=True)

        class Meta:
            table_name = "daily_review_evidence"

    class DailyWatchPlan(BaseDailyReviewModel):
        plan_id = TextField(primary_key=True)
        trade_date = DateField(index=True)
        source_report_id = TextField(index=True)
        status = TextField(index=True)
        summary = TextField()
        created_at = DateTimeField(constraints=[SQL("DEFAULT now()")], index=True)

        class Meta:
            table_name = "daily_watch_plan"

    class DailyWatchPlanItem(BaseDailyReviewModel):
        item_id = TextField(primary_key=True)
        plan_id = TextField(index=True)
        symbol = TextField(index=True)
        name = TextField()
        role = TextField(index=True)
        watch_action = TextField()
        entry_condition = TextField()
        avoid_condition = TextField()
        position_rule = TextField()
        evidence_ids = BinaryJSONField()
        created_at = DateTimeField(constraints=[SQL("DEFAULT now()")], index=True)

        class Meta:
            table_name = "daily_watch_plan_item"

    class DailyReviewModelAudit(BaseDailyReviewModel):
        audit_id = TextField(primary_key=True)
        report_id = TextField(index=True)
        trade_date = DateField(index=True)
        stage = TextField(index=True)
        provider = TextField()
        model_name = TextField()
        status = TextField(index=True)
        payload = BinaryJSONField()
        created_at = DateTimeField(constraints=[SQL("DEFAULT now()")], index=True)

        class Meta:
            table_name = "daily_review_model_audit"

    return [
        DailyReviewReport,
        DailyReviewEvidence,
        DailyWatchPlan,
        DailyWatchPlanItem,
        DailyReviewModelAudit,
    ]
