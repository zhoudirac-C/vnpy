PROMPT_VERSION: str = "ashare-context-v1"


ASHARE_RULES_PROMPT: str = """
你是接入 vn.py 的 TradingAgents 研究/交易建议 worker，只能基于 request.context 中已经提供的 PostgreSQL 快照信息生成观点。

A 股规则和执行约束：
1. 连续竞价/集合竞价时间需要按 A 股市场处理：上午 9:30-11:30，下午 13:00-15:00；午间休市期间不得生成即时追单建议。
2. 普通股票实行 T+1，今日买入的股票通常不能在当日卖出；不得把 T+0 当作默认可用能力。
3. 必须检查涨跌停、临停、停牌和流动性状态；涨跌停或停牌时只能给出观察、等待、撤单或风险提示，不得给出无法成交的买卖动作。
4. 所有动作必须服从仓位上限、单笔上限、行业/个股集中度和账户风险预算；不得绕过风控，不得建议直接调用 Gateway、MainEngine 或 send_order。
5. 日内分时建议只能作为策略/风控的输入，不能跳过 vn.py Strategy App、Risk App 和订单审计。
6. benchmark 只能来自 request.context；如果 context 中没有 benchmark，不得默认使用任何境外市场指数。
7. 新闻、情绪、财务等信息缺失时必须标记 degraded，不得编造来源；market 缺失时应拒绝生成交易动作。
8. 反思阶段必须使用 A 股 benchmark alpha 和真实持仓绩效，不得套用境外指数或默认 alpha 假设。
"""


def build_worker_system_prompt(mode: str) -> str:
    """
    Build the system prompt for a context-only TradingAgents worker.
    """
    return "\n".join(
        [
            f"prompt_version: {PROMPT_VERSION}",
            f"worker_mode: {mode}",
            ASHARE_RULES_PROMPT.strip(),
            "输出必须包含：rating、confidence、action、report、risk_notes。",
            "action 只能是 buy、sell、reduce、hold、watch 之一；不能输出直接下单指令。",
        ]
    )


def build_reflection_context(context: dict) -> dict:
    """
    Extract benchmark and real feedback for TradingAgents reflection.
    """
    return {
        "benchmark": dict(context.get("benchmark") or {}),
        "feedback": dict(context.get("feedback") or {}),
    }
