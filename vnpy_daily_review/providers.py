"""
Data providers for the vn.py daily market review service.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from importlib import import_module
from time import perf_counter
from typing import Any

from vnpy.trader.engine import MainEngine

from .domain import (
    DailyEventCatalyst,
    DailyIntradayAnomaly,
    DailyLhbSnapshot,
    DailyLimitUpSnapshot,
    DailySectorSnapshot,
    DailyStockSnapshot,
)
from .service import DailyReviewDataBundle


class VnpyAkshareDailyReviewProvider:
    """
    Provider that first reuses live ticks in vn.py and then falls back to AKShare.
    """

    def __init__(
        self,
        main_engine: MainEngine,
        event_storage: Any | None = None,
        financial_storage: Any | None = None,
    ) -> None:
        self._main_engine = main_engine
        self._event_storage = event_storage
        self._financial_storage = financial_storage

    def load_data_bundle(self, trade_date: date) -> DailyReviewDataBundle:
        """
        Load current market review data.
        """
        provider_records: list[dict[str, Any]] = []
        stocks = self._load_vnpy_ticks(trade_date, provider_records)
        if not stocks:
            stocks = self._load_akshare_stocks(trade_date, provider_records)
        sectors = self._load_akshare_sectors(trade_date, provider_records)
        limit_ups = self._load_akshare_limit_ups(trade_date, provider_records)
        lhb = self._load_akshare_lhb(trade_date, provider_records)
        events = self._load_postgres_events(trade_date, provider_records)
        financial_contexts = self._load_financial_contexts(
            trade_date,
            stocks,
            provider_records,
        )
        intraday_anomalies = _intraday_anomalies_from_stocks(stocks)
        quality_warnings = []
        if not sectors:
            quality_warnings.append("sector_provider_empty")
        if not limit_ups:
            quality_warnings.append("limit_up_provider_empty")
        if not lhb:
            quality_warnings.append("lhb_provider_empty")
        if self._event_storage is not None and not events:
            quality_warnings.append("news_event_storage_empty")
        if self._financial_storage is not None and not financial_contexts:
            quality_warnings.append("financial_context_empty")

        return DailyReviewDataBundle(
            trade_date=trade_date,
            stocks=stocks,
            sectors=sectors,
            limit_ups=limit_ups,
            lhb=lhb,
            intraday_anomalies=intraday_anomalies,
            events=events,
            financial_contexts=financial_contexts,
            provider_records=provider_records,
            quality_warnings=quality_warnings,
        )

    def _load_vnpy_ticks(
        self,
        trade_date: date,
        provider_records: list[dict[str, Any]],
    ) -> list[DailyStockSnapshot]:
        started_at = perf_counter()
        try:
            ticks = list(self._main_engine.get_all_ticks())
        except Exception as exc:
            provider_records.append(
                _record("vnpy_main_engine", "stock_snapshot", "failed", 0, started_at, str(exc))
            )
            return []

        snapshots: list[DailyStockSnapshot] = []
        for tick in ticks:
            snapshot = _snapshot_from_tick(tick, trade_date)
            if snapshot is not None:
                snapshots.append(snapshot)
        provider_records.append(
            _record("vnpy_main_engine", "stock_snapshot", "success", len(snapshots), started_at)
        )
        return snapshots

    def _load_akshare_stocks(
        self,
        trade_date: date,
        provider_records: list[dict[str, Any]],
    ) -> list[DailyStockSnapshot]:
        started_at = perf_counter()
        try:
            akshare = import_module("akshare")
            frame = akshare.stock_zh_a_spot_em()
            rows = _records_from_frame(frame)
            snapshots = [_snapshot_from_akshare_row(row, trade_date) for row in rows]
            snapshots = [snapshot for snapshot in snapshots if snapshot is not None]
            provider_records.append(
                _record("akshare", "stock_snapshot", "success", len(snapshots), started_at)
            )
            return snapshots
        except Exception as exc:
            provider_records.append(
                _record("akshare", "stock_snapshot", "failed", 0, started_at, str(exc))
            )
            return []

    def _load_akshare_sectors(
        self,
        trade_date: date,
        provider_records: list[dict[str, Any]],
    ) -> list[DailySectorSnapshot]:
        started_at = perf_counter()
        try:
            akshare = import_module("akshare")
            frame = akshare.stock_board_industry_name_em()
            rows = _records_from_frame(frame)
            sectors = [_sector_from_akshare_row(row, trade_date) for row in rows]
            sectors = [sector for sector in sectors if sector is not None]
            provider_records.append(
                _record("akshare", "sector_snapshot", "success", len(sectors), started_at)
            )
            return sectors
        except Exception as exc:
            provider_records.append(
                _record("akshare", "sector_snapshot", "failed", 0, started_at, str(exc))
            )
            return []

    def _load_akshare_limit_ups(
        self,
        trade_date: date,
        provider_records: list[dict[str, Any]],
    ) -> list[DailyLimitUpSnapshot]:
        started_at = perf_counter()
        try:
            akshare = import_module("akshare")
            frame = akshare.stock_zt_pool_em(date=trade_date.strftime("%Y%m%d"))
            rows = _records_from_frame(frame)
            limit_ups = [_limit_up_from_akshare_row(row, trade_date) for row in rows]
            limit_ups = [item for item in limit_ups if item is not None]
            provider_records.append(
                _record("akshare", "limit_up_snapshot", "success", len(limit_ups), started_at)
            )
            return limit_ups
        except Exception as exc:
            provider_records.append(
                _record("akshare", "limit_up_snapshot", "failed", 0, started_at, str(exc))
            )
            return []

    def _load_akshare_lhb(
        self,
        trade_date: date,
        provider_records: list[dict[str, Any]],
    ) -> list[DailyLhbSnapshot]:
        started_at = perf_counter()
        try:
            akshare = import_module("akshare")
            frame = akshare.stock_lhb_detail_em(
                start_date=trade_date.strftime("%Y%m%d"),
                end_date=trade_date.strftime("%Y%m%d"),
            )
            rows = _records_from_frame(frame)
            snapshots = [_lhb_from_akshare_row(row, trade_date) for row in rows]
            snapshots = [snapshot for snapshot in snapshots if snapshot is not None]
            provider_records.append(
                _record("akshare", "lhb_snapshot", "success", len(snapshots), started_at)
            )
            return snapshots
        except Exception as exc:
            provider_records.append(
                _record("akshare", "lhb_snapshot", "failed", 0, started_at, str(exc))
            )
            return []

    def _load_postgres_events(
        self,
        trade_date: date,
        provider_records: list[dict[str, Any]],
    ) -> list[DailyEventCatalyst]:
        started_at = perf_counter()
        if self._event_storage is None:
            provider_records.append(
                _record("postgres", "news_event", "partial", 0, started_at, "not_configured")
            )
            return []
        try:
            events = self._event_storage.search_news_events(limit=200)
            start = datetime(
                trade_date.year,
                trade_date.month,
                trade_date.day,
                tzinfo=UTC,
            ) - timedelta(days=2)
            end = start + timedelta(days=4)
            catalysts = [
                _event_catalyst_from_news_event(event, trade_date)
                for event in events
                if start <= _aware_datetime(getattr(event, "occurred_at", None)) <= end
            ]
            catalysts = [event for event in catalysts if event is not None][:80]
            provider_records.append(
                _record("postgres", "news_event", "success", len(catalysts), started_at)
            )
            return catalysts
        except Exception as exc:
            provider_records.append(
                _record("postgres", "news_event", "failed", 0, started_at, str(exc))
            )
            return []

    def _load_financial_contexts(
        self,
        trade_date: date,
        stocks: list[DailyStockSnapshot],
        provider_records: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        started_at = perf_counter()
        if self._financial_storage is None:
            provider_records.append(
                _record(
                    "postgres",
                    "financial_context",
                    "partial",
                    0,
                    started_at,
                    "not_configured",
                )
            )
            return []
        as_of = datetime(
            trade_date.year,
            trade_date.month,
            trade_date.day,
            23,
            59,
            tzinfo=UTC,
        )
        contexts: list[dict[str, Any]] = []
        try:
            for stock in sorted(stocks, key=lambda item: item.amount, reverse=True)[:20]:
                context = self._financial_storage.load_financial_context(
                    stock.symbol,
                    as_of=as_of,
                    max_periods=4,
                )
                if context.get("quality_status") != "empty":
                    contexts.append(dict(context))
            provider_records.append(
                _record(
                    "postgres",
                    "financial_context",
                    "success",
                    len(contexts),
                    started_at,
                )
            )
            return contexts
        except Exception as exc:
            provider_records.append(
                _record("postgres", "financial_context", "failed", 0, started_at, str(exc))
            )
            return []


def _snapshot_from_tick(tick: Any, trade_date: date) -> DailyStockSnapshot | None:
    last_price = _to_decimal(getattr(tick, "last_price", None))
    if last_price <= 0:
        return None
    pre_close = _to_decimal(getattr(tick, "pre_close", None))
    pct_change = (
        (last_price - pre_close) / pre_close * Decimal("100")
        if pre_close > 0
        else Decimal("0")
    )
    exchange = getattr(getattr(tick, "exchange", None), "value", "")
    symbol = f"{getattr(tick, 'symbol', '')}.{exchange}" if exchange else getattr(tick, "symbol", "")
    open_price = _to_decimal(getattr(tick, "open_price", None)) or last_price
    high_price = max(_to_decimal(getattr(tick, "high_price", None)), open_price, last_price)
    low_price = min(
        value
        for value in [_to_decimal(getattr(tick, "low_price", None)), open_price, last_price]
        if value > 0
    )
    return DailyStockSnapshot(
        symbol=symbol,
        name=getattr(tick, "name", "") or symbol,
        trade_date=trade_date,
        open_price=open_price,
        high_price=high_price,
        low_price=low_price,
        close_price=last_price,
        pct_change=pct_change,
        volume=int(_to_decimal(getattr(tick, "volume", None))),
        amount=_to_decimal(getattr(tick, "turnover", None)),
        turnover_rate=None,
        is_limit_up=pct_change >= Decimal("9.8"),
        is_limit_down=pct_change <= Decimal("-9.8"),
        provider="vnpy_main_engine",
    )


def _snapshot_from_akshare_row(
    row: dict[str, Any],
    trade_date: date,
) -> DailyStockSnapshot | None:
    symbol = _vt_symbol(_text_value(row, "代码", "code", "symbol"))
    if not symbol:
        return None
    close_price = _to_decimal(_row_value(row, "最新价", "close", "price"))
    if close_price <= 0:
        return None
    open_price = _positive_or(_to_decimal(_row_value(row, "今开", "open")), close_price)
    high_price = max(
        _positive_or(_to_decimal(_row_value(row, "最高", "high")), close_price),
        open_price,
        close_price,
    )
    low_price = min(
        _positive_or(_to_decimal(_row_value(row, "最低", "low")), close_price),
        open_price,
        close_price,
    )
    pct_change = _to_decimal(_row_value(row, "涨跌幅", "pct_change"))
    return DailyStockSnapshot(
        symbol=symbol,
        name=_text_value(row, "名称", "name") or symbol,
        trade_date=trade_date,
        open_price=open_price,
        high_price=high_price,
        low_price=low_price,
        close_price=close_price,
        pct_change=pct_change,
        volume=int(_to_decimal(_row_value(row, "成交量", "volume"))),
        amount=_to_decimal(_row_value(row, "成交额", "amount")),
        turnover_rate=_to_decimal(_row_value(row, "换手率", "turnover_rate")),
        is_limit_up=pct_change >= Decimal("9.8"),
        is_limit_down=pct_change <= Decimal("-9.8"),
        provider="akshare",
    )


def _sector_from_akshare_row(
    row: dict[str, Any],
    trade_date: date,
) -> DailySectorSnapshot | None:
    name = _text_value(row, "板块名称", "名称", "name")
    if not name:
        return None
    leader_symbol = _vt_symbol(_text_value(row, "领涨股票代码", "领涨股票", "leader"))
    return DailySectorSnapshot(
        sector_name=name,
        trade_date=trade_date,
        pct_change=_to_decimal(_row_value(row, "涨跌幅", "pct_change")),
        turnover_amount=_to_decimal(_row_value(row, "成交额", "amount")),
        advance_count=int(_to_decimal(_row_value(row, "上涨家数", "advance_count"))),
        decline_count=int(_to_decimal(_row_value(row, "下跌家数", "decline_count"))),
        leader_symbols=[leader_symbol] if leader_symbol else [],
        provider="akshare",
    )


def _limit_up_from_akshare_row(
    row: dict[str, Any],
    trade_date: date,
) -> DailyLimitUpSnapshot | None:
    symbol = _vt_symbol(_text_value(row, "代码", "symbol", "code"))
    if not symbol:
        return None
    return DailyLimitUpSnapshot(
        symbol=symbol,
        trade_date=trade_date,
        board_count=max(1, int(_to_decimal(_row_value(row, "连板数", "board_count")))),
        sealed=True,
        broken_count=int(_to_decimal(_row_value(row, "炸板次数", "broken_count"))),
        provider="akshare",
    )


def _lhb_from_akshare_row(
    row: dict[str, Any],
    trade_date: date,
) -> DailyLhbSnapshot | None:
    symbol = _vt_symbol(_text_value(row, "代码", "股票代码", "symbol", "code"))
    if not symbol:
        return None
    buy_amount = _to_decimal(_row_value(row, "买入额", "买入金额", "buy_amount"))
    sell_amount = _to_decimal(_row_value(row, "卖出额", "卖出金额", "sell_amount"))
    net_buy = _to_decimal(_row_value(row, "净买额", "净买入", "net_buy_amount"))
    if net_buy == 0 and (buy_amount > 0 or sell_amount > 0):
        net_buy = buy_amount - sell_amount
    return DailyLhbSnapshot(
        symbol=symbol,
        trade_date=trade_date,
        buy_amount=buy_amount,
        sell_amount=sell_amount,
        net_buy_amount=net_buy,
        seat_tags=[_text_value(row, "上榜原因", "解读", "reason")],
        provider="akshare",
    )


def _intraday_anomalies_from_stocks(
    stocks: list[DailyStockSnapshot],
) -> list[DailyIntradayAnomaly]:
    anomalies: list[DailyIntradayAnomaly] = []
    for stock in stocks:
        if stock.pct_change >= Decimal("7"):
            anomaly_type = "strong_pull_up"
        elif stock.pct_change <= Decimal("-7"):
            anomaly_type = "sharp_selloff"
        else:
            continue
        anomalies.append(
            DailyIntradayAnomaly(
                symbol=stock.symbol,
                trade_date=stock.trade_date,
                anomaly_type=anomaly_type,
                occurred_at=datetime.now(UTC),
                strength_score=min(Decimal("15"), abs(stock.pct_change)),
                description=f"{stock.name} 最新涨跌幅 {stock.pct_change}%",
                provider="derived_from_stock_snapshot",
            )
        )
    return anomalies[:200]


def _event_catalyst_from_news_event(
    event: Any,
    trade_date: date,
) -> DailyEventCatalyst | None:
    title = str(getattr(event, "title", "") or "")
    if not title:
        return None
    vt_symbol = str(getattr(event, "vt_symbol", "") or "")
    summary = str(getattr(event, "summary", "") or "")
    content_hash = sha256(
        "|".join(
            [
                str(getattr(event, "event_id", "")),
                vt_symbol,
                title,
                summary,
            ]
        ).encode("utf-8")
    ).hexdigest()
    return DailyEventCatalyst(
        trade_date=trade_date,
        title=title,
        source=str(getattr(event, "source", "") or "news_event"),
        source_type=str(getattr(event, "event_type", "") or "news"),
        published_at=_aware_datetime(getattr(event, "occurred_at", None)),
        related_symbols=[vt_symbol] if vt_symbol else [],
        related_sectors=[
            value
            for value in [
                str(getattr(event, "sector", "") or ""),
                str(getattr(event, "topic", "") or ""),
            ]
            if value
        ],
        sentiment=_event_sentiment(event),
        trust_score=_trust_score(getattr(event, "trust_score", 0)),
        content_hash=content_hash,
    )


def _records_from_frame(frame: Any) -> list[dict[str, Any]]:
    if frame is None:
        return []
    if hasattr(frame, "to_dict"):
        return list(frame.to_dict("records"))
    return list(frame)


def _row_value(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in row:
            return row[name]
    return None


def _text_value(row: dict[str, Any], *names: str) -> str:
    value = _row_value(row, *names)
    if value is None:
        return ""
    return str(value).strip()


def _to_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    try:
        if str(value).lower() in {"nan", "none", ""}:
            return Decimal("0")
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _positive_or(value: Decimal, fallback: Decimal) -> Decimal:
    return value if value > 0 else fallback


def _aware_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
    return datetime.now(UTC)


def _trust_score(value: Any) -> Decimal:
    score = _to_decimal(value)
    if score <= 0:
        return Decimal("0.6")
    if score > 1:
        return Decimal("1")
    return score


def _event_sentiment(event: Any) -> str:
    event_type = str(getattr(event, "event_type", "") or "").lower()
    title = str(getattr(event, "title", "") or "")
    negative_words = ("风险", "处罚", "监管", "亏损", "减持", "暴雷", "问询")
    positive_words = ("增长", "中标", "回购", "增持", "突破", "合作", "利好")
    if any(word in title for word in negative_words) or "risk" in event_type:
        return "negative"
    if any(word in title for word in positive_words):
        return "positive"
    return "neutral"


def _vt_symbol(raw_symbol: str) -> str:
    symbol = raw_symbol.strip().upper()
    if not symbol:
        return ""
    symbol = symbol.removeprefix("SH").removeprefix("SZ").removeprefix("BJ")
    symbol = symbol.split(".")[0]
    if not symbol:
        return ""
    if symbol.startswith(("6", "9")):
        return f"{symbol}.SSE"
    if symbol.startswith(("0", "2", "3")):
        return f"{symbol}.SZSE"
    if symbol.startswith(("4", "8")):
        return f"{symbol}.BSE"
    return symbol


def _record(
    provider: str,
    data_type: str,
    status: str,
    row_count: int,
    started_at: float,
    error_message: str | None = None,
) -> dict[str, Any]:
    return {
        "provider": provider,
        "data_type": data_type,
        "status": status,
        "row_count": row_count,
        "elapsed_ms": max(0, round((perf_counter() - started_at) * 1000)),
        "error_message": error_message,
    }
