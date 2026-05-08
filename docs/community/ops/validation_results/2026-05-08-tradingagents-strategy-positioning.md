# P27 TradingAgents 独立 AI 策略定位验证结果

日期：2026-05-08

## 验证目标

- TradingAgents 手动分析入口只生成报告、评级和交易意图，不直接下单。
- `TradingAgentsSignalStrategy` 作为独立 AI 策略读取已落库意图，`hold/watch` 不会被当成订单。
- `TradingAgentsBacktestStrategy` 只读取历史时点已固化 AI 信号，不在回测循环里调用 LLM。
- 历史 AI 信号通过 `HistoricalAiSignalJob` 预生成并落库，供后续回测读取。
- 传统规则策略不被本次改动隐式接入 TradingAgents。

## 验证命令

```bash
uv run --with pytest pytest \
  tests/test_tradingagents_manual_analysis.py \
  tests/test_tradingagents_signal_strategy.py \
  tests/test_tradingagents_backtest_strategy.py \
  tests/test_vnpy_cta_strategy_ai_isolation.py \
  -q
```

结果：

```text
16 passed
```

```bash
uv run --with pytest pytest \
  tests/test_tradingagents_manual_analysis.py \
  tests/test_tradingagents_signal_strategy.py \
  tests/test_tradingagents_backtest_strategy.py \
  tests/test_tradingagents_storage_service.py \
  tests/test_tradingagents_ui.py \
  tests/test_tradingagents_runtime.py \
  tests/test_tradingagents_strategy_mixin.py \
  tests/test_tradingagents_llm_secret_ui.py \
  -q
```

结果：

```text
45 passed
```

```bash
uv run --with pytest pytest tests/test_tradingagents_*.py tests/test_vnpy_cta_strategy_ai_isolation.py -q
```

结果：

```text
177 passed
```

```bash
uv run --with ruff ruff check \
  vnpy_tradingagents \
  vnpy/trader/setting.py \
  vnpy/trader/ui/widget.py \
  tests/test_tradingagents_manual_analysis.py \
  tests/test_tradingagents_signal_strategy.py \
  tests/test_tradingagents_backtest_strategy.py \
  tests/test_vnpy_cta_strategy_ai_isolation.py
```

结果：

```text
All checks passed!
```

## 结论

- 代码级 P27 定位闭环已通过：手动分析、独立 AI 策略、历史信号生成、AI 回测策略和传统策略隔离测试均可运行。
- 当前验证仍是单元/组件级验证，没有调用真实 LLM，也没有连接真实 Gateway。
- 实盘前仍需继续执行 P19/P20/P21：真实数据、真实 PostgreSQL、仿真 Gateway、live gate 和连续运行验证。
