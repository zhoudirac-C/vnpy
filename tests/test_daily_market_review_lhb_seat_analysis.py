from datetime import UTC, date, datetime
from decimal import Decimal

import pytest


def test_lhb_domain_validates_success_rate_bounds():
    """龙虎榜席位成功率必须落在 0-100 之间。"""
    from vnpy_daily_review.domain import DailyLhbStockSeatSnapshot

    with pytest.raises(ValueError, match="success_rate"):
        DailyLhbStockSeatSnapshot(
            symbol="000062.SZSE",
            trade_date=date(2026, 5, 11),
            side="buy",
            seat_name="机构专用",
            amount=Decimal("1000000"),
            success_rate=Decimal("101"),
            provider="fake",
        )

    snapshot = DailyLhbStockSeatSnapshot(
        symbol="000062.SZSE",
        trade_date=date(2026, 5, 11),
        side="buy",
        seat_name="机构专用",
        amount=Decimal("1000000"),
        success_rate=Decimal("48.16"),
        provider="fake",
    )

    assert snapshot.success_rate == Decimal("48.16")


def test_daily_review_provider_loads_lhb_institution_and_seat_data(monkeypatch):
    """AKShare provider 应补充机构买卖、活跃营业部和个股席位明细。"""
    import vnpy_daily_review.providers as provider_module
    from vnpy_daily_review.providers import VnpyAkshareDailyReviewProvider

    class FakeMainEngine:
        def get_all_ticks(self):
            return []

        def get_contract(self, vt_symbol):
            del vt_symbol
            return None

    class FakeAkshare:
        def stock_zh_a_spot_em(self):
            return [
                {
                    "代码": "000062",
                    "名称": "深圳华强",
                    "最新价": 39.09,
                    "今开": 38,
                    "最高": 39.09,
                    "最低": 37.5,
                    "涨跌幅": 9.9887,
                    "成交量": 1000,
                    "成交额": 100000,
                }
            ]

        def stock_board_industry_name_em(self):
            return []

        def stock_zt_pool_em(self, date):
            del date
            return []

        def stock_lhb_detail_em(self, start_date, end_date):
            del start_date, end_date
            return [
                {
                    "代码": "000062",
                    "名称": "深圳华强",
                    "龙虎榜买入额": 673637900,
                    "龙虎榜卖出额": 198561200,
                    "龙虎榜净买额": 475076700,
                    "龙虎榜成交额": 872199100,
                    "市场总成交额": 3100000000,
                    "净买额占总成交比": 15.32,
                    "成交额占总成交比": 28.14,
                    "换手率": 22.4,
                    "上榜原因": "日涨幅偏离值达到7%的前5只证券",
                    "解读": "3家机构买入，成功率48.16%",
                }
            ]

        def stock_lhb_jgmmtj_em(self, start_date, end_date):
            del start_date, end_date
            return [
                {
                    "代码": "000062",
                    "名称": "深圳华强",
                    "买方机构数": 3,
                    "卖方机构数": 1,
                    "机构买入总额": 320000000,
                    "机构卖出总额": 20000000,
                    "机构买入净额": 300000000,
                    "上榜原因": "日涨幅偏离值达到7%的前5只证券",
                }
            ]

        def stock_lhb_hyyyb_em(self, start_date, end_date):
            del start_date, end_date
            return [
                {
                    "营业部名称": "东方财富证券拉萨团结路第二证券营业部",
                    "上榜日": 2,
                    "买入个股数": 4,
                    "卖出个股数": 3,
                    "买入总金额": 80000000,
                    "卖出总金额": 20000000,
                    "总买卖净额": 60000000,
                    "买入股票": "深圳华强,大众交通",
                }
            ]

        def stock_lhb_stock_detail_em(self, symbol, date, flag):
            assert symbol == "000062"
            assert date == "20260511"
            assert flag in {"买入", "卖出"}
            return [
                {
                    "营业部名称": "机构专用" if flag == "买入" else "深股通专用",
                    "买入金额": 120000000 if flag == "买入" else 0,
                    "卖出金额": 0 if flag == "买入" else 50000000,
                    "成功率": "48.16%",
                }
            ]

    monkeypatch.setattr(provider_module, "import_module", lambda name: FakeAkshare())

    bundle = VnpyAkshareDailyReviewProvider(FakeMainEngine()).load_data_bundle(
        date(2026, 5, 11)
    )

    assert bundle.lhb[0].reason_category == "price_deviation"
    assert bundle.lhb[0].turnover_ratio == Decimal("28.14")
    assert bundle.lhb_institutions[0].net_amount == Decimal("300000000")
    assert bundle.lhb_active_seats[0].seat_type_hint == "hot_money"
    assert bundle.lhb_stock_seats[0].seat_type_hint == "institution"
    assert bundle.lhb_stock_seats[0].success_rate == Decimal("48.16")
    assert any(
        record["data_type"] == "lhb_stock_seat_snapshot"
        and record["status"] == "success"
        for record in bundle.provider_records
    )


def test_lhb_seat_signal_enters_evidence_pack_and_leader_payload():
    """席位拆解应该影响风向标评分，并进入 Evidence Pack。"""
    from vnpy_daily_review.domain import (
        DailyLhbActiveSeatSnapshot,
        DailyLhbInstitutionSnapshot,
        DailyLhbSnapshot,
        DailyLhbStockSeatSnapshot,
        DailyStockSnapshot,
    )
    from vnpy_daily_review.evidence import EvidencePackBuilder
    from vnpy_daily_review.signals import (
        LeaderScoringEngine,
        LhbSeatAnalysisEngine,
        MarketBreadthEngine,
        SectorRotationEngine,
    )

    trade_date = date(2026, 5, 11)
    stock = DailyStockSnapshot(
        symbol="000062.SZSE",
        name="深圳华强",
        trade_date=trade_date,
        open_price=Decimal("38"),
        high_price=Decimal("39.09"),
        low_price=Decimal("37.5"),
        close_price=Decimal("39.09"),
        pct_change=Decimal("9.99"),
        volume=1000,
        amount=Decimal("100000000"),
        turnover_rate=Decimal("22.4"),
        is_limit_up=True,
        is_limit_down=False,
        provider="fake",
        sector="AI硬件",
    )
    lhb = DailyLhbSnapshot(
        symbol=stock.symbol,
        name=stock.name,
        trade_date=trade_date,
        buy_amount=Decimal("673637900"),
        sell_amount=Decimal("198561200"),
        net_buy_amount=Decimal("475076700"),
        seat_tags=["日涨幅偏离值达到7%的前5只证券"],
        provider="fake",
        reason_category="price_deviation",
        net_buy_ratio=Decimal("15.32"),
        turnover_ratio=Decimal("28.14"),
    )
    institution = DailyLhbInstitutionSnapshot(
        symbol=stock.symbol,
        name=stock.name,
        trade_date=trade_date,
        buy_institution_count=3,
        sell_institution_count=1,
        buy_amount=Decimal("320000000"),
        sell_amount=Decimal("20000000"),
        net_amount=Decimal("300000000"),
        list_reason="日涨幅偏离值达到7%的前5只证券",
        provider="fake",
    )
    active_seat = DailyLhbActiveSeatSnapshot(
        seat_name="东方财富证券拉萨团结路第二证券营业部",
        trade_date=trade_date,
        list_day_count=2,
        buy_stock_count=4,
        sell_stock_count=3,
        buy_amount=Decimal("80000000"),
        sell_amount=Decimal("20000000"),
        net_amount=Decimal("60000000"),
        buy_symbols=["深圳华强"],
        provider="fake",
    )
    stock_seat = DailyLhbStockSeatSnapshot(
        symbol=stock.symbol,
        trade_date=trade_date,
        side="buy",
        seat_name="机构专用",
        amount=Decimal("120000000"),
        success_rate=Decimal("48.16"),
        provider="fake",
    )
    seat_signal = LhbSeatAnalysisEngine().calculate(
        lhb_snapshots=[lhb],
        institution_snapshots=[institution],
        active_seats=[active_seat],
        stock_seats=[stock_seat],
    )
    sector_signals = SectorRotationEngine().calculate([], [stock])
    leaders = LeaderScoringEngine().calculate(
        stock_snapshots=[stock],
        sector_signals=sector_signals,
        limit_up_snapshots=[],
        lhb_snapshots=[lhb],
        lhb_seat_signal=seat_signal,
        intraday_anomalies=[],
        event_catalysts=[],
    )
    pack = EvidencePackBuilder().build(
        trade_date=trade_date,
        market_signal=MarketBreadthEngine().calculate([stock]),
        sector_signals=sector_signals,
        leader_candidates=leaders,
        lhb_seat_signal=seat_signal,
    )

    assert leaders[0].evidence_payload["capital_type"] == "institution_net_buy"
    assert leaders[0].evidence_payload["lhb_reason_category"] == "price_deviation"
    assert any(item.source_type == "lhb_seat_analysis" for item in pack.evidence)
    assert pack.leader_candidates[0]["capital_type"] == "institution_net_buy"


def test_repository_restores_watch_item_lhb_extra_fields():
    """从结构化报告恢复观察计划时，不能丢失 AI/龙虎榜扩展字段。"""
    from vnpy_daily_review.engine import DailyMarketReviewReportResult
    from vnpy_daily_review.storage import InMemoryDailyReviewRepository

    result = DailyMarketReviewReportResult(
        status="completed",
        trade_date=date(2026, 5, 11),
        title="2026-05-11 每日市场复盘",
        markdown="## report",
        watch_items=[
            {
                "symbol": "000062.SZSE",
                "name": "深圳华强",
                "role": "institution_lhb",
                "watch_action": "wait_pullback",
                "entry_condition": "回踩承接",
                "avoid_condition": "高开加速",
                "position_rule": "只观察",
                "capital_type": "institution_net_buy",
                "lhb_summary": "机构净买 3.00 亿",
                "evidence_ids": ["EVT-1"],
            }
        ],
        audit=[
            {
                "mode": "deterministic",
                "created_at": datetime.now(UTC).isoformat(),
            }
        ],
    )
    repository = InMemoryDailyReviewRepository()
    repository.save_report_result(result)

    restored = repository.load_latest_report()

    assert restored is not None
    assert restored.watch_items[0]["capital_type"] == "institution_net_buy"
    assert restored.watch_items[0]["lhb_summary"] == "机构净买 3.00 亿"
