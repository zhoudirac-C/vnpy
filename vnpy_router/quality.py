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
    field: str = ""
    provider_name: str = ""
    compared_provider_name: str = ""
    provider_value: object = None
    compared_value: object = None
    tolerance: float | None = None
    provider_version: str = ""
    compared_provider_version: str = ""


@dataclass
class DataQualityReport:
    """
    Data quality report for provider output.
    """

    provider_name: str
    status: QualityStatus = QualityStatus.PASSED
    issues: list[QualityIssue] = field(default_factory=list)
    compared_provider_name: str = ""
    compared_bar_count: int = 0


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


def compare_bar_provider_outputs(
    provider_name: str,
    provider_bars: list[BarData],
    compared_provider_name: str,
    compared_bars: list[BarData],
    price_tolerance: float = 0.01,
    volume_tolerance: float = 0,
) -> DataQualityReport:
    """
    Compare OHLCV values from two providers for the same symbol/date.
    """
    report = DataQualityReport(
        provider_name=provider_name,
        compared_provider_name=compared_provider_name,
    )
    compared_index: dict[tuple[str, str, object], BarData] = {
        _bar_key(bar): bar for bar in compared_bars
    }

    for provider_bar in provider_bars:
        compared_bar = compared_index.get(_bar_key(provider_bar))
        if compared_bar is None:
            report.issues.append(
                QualityIssue(
                    code="provider_bar_missing",
                    message="compared provider is missing the same bar",
                    vt_symbol=provider_bar.vt_symbol,
                    provider_name=provider_name,
                    compared_provider_name=compared_provider_name,
                    provider_version=_provider_version(provider_bar),
                )
            )
            continue

        report.compared_bar_count += 1
        for field_name, tolerance in _comparison_fields(price_tolerance, volume_tolerance):
            provider_value = getattr(provider_bar, field_name)
            compared_value = getattr(compared_bar, field_name)
            if abs(float(provider_value) - float(compared_value)) <= tolerance:
                continue
            report.issues.append(
                QualityIssue(
                    code="provider_field_mismatch",
                    message=f"{field_name} differs between providers",
                    vt_symbol=provider_bar.vt_symbol,
                    field=field_name,
                    provider_name=provider_name,
                    compared_provider_name=compared_provider_name,
                    provider_value=provider_value,
                    compared_value=compared_value,
                    tolerance=tolerance,
                    provider_version=_provider_version(provider_bar),
                    compared_provider_version=_provider_version(compared_bar),
                )
            )

    if report.issues:
        report.status = QualityStatus.FAILED if _has_missing_bar(report) else QualityStatus.WARNING

    return report


def _comparison_fields(
    price_tolerance: float,
    volume_tolerance: float,
) -> tuple[tuple[str, float], ...]:
    """
    Return fields and tolerances for provider cross-checks.
    """
    return (
        ("open_price", price_tolerance),
        ("high_price", price_tolerance),
        ("low_price", price_tolerance),
        ("close_price", price_tolerance),
        ("volume", volume_tolerance),
        ("turnover", volume_tolerance),
    )


def _bar_key(bar: BarData) -> tuple[str, str, object]:
    """
    Return the comparison key for one bar.
    """
    interval: str = bar.interval.value if bar.interval else ""
    return bar.vt_symbol, interval, bar.datetime


def _provider_version(bar: BarData) -> str:
    """
    Return provider version from bar metadata.
    """
    extra: dict = bar.extra or {}
    return str(extra.get("provider_version") or "")


def _has_missing_bar(report: DataQualityReport) -> bool:
    """
    Return whether a report contains missing compared bars.
    """
    return any(issue.code == "provider_bar_missing" for issue in report.issues)
