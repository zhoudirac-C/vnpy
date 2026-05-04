# P13 TradingAgents 真实 context-only Worker 任务

目标：把 TradingAgents 接入从“兼容 runner 形态的骨架”升级为可生产运行的 context-only Worker。Worker 只能读取本地快照上下文，不允许默认 yfinance、Alpha Vantage、外部 provider、Gateway 或 MainEngine 进入推理链路。

## 任务清单

- [x] **P13-T01: 禁止生产路径裸调 `propagate(symbol, date)`**
  - 修改：`vnpy_tradingagents/real_runner.py`
  - 测试：`tests/test_tradingagents_real_runner.py`
  - 目标：生产 runner 只接受 `run(native_input)`、`invoke(native_input)` 或 callable context-only 接口；裸 `propagate(symbol, date)` 只能在明确标记的 legacy/test 模式下使用。
  - 验收：未提供 context-only runner 时返回结构化 `runner_not_configured` 或 `unsupported_runner_shape`，不会悄悄走 TradingAgents 默认美股数据工具。

- [x] **P13-T02: A 股 context-only native runner wrapper**
  - 创建：`vnpy_tradingagents/native_context_runner.py`
  - 测试：`tests/test_tradingagents_native_context_runner.py`
  - 目标：提供统一 wrapper，把 `MarketDataToolkit` 生成的行情、财务、估值、新闻、情绪、持仓和交易规则上下文传给 TradingAgents。
  - 验收：runner 输入中不包含外部 provider handle、数据库连接、API key、Gateway、MainEngine 或账号对象。

- [x] **P13-T03: Worker 进程配置加载**
  - 修改：`vnpy_tradingagents/worker_process.py`、`vnpy_tradingagents/worker_adapter.py`
  - 目标：CLI/子进程可以根据配置加载真实 runner；默认无 runner 时给出清晰失败，不再伪装成可运行。
  - 验收：fake runner smoke 成功；无 runner smoke 失败但不写入有效交易意图。

- [x] **P13-T04: TradingAgents 输出和失败写库规则**
  - 修改：`vnpy_tradingagents/storage.py`、`vnpy_tradingagents/output_validation.py`
  - 目标：失败、超时、依赖缺失时只保存 `agent_run` 和诊断，不生成有效 `rating_signal` 或 `trade_intent`。
  - 验收：失败响应不会被策略侧读取为 hold/watch 交易意图。

- [x] **P13-T05: checkpoint 和 memory 隔离复核**
  - 修改：`vnpy_tradingagents/worker.py`、`vnpy_tradingagents/real_runner.py`
  - 目标：按 `trade_date/vt_symbol/run_id` 隔离 checkpoint，避免多标的串状态；清理旧 checkpoint 有明确策略。
  - 验收：同一批次多个标的运行时 checkpoint 路径互不覆盖。

- [x] **P13-T06: Worker smoke 和 readiness 接入**
  - 修改：`vnpy_tradingagents/readiness.py`
  - 测试：`tests/test_tradingagents_runner_smoke.py`、`tests/test_tradingagents_production_readiness.py`
  - 目标：readiness 能检查 runner 是否可加载、是否 context-only、是否能处理一条最小快照。
  - 验收：缺少 TradingAgents 或缺少 LLM key 时显示 failed/warning，不影响 vn.py 主程序启动。

## 完成记录

| 任务 | 日期 | 提交 | 验证 |
| --- | --- | --- | --- |
| P13-T01 | 2026-05-04 | 未提交 | `uv run --with pytest pytest tests/test_tradingagents_real_runner.py -q` |
| P13-T02 | 2026-05-04 | 未提交 | `uv run --with pytest pytest tests/test_tradingagents_native_context_runner.py -q` |
| P13-T03 | 2026-05-04 | 未提交 | `uv run --with pytest pytest tests/test_tradingagents_worker_process.py tests/test_tradingagents_real_runner.py -q` |
| P13-T04 | 2026-05-04 | 未提交 | `uv run --with pytest pytest tests/test_tradingagents_real_runner.py tests/test_tradingagents_storage_service.py -q` |
| P13-T05 | 2026-05-04 | 未提交 | `uv run --with pytest pytest tests/test_tradingagents_real_runner.py::test_checkpoint_path_is_isolated_by_date_symbol_and_run_id -q` |
| P13-T06 | 2026-05-04 | 未提交 | `uv run --with pytest pytest tests/test_tradingagents_real_runner.py tests/test_tradingagents_production_readiness.py -q` |
