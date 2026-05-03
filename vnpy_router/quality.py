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

    for bar in bars:
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

    if report.issues:
        report.status = QualityStatus.FAILED

    return report
