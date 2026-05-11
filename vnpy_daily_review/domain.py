"""
Domain objects for the vn.py daily market review app.
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from re import fullmatch
from typing import Any


def utc_now() -> datetime:
    """
    Return the current UTC timestamp.
    """
    return datetime.now(UTC)


def validate_symbol(symbol: str) -> None:
    """
    Validate a stock symbol used by the review module.
    """
    if not symbol:
        raise ValueError("symbol cannot be empty")
    if fullmatch(r"[0-9A-Za-z._-]{1,32}", symbol) is None:
        raise ValueError(f"invalid symbol: {symbol}")


def _validate_non_empty(value: str, field_name: str) -> None:
    if not value:
        raise ValueError(f"{field_name} cannot be empty")


def _validate_non_negative(value: int | Decimal, field_name: str) -> None:
    if value < 0:
        raise ValueError(f"{field_name} cannot be negative")


def _validate_timezone_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone aware")


def _validate_status(value: str, allowed: set[str], field_name: str = "status") -> None:
    if value not in allowed:
        raise ValueError(f"{field_name} must be one of {sorted(allowed)}")


def _validate_price_range(
    open_price: Decimal,
    high_price: Decimal,
    low_price: Decimal,
    close_price: Decimal,
) -> None:
    prices = [open_price, high_price, low_price, close_price]
    if any(price < 0 for price in prices):
        raise ValueError("prices cannot be negative")
    if high_price < max(open_price, low_price, close_price):
        raise ValueError("high_price must be at least open, low, and close")
    if low_price > min(open_price, high_price, close_price):
        raise ValueError("low_price must be at most open, high, and close")


@dataclass(frozen=True)
class ProviderFetchRecord:
    """
    Provider fetch quality record.
    """

    provider: str
    data_type: str
    trade_date: date
    status: str
    elapsed_ms: int
    row_count: int
    error_message: str | None
    request_params: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        _validate_non_empty(self.provider, "provider")
        _validate_non_empty(self.data_type, "data_type")
        _validate_status(self.status, {"success", "failed", "partial"})
        _validate_non_negative(self.elapsed_ms, "elapsed_ms")
        _validate_non_negative(self.row_count, "row_count")
        _validate_timezone_aware(self.created_at, "created_at")


@dataclass(frozen=True)
class DailyStockSnapshot:
    """
    One stock daily or latest spot snapshot.
    """

    symbol: str
    name: str
    trade_date: date
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    pct_change: Decimal
    volume: int
    amount: Decimal
    turnover_rate: Decimal | None
    is_limit_up: bool
    is_limit_down: bool
    provider: str
    sector: str | None = None

    def __post_init__(self) -> None:
        validate_symbol(self.symbol)
        _validate_non_empty(self.name, "name")
        _validate_non_empty(self.provider, "provider")
        _validate_price_range(
            self.open_price,
            self.high_price,
            self.low_price,
            self.close_price,
        )
        _validate_non_negative(self.volume, "volume")
        _validate_non_negative(self.amount, "amount")
        if self.turnover_rate is not None:
            _validate_non_negative(self.turnover_rate, "turnover_rate")


@dataclass(frozen=True)
class DailySectorSnapshot:
    """
    Industry or concept board snapshot.
    """

    sector_name: str
    trade_date: date
    pct_change: Decimal
    turnover_amount: Decimal
    advance_count: int
    decline_count: int
    leader_symbols: list[str]
    provider: str

    def __post_init__(self) -> None:
        _validate_non_empty(self.sector_name, "sector_name")
        _validate_non_empty(self.provider, "provider")
        _validate_non_negative(self.turnover_amount, "turnover_amount")
        _validate_non_negative(self.advance_count, "advance_count")
        _validate_non_negative(self.decline_count, "decline_count")
        for symbol in self.leader_symbols:
            validate_symbol(symbol)


@dataclass(frozen=True)
class DailyLimitUpSnapshot:
    """
    Limit-up ecosystem snapshot.
    """

    symbol: str
    trade_date: date
    board_count: int
    sealed: bool
    broken_count: int
    provider: str

    def __post_init__(self) -> None:
        validate_symbol(self.symbol)
        _validate_non_empty(self.provider, "provider")
        _validate_non_negative(self.board_count, "board_count")
        _validate_non_negative(self.broken_count, "broken_count")


@dataclass(frozen=True)
class DailyLhbSnapshot:
    """
    Dragon-tiger list capital snapshot.
    """

    symbol: str
    trade_date: date
    buy_amount: Decimal
    sell_amount: Decimal
    net_buy_amount: Decimal
    seat_tags: list[str]
    provider: str

    def __post_init__(self) -> None:
        validate_symbol(self.symbol)
        _validate_non_empty(self.provider, "provider")
        _validate_non_negative(self.buy_amount, "buy_amount")
        _validate_non_negative(self.sell_amount, "sell_amount")


@dataclass(frozen=True)
class DailyIntradayAnomaly:
    """
    Intraday anomaly such as a fast pull-up, dive, or seal-break.
    """

    symbol: str
    trade_date: date
    anomaly_type: str
    occurred_at: datetime
    strength_score: Decimal
    description: str
    provider: str

    def __post_init__(self) -> None:
        validate_symbol(self.symbol)
        _validate_non_empty(self.anomaly_type, "anomaly_type")
        _validate_non_empty(self.description, "description")
        _validate_non_empty(self.provider, "provider")
        _validate_timezone_aware(self.occurred_at, "occurred_at")
        _validate_non_negative(self.strength_score, "strength_score")


@dataclass(frozen=True)
class DailyEventCatalyst:
    """
    News, announcement, policy, or other event catalyst.
    """

    trade_date: date
    title: str
    source: str
    source_type: str
    published_at: datetime
    related_symbols: list[str]
    related_sectors: list[str]
    sentiment: str
    trust_score: Decimal
    content_hash: str

    def __post_init__(self) -> None:
        _validate_non_empty(self.title, "title")
        _validate_non_empty(self.source, "source")
        _validate_non_empty(self.source_type, "source_type")
        _validate_non_empty(self.content_hash, "content_hash")
        _validate_timezone_aware(self.published_at, "published_at")
        _validate_non_negative(self.trust_score, "trust_score")
        if self.trust_score > 1:
            raise ValueError("trust_score must be <= 1")
        for symbol in self.related_symbols:
            validate_symbol(symbol)


@dataclass(frozen=True)
class DailyReviewReport:
    """
    Generated daily market review report.
    """

    trade_date: date
    status: str
    title: str
    markdown: str
    structured: dict[str, Any]
    evidence_ids: list[str]
    model_name: str
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        _validate_status(self.status, {"completed", "partial", "failed", "no_data"})
        _validate_non_empty(self.title, "title")
        _validate_non_empty(self.markdown, "markdown")
        _validate_non_empty(self.model_name, "model_name")
        _validate_timezone_aware(self.created_at, "created_at")


@dataclass(frozen=True)
class DailyWatchPlanItem:
    """
    One next-day watch item.
    """

    symbol: str
    name: str
    role: str
    watch_action: str
    entry_condition: str
    avoid_condition: str
    position_rule: str
    evidence_ids: list[str]

    def __post_init__(self) -> None:
        validate_symbol(self.symbol)
        _validate_non_empty(self.name, "name")
        _validate_non_empty(self.role, "role")
        _validate_non_empty(self.watch_action, "watch_action")
        _validate_non_empty(self.entry_condition, "entry_condition")
        _validate_non_empty(self.avoid_condition, "avoid_condition")
        _validate_non_empty(self.position_rule, "position_rule")
