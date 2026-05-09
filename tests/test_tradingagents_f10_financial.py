import json
import pytest


def test_context_financial_statement_tools_read_nested_financials():
    """TradingAgents context tools should expose vn.py financial statement snapshots."""
    from vnpy_tradingagents.tradingagents_factory import (
        _CURRENT_CONTEXT,
        get_context_balance_sheet,
        get_context_cashflow,
        get_context_income_statement,
    )

    token = _CURRENT_CONTEXT.set(
        {
            "financials": {
                "statements": {
                    "balance_sheet": {
                        "report_period": "2024-12-31",
                        "fields": {"TOTAL_ASSETS": 319918.0},
                    },
                    "cash_flow": {
                        "report_period": "2024-12-31",
                        "fields": {"NETCASH_OPERATE": 26971.0},
                    },
                    "income_statement": {
                        "report_period": "2024-12-31",
                        "fields": {"OPERATE_INCOME": 53909.0},
                    },
                }
            }
        }
    )
    try:
        balance = _tool_payload(
            get_context_balance_sheet("600519.SSE", curr_date="2025-04-02")
        )
        cashflow = _tool_payload(get_context_cashflow("600519.SSE", curr_date="2025-04-02"))
        income = _tool_payload(
            get_context_income_statement("600519.SSE", curr_date="2025-04-02")
        )
    finally:
        _CURRENT_CONTEXT.reset(token)

    assert balance["data"]["fields"]["TOTAL_ASSETS"] == 319918.0
    assert cashflow["data"]["fields"]["NETCASH_OPERATE"] == 26971.0
    assert income["data"]["fields"]["OPERATE_INCOME"] == 53909.0


def test_f10_financial_analyzer_builds_dupont_cash_quality_and_missing_fields():
    """F10 analyzer should produce deterministic financial bottom-sheet context."""
    from vnpy_tradingagents.f10_financial import F10FinancialAnalyzer

    analysis = F10FinancialAnalyzer().analyze(
        vt_symbol="600519.SSE",
        financials={
            "quality_status": "primary",
            "statements": {
                "income_statement": {
                    "report_period": "2024-12-31",
                    "fields": {"OPERATE_INCOME": 53909.0, "NETPROFIT": 28134.0},
                },
                "cash_flow": {
                    "report_period": "2024-12-31",
                    "fields": {"NETCASH_OPERATE": 26971.0},
                },
                "balance_sheet": {
                    "report_period": "2024-12-31",
                    "fields": {
                        "TOTAL_ASSETS": 319918.0,
                        "TOTAL_LIABILITIES": 38782.0,
                        "TOTAL_PARENT_EQUITY": 281136.0,
                    },
                },
            },
            "indicators": [
                {
                    "report_period": "2024-12-31",
                    "fields": {
                        "ROEJQ": 10.57,
                        "XSMLL": 89.76,
                        "XSJLL": 52.22,
                        "ZCFZL": 12.12,
                    },
                }
            ],
        },
        fundamentals={},
        valuation={},
    )

    assert analysis["methodology_version"] == "f10-financial-v1"
    assert analysis["profitability"]["revenue"] == 53909.0
    assert analysis["profitability"]["roe"] == 10.57
    assert analysis["dupont"]["net_margin"] == 52.22
    assert analysis["dupont"]["asset_turnover"] == pytest.approx(53909.0 / 319918.0)
    assert analysis["dupont"]["equity_multiplier"] == pytest.approx(319918.0 / 281136.0)
    assert analysis["cash_quality"]["operating_cash_flow_to_net_profit"] == pytest.approx(
        26971.0 / 28134.0
    )
    assert analysis["valuation_methods"]["PE"]["ready"] is False
    assert analysis["valuation_methods"]["PB"]["ready"] is False
    assert analysis["valuation_methods"]["PS"]["ready"] is False
    assert "valuation_provider_missing" in analysis["missing_fields"]


def _tool_payload(value: str) -> dict:
    return json.loads(value.split("\n", 1)[1])
