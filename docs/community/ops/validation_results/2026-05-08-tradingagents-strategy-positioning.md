# P27 TradingAgents 独立 AI 策略定位验证结果

日期：2026-05-08

## 验证目标

- TradingAgents 手动分析入口只生成报告、评级和交易意图，不直接下单。
- `TradingAgentsSignalStrategy` 作为独立 AI 策略读取已落库意图，`hold/watch` 不会被当成订单。
- `TradingAgentsBacktestStrategy` 只读取历史时点已固化 AI 信号，不在回测循环里调用 LLM。
- 历史 AI 信号通过 `HistoricalAiSignalJob` 预生成并落库，供后续回测读取。
- `TradingAgentsCtaSignalStrategy` 作为 CTA UI 可见包装层，能在 `功能 -> CTA策略` 下拉框中被扫描到。
- `TradingAgentsApp` 启动后自动装配手动分析服务，避免 UI 点击时报 `manual analysis service is not configured`。
- TradingAgents UI 像 `CTA策略` 一样作为独立大窗口打开，入口同时包括左侧 toolbar 的 `TradingAgents分析管理` 和 `功能 -> TradingAgents分析管理`；左侧 toolbar 的 `数据管理` 继续表示 vn.py 原生 DataManager。
- 传统规则策略不被本次改动隐式接入 TradingAgents。

## 验证命令

```bash
uv run --with pytest pytest tests/test_tradingagents_app_bootstrap.py -q
```

结果：

```text
2 passed
```

```bash
uv run --with pytest pytest tests/test_tradingagents_cta_signal_strategy.py -q
```

结果：

```text
4 passed
```

```bash
uv run --with pytest pytest \
  tests/test_tradingagents_cta_signal_strategy.py \
  tests/test_tradingagents_signal_strategy.py \
  tests/test_vnpy_cta_strategy_ai_isolation.py \
  -q
```

结果：

```text
11 passed
```

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
uv run --with pytest pytest \
  tests/test_tradingagents_ui.py \
  tests/test_tradingagents_storage_service.py \
  tests/test_tradingagents_manual_analysis.py \
  tests/test_tradingagents_app_bootstrap.py \
  -q
```

结果：

```text
22 passed
```

```bash
uv run --with ruff ruff check \
  vnpy_tradingagents/ui/widget.py \
  vnpy_tradingagents/storage.py \
  vnpy_tradingagents/engine.py \
  vnpy_tradingagents/bootstrap.py \
  vnpy/trader/ui/mainwindow.py \
  tests/test_tradingagents_ui.py \
  tests/test_tradingagents_storage_service.py
```

结果：

```text
All checks passed!
```

```bash
uv run --with pytest pytest tests/test_tradingagents_*.py tests/test_vnpy_cta_strategy_ai_isolation.py -q
```

结果：

```text
188 passed
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
- CTA UI 可见性补齐：`TradingAgentsCtaSignalStrategy` 放在仓库根目录 `strategies/` 下，vn.py CTA 引擎会按原生机制自动扫描。
- TradingAgents App 启动装配补齐：`examples/veighna_trader/run.py` 会调用 `configure_tradingagents_services(main_engine)`，把手动分析服务挂到 `TradingAgentsEngine`。
- TradingAgents 分析管理页补齐：左侧 toolbar 和 `功能 -> TradingAgents分析管理` 都能打开独立大窗口，不占用主窗口行情/委托 Dock；它与左侧原生 `数据管理` 并列但职责不同，历史页从 PostgreSQL 审计表读取分析记录，点击历史表最后一列 `分析报告` 后跳转展示完整报告。
- 当前验证仍是单元/组件级验证，没有调用真实 LLM，也没有连接真实 Gateway。
- 实盘前仍需继续执行 P19/P20/P21：真实数据、真实 PostgreSQL、仿真 Gateway、live gate 和连续运行验证。
