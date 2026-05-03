import csv
import json
from dataclasses import dataclass
from io import StringIO
from typing import Any

from .risk import DecisionAuditRecord


@dataclass(frozen=True)
class AuditExportRecord:
    """
    One complete gray-run audit export row.
    """

    audit: DecisionAuditRecord
    rule_signal: dict[str, Any]
    order_intent: dict[str, Any]
    simulated_trade_id: str = ""
    live_trade_id: str = ""


def export_audit_jsonl(records: list[AuditExportRecord]) -> str:
    """
    Export audit records as JSON Lines.
    """
    return "".join(
        json.dumps(_record_to_row(record), ensure_ascii=False, sort_keys=True) + "\n"
        for record in records
    )


def export_audit_csv(records: list[AuditExportRecord]) -> str:
    """
    Export audit records as CSV.
    """
    output = StringIO()
    fieldnames = list(_record_to_row(records[0]).keys()) if records else _fieldnames()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for record in records:
        row = _record_to_row(record)
        row["ai_source_run_ids"] = json.dumps(row["ai_source_run_ids"], ensure_ascii=False)
        row["rule_signal"] = json.dumps(row["rule_signal"], ensure_ascii=False, sort_keys=True)
        row["order_intent"] = json.dumps(row["order_intent"], ensure_ascii=False, sort_keys=True)
        writer.writerow(row)
    return output.getvalue()


def _record_to_row(record: AuditExportRecord) -> dict[str, Any]:
    """"""
    audit: DecisionAuditRecord = record.audit
    return {
        "decision_id": audit.decision_id,
        "created_at": audit.created_at.isoformat(),
        "vt_symbol": audit.vt_symbol,
        "action": audit.action,
        "rule_confidence": audit.rule_confidence,
        "ai_decision": audit.ai_decision,
        "ai_used": audit.ai_used,
        "ai_source_run_ids": audit.ai_source_run_ids,
        "risk_decision": audit.risk_decision.value,
        "risk_failed_rule": audit.risk_failed_rule,
        "risk_reason": audit.risk_reason,
        "rule_signal": record.rule_signal,
        "order_intent": record.order_intent,
        "simulated_trade_id": record.simulated_trade_id,
        "live_trade_id": record.live_trade_id,
    }


def _fieldnames() -> list[str]:
    """"""
    return [
        "decision_id",
        "created_at",
        "vt_symbol",
        "action",
        "rule_confidence",
        "ai_decision",
        "ai_used",
        "ai_source_run_ids",
        "risk_decision",
        "risk_failed_rule",
        "risk_reason",
        "rule_signal",
        "order_intent",
        "simulated_trade_id",
        "live_trade_id",
    ]
