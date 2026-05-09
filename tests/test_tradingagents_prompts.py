def test_ashare_rules_prompt_contains_required_market_constraints():
    """A-share prompt should include concrete trading and risk constraints."""
    from vnpy_tradingagents.prompts import ASHARE_RULES_PROMPT

    assert "9:30" in ASHARE_RULES_PROMPT
    assert "11:30" in ASHARE_RULES_PROMPT
    assert "13:00" in ASHARE_RULES_PROMPT
    assert "15:00" in ASHARE_RULES_PROMPT
    assert "T+1" in ASHARE_RULES_PROMPT
    assert "涨跌停" in ASHARE_RULES_PROMPT
    assert "停牌" in ASHARE_RULES_PROMPT
    assert "仓位上限" in ASHARE_RULES_PROMPT
    assert "不得绕过风控" in ASHARE_RULES_PROMPT


def test_worker_system_prompt_does_not_assume_us_benchmark():
    """Worker prompt should not bake in US-market benchmark assumptions."""
    from vnpy_tradingagents.prompts import build_worker_system_prompt

    prompt = build_worker_system_prompt(mode="intraday_advice")
    upper_prompt = prompt.upper()

    assert "SPY" not in upper_prompt
    assert "S&P" not in upper_prompt
    assert "NASDAQ" not in upper_prompt
    assert "美股" not in prompt
    assert "benchmark 只能来自 request.context" in prompt


def test_worker_system_prompt_contains_f10_financial_methodology():
    """Worker prompt should force financial analysis to follow the local F10 method."""
    from vnpy_tradingagents.prompts import build_worker_system_prompt

    prompt = build_worker_system_prompt(mode="long_horizon")

    assert "F10财务分析方法论" in prompt
    assert "公司类型" in prompt
    assert "PE" in prompt
    assert "PB" in prompt
    assert "PEG" in prompt
    assert "PS" in prompt
    assert "杜邦" in prompt
    assert "现金流" in prompt
    assert "字段缺失" in prompt
