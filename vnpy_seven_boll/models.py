"""
Peewee models for seven-rail Bollinger scan persistence.
"""

from typing import Any


SEVEN_BOLL_EXTENSION_TABLE_NAMES: tuple[str, ...] = (
    "seven_boll_scan_run",
    "seven_boll_scan_result",
)


def build_seven_boll_extension_models(database: Any) -> list[type]:
    """
    Build seven-boll scan models bound to a Peewee database.
    """
    from peewee import DateTimeField, FloatField, IntegerField, Model, TextField

    peewee_database = database

    class BaseSevenBollModel(Model):
        class Meta:
            database = peewee_database
            legacy_table_names = False

    class SevenBollScanRun(BaseSevenBollModel):
        scan_run_id = TextField(primary_key=True)
        scan_type = TextField(index=True)
        status = TextField(index=True)
        started_at = DateTimeField(index=True)
        finished_at = DateTimeField(index=True)
        total_symbols = IntegerField()
        scanned_symbols = IntegerField()
        skipped_symbols = IntegerField()
        buy_count = IntegerField()
        sell_count = IntegerField()
        errors_json = TextField()
        created_at = DateTimeField(null=True)

        class Meta:
            table_name = "seven_boll_scan_run"

    class SevenBollScanResult(BaseSevenBollModel):
        result_id = TextField(primary_key=True)
        scan_run_id = TextField(index=True)
        vt_symbol = TextField(index=True)
        name = TextField()
        concept = TextField(null=True)
        action = TextField(index=True)
        score = FloatField()
        buy_score = FloatField()
        sell_score = FloatField()
        signal_types_json = TextField()
        reasons_json = TextField()
        risks_json = TextField()
        close = FloatField()
        zscore = FloatField()
        bandwidth_percentile = FloatField(null=True)
        mid_slope = FloatField(null=True)
        rail_zone = TextField()
        regime = TextField(index=True)
        bar_datetime = DateTimeField(index=True)
        interval = TextField(index=True)
        boll_point_json = TextField(null=True)
        analysis_run_id = TextField(null=True)
        analysis_status = TextField(null=True)
        created_at = DateTimeField(null=True)

        class Meta:
            table_name = "seven_boll_scan_result"

    return [SevenBollScanRun, SevenBollScanResult]
