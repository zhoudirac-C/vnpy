"""
Full-market seven-rail Bollinger scanner.
"""

from __future__ import annotations

import json

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Protocol

from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import BarData, HistoryRequest
from vnpy.trader.setting import SETTINGS

from .indicator import (
    SevenBollIndicatorConfig,
    calculate_seven_bollinger,
)
from .signals import SevenBollSignalResult, evaluate_seven_boll_signal


class SevenBollHistoryProvider(Protocol):
    """
    Loads symbol universe and historical bars for scanning.
    """

    def load_symbols(self, request: "SevenBollScanRequest") -> list[str]:
        pass

    def load_bars(self, vt_symbol: str, request: "SevenBollScanRequest") -> list[BarData]:
        pass

    def load_name(self, vt_symbol: str) -> str:
        pass

    def load_concept(self, vt_symbol: str) -> str:
        pass


@dataclass(frozen=True)
class SevenBollScanRequest:
    """
    One scan request.
    """

    interval: Interval = Interval.DAILY
    lookback_days: int = 260
    max_symbols: int = 0
    min_buy_score: float = 65.0
    min_sell_score: float = 65.0
    symbols: tuple[str, ...] = ()
    scan_type: str = "manual"
    end: datetime = field(default_factory=datetime.now)
    config: SevenBollIndicatorConfig = field(default_factory=SevenBollIndicatorConfig)

    def __post_init__(self) -> None:
        if self.interval != Interval.DAILY:
            raise ValueError("seven boll scanner only supports daily interval")


@dataclass(frozen=True)
class SevenBollScanResult:
    """
    One symbol scan result.
    """

    vt_symbol: str
    name: str
    action: str
    score: float
    buy_score: float
    sell_score: float
    signal_types: tuple[str, ...]
    reasons: tuple[str, ...]
    risks: tuple[str, ...]
    close: float
    zscore: float
    bandwidth_percentile: float | None
    mid_slope: float | None
    rail_zone: str
    regime: str
    bar_datetime: Any
    interval: str
    boll_point: dict[str, Any] = field(default_factory=dict)
    concept: str = ""
    report_run_id: str = ""

    def to_context(self) -> dict[str, Any]:
        """
        Convert scan output into TradingAgents context override.
        """
        return {
            "vt_symbol": self.vt_symbol,
            "name": self.name,
            "concept": self.concept,
            "action": self.action,
            "score": self.score,
            "buy_score": self.buy_score,
            "sell_score": self.sell_score,
            "signals": list(self.signal_types),
            "reasons": list(self.reasons),
            "risks": list(self.risks),
            "close": self.close,
            "zscore": self.zscore,
            "bandwidth_percentile": self.bandwidth_percentile,
            "mid_slope": self.mid_slope,
            "rail_zone": self.rail_zone,
            "regime": self.regime,
            "bar_datetime": str(self.bar_datetime),
            "interval": self.interval,
            "boll_point": dict(self.boll_point),
        }


@dataclass(frozen=True)
class SevenBollScanSummary:
    """
    Scan summary shown by the UI.
    """

    run_id: str
    started_at: datetime
    finished_at: datetime
    status: str
    total_symbols: int
    scanned_symbols: int
    skipped_symbols: int
    buy_candidates: list[SevenBollScanResult]
    sell_candidates: list[SevenBollScanResult]
    errors: list[str] = field(default_factory=list)

    @property
    def all_candidates(self) -> list[SevenBollScanResult]:
        return [*self.buy_candidates, *self.sell_candidates]


@dataclass(frozen=True)
class SevenBollScanProgress:
    """
    Incremental scan progress for UI/background workers.
    """

    run_id: str
    status: str
    total_symbols: int
    scanned_symbols: int
    skipped_symbols: int
    buy_count: int
    sell_count: int
    current_symbol: str = ""
    error_count: int = 0


class SevenBollScanService:
    """
    Deterministic seven-rail Bollinger full-market scanner.
    """

    def __init__(
        self,
        history_provider: SevenBollHistoryProvider,
        run_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.history_provider = history_provider
        self.run_id_factory = run_id_factory or _scan_run_id
        self.latest_summary: SevenBollScanSummary | None = None

    def scan(
        self,
        request: SevenBollScanRequest,
        progress_callback: Callable[[SevenBollScanProgress], None] | None = None,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> SevenBollScanSummary:
        """
        Run one scan.
        """
        started_at = datetime.now()
        run_id = self.run_id_factory()
        symbols = self.history_provider.load_symbols(request)
        if request.max_symbols > 0:
            symbols = symbols[: request.max_symbols]

        buy_candidates: list[SevenBollScanResult] = []
        sell_candidates: list[SevenBollScanResult] = []
        errors: list[str] = []
        scanned = 0
        skipped = 0
        status = "running"

        def publish(current_symbol: str = "") -> None:
            if progress_callback is None:
                return
            progress_callback(
                SevenBollScanProgress(
                    run_id=run_id,
                    status=status,
                    total_symbols=len(symbols),
                    scanned_symbols=scanned,
                    skipped_symbols=skipped,
                    buy_count=len(buy_candidates),
                    sell_count=len(sell_candidates),
                    current_symbol=current_symbol,
                    error_count=len(errors),
                )
            )

        publish()

        for vt_symbol in symbols:
            if cancel_requested is not None and cancel_requested():
                status = "cancelled"
                publish(vt_symbol)
                break

            try:
                bars = self.history_provider.load_bars(vt_symbol, request)
            except Exception as exc:
                skipped += 1
                errors.append(f"{vt_symbol}: {exc}")
                publish(vt_symbol)
                continue

            if len(bars) < request.config.window + request.config.std_ma_window:
                skipped += 1
                publish(vt_symbol)
                continue

            scanned += 1
            points = calculate_seven_bollinger(bars, request.config)
            signal = evaluate_seven_boll_signal(bars, points, request.config)
            if signal is None:
                skipped += 1
                publish(vt_symbol)
                continue

            result = _scan_result_from_signal(
                vt_symbol=vt_symbol,
                name=self.history_provider.load_name(vt_symbol),
                concept=_load_concept(self.history_provider, vt_symbol),
                signal=signal,
            )
            if result.action == "buy_watch" and result.buy_score >= request.min_buy_score:
                buy_candidates.append(result)
            elif result.action == "sell_watch" and result.sell_score >= request.min_sell_score:
                sell_candidates.append(result)
            publish(vt_symbol)
        else:
            status = "completed"

        buy_candidates.sort(key=lambda item: item.score, reverse=True)
        sell_candidates.sort(key=lambda item: item.score, reverse=True)
        summary = SevenBollScanSummary(
            run_id=run_id,
            started_at=started_at,
            finished_at=datetime.now(),
            status=status,
            total_symbols=len(symbols),
            scanned_symbols=scanned,
            skipped_symbols=skipped,
            buy_candidates=buy_candidates,
            sell_candidates=sell_candidates,
            errors=errors[:50],
        )
        self.latest_summary = summary
        publish()
        return summary


class VnpySevenBollHistoryProvider:
    """
    vn.py history provider that prefers local database, then router datafeed.
    """

    def __init__(
        self,
        main_engine: Any | None = None,
        settings: Mapping[str, Any] | None = None,
    ) -> None:
        self.main_engine = main_engine
        self.settings = settings or SETTINGS
        self._name_cache: dict[str, str] = {}
        self._concept_cache: dict[str, str] = {}
        self._security_catalog: Any | None = None
        self._security_catalog_loaded: bool = False
        self._datafeed: Any | None = None
        self._database: Any | None = None

    def load_symbols(self, request: SevenBollScanRequest) -> list[str]:
        """
        Load explicit symbols first, then settings/main-engine/AKShare universe.
        """
        if request.symbols:
            return list(dict.fromkeys(_normalize_vt_symbol(symbol) for symbol in request.symbols if symbol))

        explicit = _split_symbols(self.settings.get("seven_boll.scan.symbols", ""))
        if explicit:
            return explicit

        symbols = _symbols_from_main_engine(self.main_engine, self._name_cache)
        if symbols:
            return symbols

        symbols = _symbols_from_bar_overview(self._database_or_none())
        if symbols:
            return symbols

        try:
            from vnpy_tradingagents.bootstrap import _symbols_from_akshare_universe

            return list(_symbols_from_akshare_universe())
        except Exception:
            return []

    def load_bars(self, vt_symbol: str, request: SevenBollScanRequest) -> list[BarData]:
        """
        Load bars from vn.py database first, then configured datafeed/router.
        """
        normalized = _normalize_vt_symbol(vt_symbol)
        symbol, exchange = _parse_vt_symbol(normalized)
        start = request.end - timedelta(days=max(request.lookback_days, request.config.window * 3))
        bars = self._load_database_bars(symbol, exchange, request.interval, start, request.end)
        if not bars:
            bars = self._load_datafeed_bars(symbol, exchange, request.interval, start, request.end)
        return self._refresh_latest_daily_bar_if_needed(
            normalized,
            symbol,
            exchange,
            request,
            start,
            bars,
        )

    def load_name(self, vt_symbol: str) -> str:
        normalized = _normalize_vt_symbol(vt_symbol)
        if normalized in self._name_cache:
            return self._name_cache[normalized]

        entity = self._security_entity_from_catalog(normalized)
        if entity is not None:
            name = str(getattr(entity, "short_name", "") or getattr(entity, "name", "") or "")
            if name:
                self._name_cache[normalized] = name
                return name

        metadata = self._security_entity_from_database(normalized)
        name = str(metadata.get("short_name") or metadata.get("name") or "") if metadata else ""
        if name:
            self._name_cache[normalized] = name
        return name

    def load_concept(self, vt_symbol: str) -> str:
        normalized = _normalize_vt_symbol(vt_symbol)
        if normalized in self._concept_cache:
            return self._concept_cache[normalized]

        concept = ",".join(self._security_concepts_from_database(normalized))
        if not concept:
            concept = _concept_from_security_metadata(
                self._security_entity_from_database(normalized)
            )
        if not concept:
            entity = self._security_entity_from_catalog(normalized)
            concept = _concept_from_security_entity(entity)
        self._concept_cache[normalized] = concept
        return concept

    def _load_database_bars(
        self,
        symbol: str,
        exchange: Exchange,
        interval: Interval,
        start: datetime,
        end: datetime,
    ) -> list[BarData]:
        database = self._database_or_none()
        if database is None:
            return []
        try:
            return list(database.load_bar_data(symbol, exchange, interval, start, end) or [])
        except Exception:
            return []

    def _load_datafeed_bars(
        self,
        symbol: str,
        exchange: Exchange,
        interval: Interval,
        start: datetime,
        end: datetime,
    ) -> list[BarData]:
        datafeed = self._datafeed_or_none()
        if datafeed is None:
            return []
        req = HistoryRequest(
            symbol=symbol,
            exchange=exchange,
            interval=interval,
            start=start,
            end=end,
        )
        try:
            init = getattr(datafeed, "init", None)
            if callable(init):
                init(output=lambda _message: None)
            return list(datafeed.query_bar_history(req, output=lambda _message: None) or [])
        except Exception:
            return []

    def _refresh_latest_daily_bar_if_needed(
        self,
        vt_symbol: str,
        symbol: str,
        exchange: Exchange,
        request: SevenBollScanRequest,
        start: datetime,
        bars: list[BarData],
    ) -> list[BarData]:
        if request.interval != Interval.DAILY:
            return bars
        if not _bool_setting(self.settings.get("seven_boll.scan.refresh_latest_daily", True), True):
            return bars
        if request.end.date() != datetime.now().date():
            return bars

        datafeed = self._datafeed_or_none()
        refresh_bar_history = getattr(datafeed, "refresh_bar_history", None)
        if not callable(refresh_bar_history):
            return bars

        ttl_seconds = _int_setting(
            self.settings.get("seven_boll.scan.latest_daily_ttl_seconds", 900),
            900,
        )
        if ttl_seconds > 0 and self._latest_daily_snapshot_fresh(vt_symbol, ttl_seconds):
            return bars

        refresh_start = max(start, request.end.replace(hour=0, minute=0, second=0, microsecond=0))
        req = HistoryRequest(
            symbol=symbol,
            exchange=exchange,
            interval=Interval.DAILY,
            start=refresh_start,
            end=request.end,
        )
        try:
            init = getattr(datafeed, "init", None)
            if callable(init):
                init(output=lambda _message: None)
            refreshed = list(refresh_bar_history(req, output=lambda _message: None) or [])
        except Exception:
            return bars
        if not refreshed:
            return bars
        return _merge_bars_by_date(bars, refreshed)

    def _latest_daily_snapshot_fresh(self, vt_symbol: str, ttl_seconds: int) -> bool:
        database = self._database_or_none()
        peewee_database = getattr(database, "db", None)
        if peewee_database is None:
            return False
        placeholder = getattr(peewee_database, "param", "?")
        try:
            cursor = peewee_database.execute_sql(
                "SELECT pulled_at "
                "FROM market_bar_snapshot "
                f"WHERE vt_symbol = {placeholder} AND interval = 'd' "
                "ORDER BY datetime DESC, pulled_at DESC "
                "LIMIT 1",
                (vt_symbol,),
            )
            row = cursor.fetchone()
        except Exception:
            return False
        if not row:
            return False
        pulled_at = row[0] if isinstance(row, (list, tuple)) else getattr(row, "pulled_at", None)
        pulled_at_dt = _to_datetime_or_none(pulled_at)
        if pulled_at_dt is None:
            return False
        now = datetime.now(pulled_at_dt.tzinfo) if pulled_at_dt.tzinfo else datetime.now()
        return (now - pulled_at_dt).total_seconds() < ttl_seconds

    def _database_or_none(self) -> Any | None:
        if self._database is not None:
            return self._database
        try:
            from vnpy.trader.database import get_database

            self._database = get_database()
        except Exception:
            self._database = None
        return self._database

    def _datafeed_or_none(self) -> Any | None:
        if self._datafeed is not None:
            return self._datafeed
        try:
            from vnpy.trader.datafeed import get_datafeed

            self._datafeed = get_datafeed()
        except Exception:
            self._datafeed = None
        return self._datafeed

    def _security_entity_from_catalog(self, vt_symbol: str) -> Any | None:
        catalog = self._security_catalog_or_none()
        if catalog is None:
            return None
        try:
            return catalog.get(vt_symbol)
        except Exception:
            return None

    def _security_catalog_or_none(self) -> Any | None:
        if self._security_catalog_loaded:
            return self._security_catalog
        self._security_catalog_loaded = True
        catalog_path = str(
            self.settings.get("financial.ingestion.catalog_path")
            or self.settings.get("news.entity.catalog_path")
            or ""
        ).strip()
        if not catalog_path:
            return None
        try:
            from vnpy_router.security_catalog import SecurityEntityCatalog

            self._security_catalog = SecurityEntityCatalog.from_path(catalog_path)
        except Exception:
            self._security_catalog = None
        return self._security_catalog

    def _security_entity_from_database(self, vt_symbol: str) -> dict[str, Any]:
        database = self._database_or_none()
        peewee_database = getattr(database, "db", None)
        if peewee_database is None:
            return {}
        placeholder = getattr(peewee_database, "param", "?")
        try:
            cursor = peewee_database.execute_sql(
                "SELECT name, short_name, industry, sector, concept_tags "
                f"FROM security_entity WHERE vt_symbol = {placeholder} LIMIT 1",
                (vt_symbol,),
            )
            row = cursor.fetchone()
        except Exception:
            return {}
        if not row:
            return {}
        return {
            "name": row[0],
            "short_name": row[1],
            "industry": row[2],
            "sector": row[3],
            "concept_tags": row[4],
        }

    def _security_concepts_from_database(self, vt_symbol: str, limit: int = 3) -> list[str]:
        database = self._database_or_none()
        peewee_database = getattr(database, "db", None)
        if peewee_database is None:
            return []
        placeholder = getattr(peewee_database, "param", "?")
        try:
            cursor = peewee_database.execute_sql(
                "SELECT board_name "
                "FROM security_concept_link "
                f"WHERE vt_symbol = {placeholder} AND board_type = 'concept' "
                "ORDER BY is_primary DESC, COALESCE(relevance_score, 0) DESC, board_name "
                f"LIMIT {max(1, int(limit))}",
                (vt_symbol,),
            )
            rows = cursor.fetchall()
        except Exception:
            return []
        concepts: list[str] = []
        for row in rows or []:
            value = str(row[0] if isinstance(row, (list, tuple)) else row or "").strip()
            if value and value not in concepts:
                concepts.append(value)
        return concepts


def build_scan_request_from_settings(
    settings: Mapping[str, Any] | None = None,
    symbols: Sequence[str] | None = None,
    scan_type: str = "manual",
) -> SevenBollScanRequest:
    """
    Build a scan request from vn.py SETTINGS plus optional UI overrides.
    """
    source = settings or SETTINGS
    return SevenBollScanRequest(
        interval=Interval.DAILY,
        lookback_days=_int_setting(
            source.get("seven_boll.scan.lookback_bars", source.get("seven_boll.scan.lookback_days", 250)),
            250,
        ),
        max_symbols=_int_setting(source.get("seven_boll.scan.max_symbols", 0), 0),
        min_buy_score=float(source.get("seven_boll.scan.min_buy_score", 65.0) or 65.0),
        min_sell_score=float(source.get("seven_boll.scan.min_sell_score", 65.0) or 65.0),
        symbols=tuple(_normalize_vt_symbol(symbol) for symbol in (symbols or []) if symbol),
        scan_type=scan_type,
        config=SevenBollIndicatorConfig(
            window=_int_setting(source.get("seven_boll.indicator.window", 20), 20),
            std_ma_window=_int_setting(source.get("seven_boll.indicator.std_ma_window", 5), 5),
            squeeze_lookback=_int_setting(source.get("seven_boll.indicator.squeeze_lookback", 120), 120),
            trend_slope_window=_int_setting(source.get("seven_boll.indicator.trend_slope_window", 5), 5),
            pullback_tolerance=float(source.get("seven_boll.indicator.pullback_tolerance", 0.01) or 0.01),
            squeeze_percentile=float(source.get("seven_boll.indicator.squeeze_percentile", 10.0) or 10.0),
            volume_breakout_ratio=float(source.get("seven_boll.indicator.volume_breakout_ratio", 1.5) or 1.5),
        ),
    )


def _scan_result_from_signal(
    vt_symbol: str,
    name: str,
    concept: str,
    signal: SevenBollSignalResult,
) -> SevenBollScanResult:
    point = signal.point
    score = max(signal.buy_score, signal.sell_score)
    return SevenBollScanResult(
        vt_symbol=vt_symbol,
        name=name,
        concept=concept,
        action=signal.action,
        score=score,
        buy_score=signal.buy_score,
        sell_score=signal.sell_score,
        signal_types=tuple(item.signal_type for item in signal.signals),
        reasons=tuple(item.reason for item in signal.signals),
        risks=tuple(item.risk for item in signal.signals),
        close=point.close,
        zscore=point.zscore,
        bandwidth_percentile=point.bandwidth_percentile,
        mid_slope=point.mid_slope,
        rail_zone=point.rail_zone,
        regime=point.regime,
        bar_datetime=point.datetime,
        interval=Interval.DAILY.value,
        boll_point=_boll_point_snapshot(point),
    )


def _boll_point_snapshot(point: Any) -> dict[str, Any]:
    return {
        "current_price": point.close,
        "bar_datetime": str(point.datetime),
        "top_band": point.top_band,
        "upper2_band": point.upper2_band,
        "upper1_band": point.upper1_band,
        "mid": point.mid,
        "lower1_band": point.lower1_band,
        "lower2_band": point.lower2_band,
        "bottom_band": point.bottom_band,
        "zscore": point.zscore,
        "bandwidth_percentile": point.bandwidth_percentile,
        "mid_slope": point.mid_slope,
        "rail_zone": point.rail_zone,
    }


def _load_concept(history_provider: SevenBollHistoryProvider, vt_symbol: str) -> str:
    load_concept = getattr(history_provider, "load_concept", None)
    if not callable(load_concept):
        return ""
    try:
        return str(load_concept(vt_symbol) or "")
    except Exception:
        return ""


def _concept_from_security_entity(entity: Any | None) -> str:
    if entity is None:
        return ""
    tags = getattr(entity, "concept_tags", ()) or ()
    if tags:
        return ",".join(str(item) for item in tags if str(item))
    return str(
        getattr(entity, "industry", "")
        or getattr(entity, "sector", "")
        or ""
    )


def _concept_from_security_metadata(metadata: dict[str, Any]) -> str:
    if not metadata:
        return ""
    tags = metadata.get("concept_tags") or ()
    if isinstance(tags, str):
        tags = _concept_tags_from_text(tags)
    if isinstance(tags, (list, tuple)) and tags:
        return ",".join(str(item) for item in tags if str(item))
    return str(metadata.get("industry") or metadata.get("sector") or "")


def _concept_tags_from_text(value: str) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            decoded = None
        if isinstance(decoded, list):
            return [str(item).strip() for item in decoded if str(item).strip()]
    return [
        item.strip()
        for item in text.replace("，", ",").replace("|", ",").split(",")
        if item.strip()
    ]


def _merge_bars_by_date(
    bars: Sequence[BarData],
    refreshed_bars: Sequence[BarData],
) -> list[BarData]:
    merged: dict[Any, BarData] = {}
    for bar in bars:
        if bar.datetime is None:
            continue
        merged[bar.datetime.date()] = bar
    for bar in refreshed_bars:
        if bar.datetime is None:
            continue
        merged[bar.datetime.date()] = bar
    return sorted(merged.values(), key=lambda item: item.datetime)


def _to_datetime_or_none(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _symbols_from_main_engine(
    main_engine: Any | None,
    name_cache: dict[str, str],
) -> list[str]:
    if main_engine is None:
        return []
    get_all_contracts = getattr(main_engine, "get_all_contracts", None)
    if not callable(get_all_contracts):
        return []
    try:
        contracts = get_all_contracts()
    except Exception:
        return []

    symbols: list[str] = []
    seen: set[str] = set()
    for contract in contracts or []:
        vt_symbol = _normalize_vt_symbol(
            getattr(contract, "vt_symbol", "") or getattr(contract, "symbol", ""),
            getattr(contract, "exchange", None),
        )
        if not vt_symbol or vt_symbol in seen:
            continue
        seen.add(vt_symbol)
        symbols.append(vt_symbol)
        name_cache[vt_symbol] = str(getattr(contract, "name", "") or "")
    return symbols


def _symbols_from_bar_overview(database: Any | None) -> list[str]:
    if database is None:
        return []
    try:
        overviews = database.get_bar_overview()
    except Exception:
        return []
    symbols: list[str] = []
    seen: set[str] = set()
    for overview in overviews or []:
        vt_symbol = _normalize_vt_symbol(
            getattr(overview, "symbol", ""),
            getattr(overview, "exchange", None),
        )
        if vt_symbol and vt_symbol not in seen:
            seen.add(vt_symbol)
            symbols.append(vt_symbol)
    return symbols


def _split_symbols(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    for sep in (";", "，", "\n"):
        text = text.replace(sep, ",")
    return [_normalize_vt_symbol(item) for item in text.split(",") if item.strip()]


def _normalize_vt_symbol(value: Any, exchange: Exchange | None = None) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    parsed_exchange = exchange
    if "." in text:
        symbol_part, suffix = text.split(".", 1)
        text = symbol_part
        parsed_exchange = parsed_exchange or _exchange_from_suffix(suffix)
    for prefix, prefix_exchange in (
        ("SSE", Exchange.SSE),
        ("SZSE", Exchange.SZSE),
        ("BSE", Exchange.BSE),
        ("SH", Exchange.SSE),
        ("SZ", Exchange.SZSE),
        ("BJ", Exchange.BSE),
    ):
        if text.startswith(prefix):
            text = text[len(prefix):]
            parsed_exchange = parsed_exchange or prefix_exchange
            break
    symbol = text.zfill(6) if text.isdigit() and len(text) <= 6 else text
    if not symbol.isdigit() or len(symbol) != 6:
        return ""
    return f"{symbol}.{(parsed_exchange or _infer_exchange(symbol)).value}"


def _parse_vt_symbol(vt_symbol: str) -> tuple[str, Exchange]:
    normalized = _normalize_vt_symbol(vt_symbol)
    if not normalized or "." not in normalized:
        raise ValueError(f"invalid vt_symbol: {vt_symbol}")
    symbol, exchange_text = normalized.split(".", 1)
    return symbol, Exchange(exchange_text)


def _exchange_from_suffix(value: str) -> Exchange | None:
    return {
        "SH": Exchange.SSE,
        "SSE": Exchange.SSE,
        "SZ": Exchange.SZSE,
        "SZSE": Exchange.SZSE,
        "BJ": Exchange.BSE,
        "BSE": Exchange.BSE,
    }.get(str(value or "").strip().upper())


def _infer_exchange(symbol: str) -> Exchange:
    if symbol.startswith(("6", "9")):
        return Exchange.SSE
    if symbol.startswith(("8", "4")):
        return Exchange.BSE
    return Exchange.SZSE


def _interval_from_text(value: Any) -> Interval:
    text = str(value or "d").strip().lower()
    mapping = {
        "1m": Interval.MINUTE,
        "minute": Interval.MINUTE,
        "h": Interval.HOUR,
        "1h": Interval.HOUR,
        "hour": Interval.HOUR,
        "d": Interval.DAILY,
        "day": Interval.DAILY,
        "daily": Interval.DAILY,
        "w": Interval.WEEKLY,
        "week": Interval.WEEKLY,
        "weekly": Interval.WEEKLY,
    }
    return mapping.get(text, Interval(text))


def _int_setting(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _bool_setting(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _scan_run_id() -> str:
    return "seven-boll-" + datetime.now().strftime("%Y%m%d%H%M%S")
