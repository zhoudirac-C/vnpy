from dataclasses import dataclass, field
from enum import Enum

from vnpy.trader.object import BarData


class QualityStatus(Enum):
    """
    Data quality report status.
    """

    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"


@dataclass
class QualityIssue:
    """
    Single data quality issue.
    """

    code: str
    message: str
    vt_symbol: str


@dataclass
class DataQualityReport:
    """
    Data quality report for provider output.
    """

    provider_name: str
    status: QualityStatus = QualityStatus.PASSED
    issues: list[QualityIssue] = field(default_factory=list)


def check_bar_data(provider_name: str, bars: list[BarData]) -> DataQualityReport:
    """
    Check OHLCV sanity for bar data.
    """
    report: DataQualityReport = DataQualityReport(provider_name=provider_name)
    seen_keys: set[tuple[str, str, object]] = set()

    for bar in bars:
        if bar.datetime is None:
            report.issues.append(
                QualityIssue("missing_datetime", "bar datetime is missing", bar.vt_symbol)
            )
        else:
            interval: str = bar.interval.value if bar.interval else ""
            key: tuple[str, str, object] = (bar.vt_symbol, interval, bar.datetime)
            if key in seen_keys:
                report.issues.append(
                    QualityIssue("duplicate_bar", "duplicate bar datetime", bar.vt_symbol)
                )
            else:
                seen_keys.add(key)

        if min(bar.open_price, bar.high_price, bar.low_price, bar.close_price) < 0:
            report.issues.append(
                QualityIssue("negative_price", "OHLC price contains negative value", bar.vt_symbol)
            )

        if bar.high_price < max(bar.open_price, bar.close_price, bar.low_price):
            report.issues.append(
                QualityIssue("invalid_high_price", "high price is lower than OHLC maximum", bar.vt_symbol)
            )

        if bar.low_price > min(bar.open_price, bar.close_price, bar.high_price):
            report.issues.append(
                QualityIssue("invalid_low_price", "low price is higher than OHLC minimum", bar.vt_symbol)
            )

        if bar.volume < 0:
            report.issues.append(
                QualityIssue("negative_volume", "volume is negative", bar.vt_symbol)
            )

        if bar.turnover < 0:
            report.issues.append(
                QualityIssue("negative_turnover", "turnover is negative", bar.vt_symbol)
            )

        extra: dict = bar.extra or {}
        if extra.get("adjustment") and not extra.get("provider_version"):
            report.issues.append(
                QualityIssue(
                    "missing_adjustment_version",
                    "adjusted data is missing provider version",
                    bar.vt_symbol,
                )
            )

    if report.issues:
        report.status = QualityStatus.FAILED

    return report
