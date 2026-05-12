"""
Deterministic signal engines for daily market review.
"""

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from .domain import (
    DailyEventCatalyst,
    DailyIntradayAnomaly,
    DailyLhbActiveSeatSnapshot,
    DailyLhbInstitutionSnapshot,
    DailyLhbSnapshot,
    DailyLhbStockSeatSnapshot,
    DailyLimitUpSnapshot,
    DailySectorSnapshot,
    DailyStockSnapshot,
)


@dataclass(frozen=True)
class MarketBreadthSignal:
    """
    Market breadth and short-term emotion signal.
    """

    advance_count: int
    decline_count: int
    flat_count: int
    limit_up_count: int
    limit_down_count: int
    breadth_score: Decimal
    emotion_score: Decimal
    quality_warnings: list[str] = field(default_factory=list)
    evidence_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SectorRotationSignal:
    """
    Sector rotation signal.
    """

    theme: str
    score: Decimal
    status: str
    leader_symbols: list[str]
    risk_tags: list[str] = field(default_factory=list)
    evidence_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LimitUpEmotionSignal:
    """
    Limit-up ecosystem signal.
    """

    limit_up_count: int
    sealed_count: int
    max_board_count: int
    broken_board_rate: Decimal
    emotion_score: Decimal
    risk_tags: list[str] = field(default_factory=list)
    evidence_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LhbCapitalSignal:
    """
    Dragon-tiger list capital signal.
    """

    net_buy_amount: Decimal
    top_net_buy_symbols: list[str]
    top_net_sell_symbols: list[str]
    evidence_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LhbSeatAnalysisSignal:
    """
    Dragon-tiger list institution and seat behavior signal.
    """

    institution_top_buy_symbols: list[str]
    institution_top_sell_symbols: list[str]
    active_seat_top_buy: list[dict[str, Any]]
    suspected_hot_money_seats: list[str]
    reason_category_counts: dict[str, int]
    high_concentration_symbols: list[str]
    symbol_payloads: dict[str, dict[str, Any]]
    risk_tags: list[str] = field(default_factory=list)
    evidence_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LeaderScore:
    """
    Core market leader candidate score.
    """

    symbol: str
    name: str
    role: str
    score: Decimal
    watch_action: str
    entry_condition: str
    avoid_condition: str
    position_rule: str
    evidence_payload: dict[str, Any] = field(default_factory=dict)


class MarketBreadthEngine:
    """
    Calculate all-stock breadth and emotion.
    """

    def calculate(self, stocks: list[DailyStockSnapshot]) -> MarketBreadthSignal:
        """
        Calculate market breadth from stock snapshots.
        """
        if not stocks:
            return MarketBreadthSignal(
                advance_count=0,
                decline_count=0,
                flat_count=0,
                limit_up_count=0,
                limit_down_count=0,
                breadth_score=Decimal("0"),
                emotion_score=Decimal("0"),
                quality_warnings=["empty_stock_snapshots"],
                evidence_payload={"effective_stock_count": 0},
            )

        advance_count = sum(1 for stock in stocks if stock.pct_change > 0)
        decline_count = sum(1 for stock in stocks if stock.pct_change < 0)
        flat_count = len(stocks) - advance_count - decline_count
        limit_up_count = sum(1 for stock in stocks if stock.is_limit_up)
        limit_down_count = sum(1 for stock in stocks if stock.is_limit_down)

        breadth_score = _quantize(
            Decimal(advance_count) / Decimal(len(stocks)) * Decimal("100")
        )
        limit_score = min(Decimal("100"), Decimal(limit_up_count * 2))
        drawdown_penalty = min(Decimal("40"), Decimal(limit_down_count * 2))
        emotion_score = _clamp(
            Decimal("0.6") * breadth_score
            + Decimal("0.4") * limit_score
            - drawdown_penalty
        )

        return MarketBreadthSignal(
            advance_count=advance_count,
            decline_count=decline_count,
            flat_count=flat_count,
            limit_up_count=limit_up_count,
            limit_down_count=limit_down_count,
            breadth_score=breadth_score,
            emotion_score=emotion_score,
            evidence_payload={
                "effective_stock_count": len(stocks),
                "advance_count": advance_count,
                "decline_count": decline_count,
                "flat_count": flat_count,
                "limit_up_count": limit_up_count,
                "limit_down_count": limit_down_count,
            },
        )


class SectorRotationEngine:
    """
    Calculate sector rotation strength.
    """

    def calculate(
        self,
        sectors: list[DailySectorSnapshot],
        stocks: list[DailyStockSnapshot],
    ) -> list[SectorRotationSignal]:
        """
        Return sorted sector signals.
        """
        if not sectors:
            sectors = _infer_sector_snapshots_from_stocks(stocks)
        signals = [_sector_signal_from_snapshot(snapshot) for snapshot in sectors]
        return sorted(signals, key=lambda signal: signal.score, reverse=True)


class LimitUpEmotionEngine:
    """
    Calculate short-term limit-up emotion.
    """

    def calculate(self, snapshots: list[DailyLimitUpSnapshot]) -> LimitUpEmotionSignal:
        """
        Calculate the limit-up ecosystem.
        """
        if not snapshots:
            return LimitUpEmotionSignal(
                limit_up_count=0,
                sealed_count=0,
                max_board_count=0,
                broken_board_rate=Decimal("0"),
                emotion_score=Decimal("0"),
                risk_tags=["empty_limit_up_snapshots"],
                evidence_payload={"limit_up_count": 0},
            )

        sealed_count = sum(1 for snapshot in snapshots if snapshot.sealed)
        max_board_count = max(snapshot.board_count for snapshot in snapshots)
        broken_count = sum(snapshot.broken_count for snapshot in snapshots)
        broken_board_rate = _quantize(
            Decimal(broken_count) / Decimal(len(snapshots))
        )
        risk_tags = []
        if broken_board_rate >= Decimal("0.5"):
            risk_tags.append("high_broken_board_rate")
        emotion_score = _clamp(
            Decimal(len(snapshots) * 2)
            + Decimal(sealed_count * 3)
            + Decimal(max_board_count * 8)
            - broken_board_rate * Decimal("20")
        )

        return LimitUpEmotionSignal(
            limit_up_count=len(snapshots),
            sealed_count=sealed_count,
            max_board_count=max_board_count,
            broken_board_rate=broken_board_rate,
            emotion_score=emotion_score,
            risk_tags=risk_tags,
            evidence_payload={
                "limit_up_count": len(snapshots),
                "sealed_count": sealed_count,
                "max_board_count": max_board_count,
                "broken_count": broken_count,
                "broken_board_rate": str(broken_board_rate),
            },
        )


class LhbCapitalEngine:
    """
    Calculate dragon-tiger list capital flow.
    """

    def calculate(self, snapshots: list[DailyLhbSnapshot]) -> LhbCapitalSignal:
        """
        Summarize net buy/sell symbols.
        """
        sorted_by_net = sorted(
            snapshots,
            key=lambda snapshot: snapshot.net_buy_amount,
            reverse=True,
        )
        return LhbCapitalSignal(
            net_buy_amount=sum(
                (snapshot.net_buy_amount for snapshot in snapshots),
                Decimal("0"),
            ),
            top_net_buy_symbols=[
                snapshot.symbol
                for snapshot in sorted_by_net
                if snapshot.net_buy_amount > 0
            ][:10],
            top_net_sell_symbols=[
                snapshot.symbol
                for snapshot in reversed(sorted_by_net)
                if snapshot.net_buy_amount < 0
            ][:10],
            evidence_payload={
                "snapshot_count": len(snapshots),
                "top_net_buy_symbols": [
                    snapshot.symbol
                    for snapshot in sorted_by_net
                    if snapshot.net_buy_amount > 0
                ][:10],
            },
        )


class LhbSeatAnalysisEngine:
    """
    Calculate institution, active seat, reason, and concentration signals.
    """

    def calculate(
        self,
        lhb_snapshots: list[DailyLhbSnapshot],
        institution_snapshots: list[DailyLhbInstitutionSnapshot],
        active_seats: list[DailyLhbActiveSeatSnapshot],
        stock_seats: list[DailyLhbStockSeatSnapshot],
    ) -> LhbSeatAnalysisSignal:
        """
        Summarize dragon-tiger list seat behavior.
        """
        lhb_by_symbol = {snapshot.symbol: snapshot for snapshot in lhb_snapshots}
        institution_by_symbol = {
            snapshot.symbol: snapshot
            for snapshot in institution_snapshots
        }
        stock_seats_by_symbol: dict[str, list[DailyLhbStockSeatSnapshot]] = {}
        for seat in stock_seats:
            stock_seats_by_symbol.setdefault(seat.symbol, []).append(seat)

        sorted_institutions = sorted(
            institution_snapshots,
            key=lambda snapshot: snapshot.net_amount,
            reverse=True,
        )
        sorted_active = sorted(
            active_seats,
            key=lambda seat: seat.net_amount,
            reverse=True,
        )
        reason_category_counts: dict[str, int] = {}
        for snapshot in lhb_snapshots:
            reason_category_counts[snapshot.reason_category] = (
                reason_category_counts.get(snapshot.reason_category, 0) + 1
            )
        for snapshot in institution_snapshots:
            if snapshot.symbol in lhb_by_symbol:
                continue
            reason_category_counts[snapshot.reason_category] = (
                reason_category_counts.get(snapshot.reason_category, 0) + 1
            )

        symbol_payloads: dict[str, dict[str, Any]] = {}
        risk_tags: list[str] = []
        all_symbols = set(lhb_by_symbol) | set(institution_by_symbol) | set(stock_seats_by_symbol)
        for symbol in all_symbols:
            lhb = lhb_by_symbol.get(symbol)
            institution = institution_by_symbol.get(symbol)
            seats = stock_seats_by_symbol.get(symbol, [])
            stock_hot_money_net = sum(
                (
                    seat.amount if seat.side == "buy" else -seat.amount
                    for seat in seats
                    if seat.seat_type_hint in {"hot_money", "broker_branch"}
                ),
                Decimal("0"),
            )
            institution_net = institution.net_amount if institution is not None else Decimal("0")
            lhb_net = lhb.net_buy_amount if lhb is not None else Decimal("0")
            capital_type = _capital_type(
                institution_net=institution_net,
                hot_money_net=stock_hot_money_net,
                lhb_net=lhb_net,
            )
            concentration_risk = _has_concentration_risk(lhb) if lhb is not None else False
            if institution is not None and institution.concentration_ratio is not None:
                concentration_risk = (
                    concentration_risk
                    or abs(institution.concentration_ratio) >= Decimal("15")
                )
            if concentration_risk:
                risk_tags.append(f"high_concentration:{symbol}")
            reason_category = (
                lhb.reason_category
                if lhb is not None
                else (institution.reason_category if institution is not None else "unknown")
            )
            symbol_payloads[symbol] = {
                "name": (
                    lhb.name
                    if lhb is not None
                    else (institution.name if institution is not None else "")
                ),
                "reason_category": reason_category,
                "list_reason": (
                    lhb.list_reason
                    if lhb is not None
                    else (institution.list_reason if institution is not None else "")
                ),
                "net_buy_amount": str(lhb_net),
                "net_buy_ratio": (
                    _decimal_to_text(lhb.net_buy_ratio)
                    if lhb is not None
                    else ""
                ),
                "turnover_ratio": (
                    _decimal_to_text(lhb.turnover_ratio)
                    if lhb is not None
                    else _decimal_to_text(
                        institution.concentration_ratio
                        if institution is not None
                        else None
                    )
                ),
                "turnover_rate": (
                    _decimal_to_text(lhb.turnover_rate)
                    if lhb is not None
                    else ""
                ),
                "institution_net_amount": str(institution_net),
                "institution_buy_count": (
                    institution.buy_institution_count
                    if institution is not None
                    else 0
                ),
                "institution_sell_count": (
                    institution.sell_institution_count
                    if institution is not None
                    else 0
                ),
                "stock_hot_money_net_amount": str(stock_hot_money_net),
                "capital_type": capital_type,
                "concentration_risk": concentration_risk,
                "top_seats": [
                    {
                        "side": seat.side,
                        "seat_name": seat.seat_name,
                        "seat_type_hint": seat.seat_type_hint,
                        "amount": str(seat.amount),
                        "success_rate": _decimal_to_text(seat.success_rate),
                    }
                    for seat in sorted(seats, key=lambda item: item.amount, reverse=True)[:8]
                ],
            }

        return LhbSeatAnalysisSignal(
            institution_top_buy_symbols=[
                snapshot.symbol
                for snapshot in sorted_institutions
                if snapshot.net_amount > 0
            ][:10],
            institution_top_sell_symbols=[
                snapshot.symbol
                for snapshot in reversed(sorted_institutions)
                if snapshot.net_amount < 0
            ][:10],
            active_seat_top_buy=[
                {
                    "seat_name": seat.seat_name,
                    "seat_type_hint": seat.seat_type_hint,
                    "net_amount": str(seat.net_amount),
                    "buy_stock_count": seat.buy_stock_count,
                    "buy_symbols": seat.buy_symbols[:8],
                }
                for seat in sorted_active
                if seat.net_amount > 0
            ][:12],
            suspected_hot_money_seats=[
                seat.seat_name
                for seat in sorted_active
                if seat.seat_type_hint in {"hot_money", "broker_branch"}
                and seat.net_amount > 0
            ][:12],
            reason_category_counts=reason_category_counts,
            high_concentration_symbols=[
                symbol
                for symbol, payload in symbol_payloads.items()
                if payload["concentration_risk"]
            ],
            symbol_payloads=symbol_payloads,
            risk_tags=risk_tags,
            evidence_payload={
                "institution_snapshot_count": len(institution_snapshots),
                "active_seat_count": len(active_seats),
                "stock_seat_count": len(stock_seats),
                "reason_category_counts": reason_category_counts,
                "symbol_payloads": symbol_payloads,
            },
        )


class LeaderScoringEngine:
    """
    Calculate core watch candidates.
    """

    def calculate(
        self,
        stock_snapshots: list[DailyStockSnapshot],
        sector_signals: list[SectorRotationSignal],
        limit_up_snapshots: list[DailyLimitUpSnapshot],
        lhb_snapshots: list[DailyLhbSnapshot],
        intraday_anomalies: list[DailyIntradayAnomaly],
        event_catalysts: list[DailyEventCatalyst],
        lhb_seat_signal: LhbSeatAnalysisSignal | None = None,
    ) -> list[LeaderScore]:
        """
        Aggregate sector, capital, anomaly, and event signals.
        """
        sector_by_symbol = _sector_by_symbol(sector_signals)
        limit_by_symbol = {snapshot.symbol: snapshot for snapshot in limit_up_snapshots}
        lhb_by_symbol = {snapshot.symbol: snapshot for snapshot in lhb_snapshots}
        lhb_seat_payloads = (
            lhb_seat_signal.symbol_payloads
            if lhb_seat_signal is not None
            else {}
        )
        anomaly_score_by_symbol = _anomaly_score_by_symbol(intraday_anomalies)
        event_penalty_by_symbol = _event_penalty_by_symbol(event_catalysts)

        scores = [
            _leader_score_from_stock(
                stock=stock,
                sector_name=sector_by_symbol.get(stock.symbol, stock.sector or ""),
                sector_anchor=stock.symbol in sector_by_symbol,
                limit_snapshot=limit_by_symbol.get(stock.symbol),
                lhb_snapshot=lhb_by_symbol.get(stock.symbol),
                lhb_seat_payload=lhb_seat_payloads.get(stock.symbol, {}),
                anomaly_score=anomaly_score_by_symbol.get(stock.symbol, Decimal("0")),
                event_penalty=event_penalty_by_symbol.get(stock.symbol, Decimal("0")),
            )
            for stock in stock_snapshots
        ]
        return sorted(scores, key=lambda score: score.score, reverse=True)


def _infer_sector_snapshots_from_stocks(
    stocks: list[DailyStockSnapshot],
) -> list[DailySectorSnapshot]:
    groups: dict[str, list[DailyStockSnapshot]] = {}
    for stock in stocks:
        if stock.sector:
            groups.setdefault(stock.sector, []).append(stock)

    snapshots: list[DailySectorSnapshot] = []
    for sector, sector_stocks in groups.items():
        if not sector_stocks:
            continue
        avg_pct = _quantize(
            sum((stock.pct_change for stock in sector_stocks), Decimal("0"))
            / Decimal(len(sector_stocks))
        )
        leaders = [
            stock.symbol
            for stock in sorted(
                sector_stocks,
                key=lambda item: item.pct_change,
                reverse=True,
            )[:5]
        ]
        snapshots.append(
            DailySectorSnapshot(
                sector_name=sector,
                trade_date=sector_stocks[0].trade_date,
                pct_change=avg_pct,
                turnover_amount=sum(
                    (stock.amount for stock in sector_stocks),
                    Decimal("0"),
                ),
                advance_count=sum(1 for stock in sector_stocks if stock.pct_change > 0),
                decline_count=sum(1 for stock in sector_stocks if stock.pct_change < 0),
                leader_symbols=leaders,
                provider="inferred_from_stock_snapshot",
            )
        )
    return snapshots


def _sector_signal_from_snapshot(snapshot: DailySectorSnapshot) -> SectorRotationSignal:
    active_count = snapshot.advance_count + snapshot.decline_count
    internal_ratio = (
        Decimal(snapshot.advance_count) / Decimal(active_count)
        if active_count
        else Decimal("0")
    )
    risk_tags = []
    if internal_ratio < Decimal("0.35"):
        risk_tags.append("weak_internal_breadth")

    score = _clamp(
        snapshot.pct_change * Decimal("10")
        + min(Decimal("30"), snapshot.turnover_amount / Decimal("1000000000"))
        + internal_ratio * Decimal("40")
    )
    status = _sector_status(snapshot.pct_change, internal_ratio)
    return SectorRotationSignal(
        theme=snapshot.sector_name,
        score=score,
        status=status,
        leader_symbols=list(snapshot.leader_symbols),
        risk_tags=risk_tags,
        evidence_payload={
            "pct_change": str(snapshot.pct_change),
            "turnover_amount": str(snapshot.turnover_amount),
            "advance_count": snapshot.advance_count,
            "decline_count": snapshot.decline_count,
            "internal_ratio": str(_quantize(internal_ratio)),
        },
    )


def _sector_status(pct_change: Decimal, internal_ratio: Decimal) -> str:
    if pct_change < 0:
        return "weak"
    if pct_change >= Decimal("2") and internal_ratio >= Decimal("0.55"):
        return "mainline_strong"
    if pct_change > 0 and internal_ratio < Decimal("0.35"):
        return "mainline_divergence"
    return "defensive"


def _sector_by_symbol(signals: list[SectorRotationSignal]) -> dict[str, str]:
    result: dict[str, str] = {}
    for signal in signals:
        for symbol in signal.leader_symbols:
            result.setdefault(symbol, signal.theme)
    return result


def _anomaly_score_by_symbol(
    anomalies: list[DailyIntradayAnomaly],
) -> dict[str, Decimal]:
    result: dict[str, Decimal] = {}
    for anomaly in anomalies:
        result[anomaly.symbol] = result.get(anomaly.symbol, Decimal("0")) + anomaly.strength_score
    return result


def _event_penalty_by_symbol(catalysts: list[DailyEventCatalyst]) -> dict[str, Decimal]:
    result: dict[str, Decimal] = {}
    for catalyst in catalysts:
        if catalyst.sentiment != "negative":
            continue
        penalty = catalyst.trust_score * Decimal("20")
        for symbol in catalyst.related_symbols:
            result[symbol] = result.get(symbol, Decimal("0")) + penalty
    return result


def _leader_score_from_stock(
    stock: DailyStockSnapshot,
    sector_name: str,
    sector_anchor: bool,
    limit_snapshot: DailyLimitUpSnapshot | None,
    lhb_snapshot: DailyLhbSnapshot | None,
    lhb_seat_payload: dict[str, Any],
    anomaly_score: Decimal,
    event_penalty: Decimal,
) -> LeaderScore:
    score = Decimal("50") + stock.pct_change * Decimal("2")
    role = "trend_core" if stock.pct_change > 0 else "risk_watch"
    if sector_anchor:
        score += Decimal("25")
        role = "sector_anchor"
    if limit_snapshot is not None:
        score += Decimal(limit_snapshot.board_count * 8)
        if limit_snapshot.board_count >= 3:
            role = "limit_up_height"
    if lhb_snapshot is not None and lhb_snapshot.net_buy_amount > 0:
        score += min(Decimal("12"), lhb_snapshot.net_buy_amount / Decimal("10000000"))
    capital_type = str(lhb_seat_payload.get("capital_type", "none"))
    if capital_type == "institution_net_buy":
        score += Decimal("10")
        role = "institution_lhb"
    elif capital_type == "hot_money_net_buy":
        score += Decimal("6")
        if role == "trend_core":
            role = "hot_money_lhb"
    elif capital_type == "net_sell":
        score -= Decimal("8")
    if bool(lhb_seat_payload.get("concentration_risk")):
        score -= Decimal("6")
    score += min(Decimal("15"), anomaly_score)
    score -= event_penalty
    score = _clamp(score)

    watch_action = _watch_action(role=role, score=score)
    return LeaderScore(
        symbol=stock.symbol,
        name=stock.name,
        role=role,
        score=score,
        watch_action=watch_action,
        entry_condition=_entry_condition(watch_action),
        avoid_condition="高开加速、放量走弱或板块内部明显分化",
        position_rule="只作为次日观察计划，不直接生成订单",
        evidence_payload={
            "sector": sector_name,
            "pct_change": str(stock.pct_change),
            "limit_board_count": (
                limit_snapshot.board_count if limit_snapshot is not None else 0
            ),
            "lhb_net_buy_amount": (
                str(lhb_snapshot.net_buy_amount) if lhb_snapshot is not None else "0"
            ),
            "lhb_reason_category": str(
                lhb_seat_payload.get("reason_category", "")
            ),
            "capital_type": capital_type,
            "lhb_summary": _lhb_summary_text(lhb_seat_payload),
            "concentration_risk": bool(lhb_seat_payload.get("concentration_risk")),
            "anomaly_score": str(anomaly_score),
            "event_penalty": str(event_penalty),
        },
    )


def _watch_action(role: str, score: Decimal) -> str:
    if role == "risk_watch" or score < Decimal("45"):
        return "avoid"
    if role == "limit_up_height":
        return "observe_divergence"
    if score >= Decimal("70"):
        return "wait_pullback"
    return "low_level_rotation"


def _entry_condition(watch_action: str) -> str:
    if watch_action == "avoid":
        return "不新开仓，仅观察风险是否释放"
    if watch_action == "observe_divergence":
        return "分歧换手后仍能维持强承接"
    if watch_action == "wait_pullback":
        return "回踩关键均线或分时承接稳定后再观察"
    return "低位补涨确认并放量站稳"


def _capital_type(
    institution_net: Decimal,
    hot_money_net: Decimal,
    lhb_net: Decimal,
) -> str:
    if institution_net > 0:
        return "institution_net_buy"
    if institution_net < 0:
        return "institution_net_sell"
    if hot_money_net > 0:
        return "hot_money_net_buy"
    if lhb_net < 0:
        return "net_sell"
    if lhb_net > 0:
        return "mixed_net_buy"
    return "none"


def _has_concentration_risk(snapshot: DailyLhbSnapshot) -> bool:
    return bool(
        (snapshot.turnover_ratio is not None and snapshot.turnover_ratio >= Decimal("25"))
        or (
            snapshot.net_buy_ratio is not None
            and abs(snapshot.net_buy_ratio) >= Decimal("15")
        )
        or (snapshot.turnover_rate is not None and snapshot.turnover_rate >= Decimal("30"))
    )


def _lhb_summary_text(payload: dict[str, Any]) -> str:
    if not payload:
        return ""
    return (
        f"reason={payload.get('reason_category', 'unknown')}; "
        f"capital={payload.get('capital_type', 'none')}; "
        f"lhb_net={payload.get('net_buy_amount', '0')}; "
        f"institution_net={payload.get('institution_net_amount', '0')}; "
        f"turnover_ratio={payload.get('turnover_ratio', '')}; "
        f"risk={payload.get('concentration_risk', False)}"
    )


def _decimal_to_text(value: Decimal | None) -> str:
    return "" if value is None else str(value)


def _clamp(value: Decimal) -> Decimal:
    return _quantize(max(Decimal("0"), min(Decimal("100"), value)))


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
