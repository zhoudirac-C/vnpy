from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


F10_METHODOLOGY_VERSION = "f10-financial-v1"


class F10FinancialAnalyzer:
    """
    Build deterministic F10 financial-analysis context from stored snapshots.
    """

    def analyze(
        self,
        vt_symbol: str,
        financials: Mapping[str, Any] | None,
        fundamentals: Mapping[str, Any] | None = None,
        valuation: Mapping[str, Any] | None = None,
        industry: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Convert raw financial statements into the F10 bottom sheet used by LLM workers.
        """
        financials = financials or {}
        fundamentals = fundamentals or {}
        valuation = valuation or {}
        industry = industry or {}

        income = _fields(_latest_statement(financials, "income_statement"))
        cash_flow = _fields(_latest_statement(financials, "cash_flow", "cashflow"))
        balance = _fields(_latest_statement(financials, "balance_sheet"))
        indicator = _latest_indicator_fields(financials)

        revenue = _metric(
            income,
            aliases=("OPERATE_INCOME", "TOTAL_OPERATE_INCOME", "营业收入", "营业总收入", "revenue"),
            fallback=_compact_metric(fundamentals, "revenue"),
        )
        net_profit = _metric(
            income,
            aliases=("NETPROFIT", "PARENT_NETPROFIT", "净利润", "归母净利润", "net_profit"),
            fallback=_compact_metric(fundamentals, "net_profit"),
        )
        operating_cash_flow = _metric(
            cash_flow,
            aliases=(
                "NETCASH_OPERATE",
                "经营活动产生的现金流量净额",
                "经营现金流量净额",
                "operating_cash_flow",
            ),
            fallback=_compact_metric(fundamentals, "operating_cash_flow"),
        )
        total_assets = _metric(
            balance,
            aliases=("TOTAL_ASSETS", "资产总计", "总资产", "total_assets"),
            fallback=_compact_metric(fundamentals, "total_assets"),
        )
        total_liabilities = _metric(
            balance,
            aliases=("TOTAL_LIABILITIES", "负债合计", "总负债", "total_liabilities"),
            fallback=_compact_metric(fundamentals, "total_liabilities"),
        )
        total_equity = _metric(
            balance,
            aliases=(
                "TOTAL_PARENT_EQUITY",
                "TOTAL_EQUITY",
                "PARENT_EQUITY_BALANCE",
                "所有者权益合计",
                "净资产",
                "total_equity",
            ),
        )
        if total_equity is None and total_assets is not None and total_liabilities is not None:
            total_equity = total_assets - total_liabilities

        roe = _metric(
            indicator,
            aliases=("ROEJQ", "ROE", "净资产收益率", "roe"),
            fallback=_compact_metric(fundamentals, "roe"),
        )
        gross_margin = _metric(
            indicator,
            aliases=("XSMLL", "销售毛利率", "毛利率", "gross_margin"),
            fallback=_compact_metric(fundamentals, "gross_margin"),
        )
        net_margin = _metric(
            indicator,
            aliases=("XSJLL", "销售净利率", "净利率", "net_margin"),
            fallback=_ratio_percent(net_profit, revenue),
        )
        debt_to_assets = _metric(
            indicator,
            aliases=("ZCFZL", "资产负债率", "debt_to_assets"),
            fallback=_ratio_percent(total_liabilities, total_assets),
        )
        asset_turnover = _metric(
            indicator,
            aliases=("TOAZZL", "总资产周转率", "asset_turnover"),
            fallback=_ratio(revenue, total_assets),
        )
        equity_multiplier = _ratio(total_assets, total_equity)
        cash_profit_ratio = _ratio(operating_cash_flow, net_profit)

        revenue_yoy = _metric(
            income,
            aliases=("OPERATE_INCOME_YOY", "TOTAL_OPERATE_INCOME_YOY", "营业收入同比增长率"),
        )
        net_profit_yoy = _metric(
            income,
            aliases=("NETPROFIT_YOY", "PARENT_NETPROFIT_YOY", "净利润同比增长率"),
        )
        operating_cash_flow_yoy = _metric(
            cash_flow,
            aliases=("NETCASH_OPERATE_YOY", "经营现金流同比增长率"),
        )

        missing_fields = _missing_fields(
            {
                "revenue": revenue,
                "net_profit": net_profit,
                "operating_cash_flow": operating_cash_flow,
                "total_assets": total_assets,
                "total_liabilities": total_liabilities,
                "total_equity": total_equity,
                "roe": roe,
                "gross_margin": gross_margin,
                "net_margin": net_margin,
                "asset_turnover": asset_turnover,
            }
        )
        if _valuation_is_missing(valuation):
            missing_fields.append("valuation_provider_missing")
        if not industry:
            missing_fields.append("industry_context_missing")

        return {
            "methodology_version": F10_METHODOLOGY_VERSION,
            "vt_symbol": vt_symbol,
            "quality_status": financials.get("quality_status") or fundamentals.get("quality_status"),
            "company_type": _company_type(industry),
            "profitability": {
                "revenue": revenue,
                "net_profit": net_profit,
                "roe": roe,
                "gross_margin": gross_margin,
                "net_margin": net_margin,
            },
            "balance_sheet": {
                "total_assets": total_assets,
                "total_liabilities": total_liabilities,
                "total_equity": total_equity,
                "debt_to_assets": debt_to_assets,
                "cash": _metric(balance, aliases=("MONETARYFUNDS", "货币资金", "cash")),
                "receivables": _metric(balance, aliases=("ACCOUNTS_RECE", "应收账款")),
                "inventory": _metric(balance, aliases=("INVENTORY", "存货")),
            },
            "cash_quality": {
                "operating_cash_flow": operating_cash_flow,
                "operating_cash_flow_to_net_profit": cash_profit_ratio,
                "assessment": _cash_quality_assessment(cash_profit_ratio),
            },
            "dupont": {
                "net_margin": net_margin,
                "asset_turnover": asset_turnover,
                "equity_multiplier": equity_multiplier,
                "computed_roe": _computed_roe(net_margin, asset_turnover, equity_multiplier),
            },
            "growth_quality": {
                "revenue_yoy": revenue_yoy,
                "net_profit_yoy": net_profit_yoy,
                "operating_cash_flow_yoy": operating_cash_flow_yoy,
                "sync_check": _growth_sync_check(revenue_yoy, net_profit_yoy, operating_cash_flow_yoy),
            },
            "valuation_methods": _valuation_method_readiness(
                valuation=valuation,
                revenue=revenue,
                net_profit=net_profit,
                total_equity=total_equity,
                gross_margin=gross_margin,
            ),
            "missing_fields": _dedup(missing_fields),
            "analysis_checklist": [
                "先判断公司类型，再选择 PE/PB/PEG/PS。",
                "三大报表交叉验证收入、利润、资产负债和现金流。",
                "ROE 必须拆成净利率、资产周转率、权益乘数。",
                "净利润必须和经营现金流一起看，警惕纸面利润。",
                "字段缺失时标记 degraded，不得编造估值或财务来源。",
            ],
        }


def _latest_statement(financials: Mapping[str, Any], *names: str) -> Mapping[str, Any]:
    statements = financials.get("statements")
    if not isinstance(statements, Mapping):
        return {}
    for name in names:
        value = statements.get(name)
        if isinstance(value, Mapping):
            return value
    return {}


def _fields(row: Mapping[str, Any]) -> Mapping[str, Any]:
    fields = row.get("fields")
    if isinstance(fields, Mapping):
        return fields
    raw_fields = row.get("raw_fields")
    if isinstance(raw_fields, Mapping):
        return raw_fields
    return row


def _latest_indicator_fields(financials: Mapping[str, Any]) -> Mapping[str, Any]:
    indicators = financials.get("indicators")
    if isinstance(indicators, Mapping):
        return _fields(indicators)
    if isinstance(indicators, Sequence) and not isinstance(indicators, (str, bytes, bytearray)):
        for item in indicators:
            if isinstance(item, Mapping):
                return _fields(item)
    return {}


def _metric(
    source: Mapping[str, Any],
    *,
    aliases: Sequence[str],
    fallback: float | None = None,
) -> float | None:
    for alias in aliases:
        value = source.get(alias)
        converted = _to_float(value)
        if converted is not None:
            return converted
    return fallback


def _compact_metric(source: Mapping[str, Any], key: str) -> float | None:
    value = source.get(key)
    if isinstance(value, Mapping):
        return _to_float(value.get("current"))
    return _to_float(value)


def _to_float(value: Any) -> float | None:
    if value in (None, "", "--"):
        return None
    try:
        return float(str(value).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def _ratio_percent(numerator: float | None, denominator: float | None) -> float | None:
    value = _ratio(numerator, denominator)
    if value is None:
        return None
    return value * 100


def _computed_roe(
    net_margin: float | None,
    asset_turnover: float | None,
    equity_multiplier: float | None,
) -> float | None:
    if net_margin is None or asset_turnover is None or equity_multiplier is None:
        return None
    return (net_margin / 100) * asset_turnover * equity_multiplier * 100


def _cash_quality_assessment(value: float | None) -> str:
    if value is None:
        return "missing"
    if value >= 1:
        return "strong"
    if value >= 0.8:
        return "acceptable"
    return "weak"


def _growth_sync_check(*values: float | None) -> str:
    known = [value for value in values if value is not None]
    if len(known) < 2:
        return "insufficient"
    if min(known) >= 0:
        return "aligned_positive"
    if max(known) <= 0:
        return "aligned_negative"
    return "divergent"


def _company_type(industry: Mapping[str, Any]) -> dict[str, Any]:
    industry_name = str(
        industry.get("industry")
        or industry.get("industry_name")
        or industry.get("sector")
        or ""
    )
    if not industry_name:
        return {"value": "unknown", "reason": "industry_context_missing"}
    return {"value": "industry_based", "industry": industry_name}


def _valuation_method_readiness(
    *,
    valuation: Mapping[str, Any],
    revenue: float | None,
    net_profit: float | None,
    total_equity: float | None,
    gross_margin: float | None,
) -> dict[str, Any]:
    market_cap = _any_metric(valuation, "market_cap", "total_market_cap", "总市值")
    pe = _any_metric(valuation, "pe", "pe_ttm", "PE_TTM")
    pb = _any_metric(valuation, "pb", "PB")
    ps = _any_metric(valuation, "ps", "PS")
    forecast_growth = _any_metric(valuation, "forecast_growth", "expected_profit_growth")

    pe_ready = pe is not None or (market_cap is not None and net_profit is not None)
    pb_ready = pb is not None or (market_cap is not None and total_equity is not None)
    ps_ready = ps is not None or (market_cap is not None and revenue is not None)
    peg_ready = _any_metric(valuation, "peg", "PEG") is not None or (
        pe_ready and forecast_growth is not None
    )
    return {
        "PE": {"ready": pe_ready, "reason": "stable_profit_required"},
        "PB": {"ready": pb_ready, "reason": "asset_quality_required"},
        "PEG": {"ready": peg_ready, "reason": "forecast_growth_required"},
        "PS": {
            "ready": ps_ready,
            "reason": "market_cap_revenue_and_margin_required",
            "gross_margin_available": gross_margin is not None,
        },
    }


def _any_metric(source: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _to_float(source.get(key))
        if value is not None:
            return value
    return None


def _valuation_is_missing(valuation: Mapping[str, Any]) -> bool:
    if not valuation:
        return True
    missing = valuation.get("missing_fields")
    if isinstance(missing, Sequence) and "valuation_provider_missing" in missing:
        return True
    return not any(_any_metric(valuation, key) is not None for key in ("pe", "pe_ttm", "pb", "ps"))


def _missing_fields(values: Mapping[str, Any]) -> list[str]:
    return [key for key, value in values.items() if value is None]


def _dedup(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result
