# P5 批量调度、组合约束和反馈任务

目标：让长期链路从单标的运行边界升级为股票池批量运行、组合约束和绩效反馈闭环。

## 任务清单

- [x] **P5-T01: 股票池批量 LongHorizonAgentJob**
  - 创建：`vnpy_tradingagents/batch.py`
  - 输入：股票池、trade_date、ResearchSnapshotReader。
  - 输出：多个 `RatingSignal` 和 `PortfolioIntent`。
  - 验收：单标的失败不影响其他标的；批量结果按 run_id 可追踪。

- [x] **P5-T02: 长期调度器**
  - 创建：`vnpy_tradingagents/long_scheduler.py`
  - 支持：盘前、盘后、周末。
  - 验收：同一 trade_date 可幂等重跑；重跑不会产生重复 active intent。

- [x] **P5-T03: 组合约束规则**
  - 创建：`vnpy_tradingagents/portfolio_constraints.py`
  - 约束：单票权重上限、行业集中度、最大换手率、现金保留比例、最大回撤。
  - 验收：`PortfolioIntent` 只影响目标仓位和排序权重；违反约束时不生成买入意图。

- [x] **P5-T04: 绩效和成交反馈写回**
  - 创建：`vnpy_tradingagents/performance_feedback.py`
  - 表：`agent_performance_feedback`、`agent_trade_feedback`
  - 输入：成交、持仓、账户权益、benchmark 收益。
  - 验收：下一次 TradingAgents context 可读取历史反馈。

- [x] **P5-T05: 反思输入替换 SPY alpha**
  - 修改：真实 Worker adapter 或 prompt 层。
  - 目标：用 A 股 benchmark alpha 和真实持仓绩效，不使用原生 SPY alpha 假设。
  - 验收：prompt/context 中 benchmark 为 A 股指数。

- [x] **P5-T06: PortfolioReplayEngine 指标增强**
  - 修改：`vnpy_tradingagents/replay.py`
  - 增加：换手率、目标权重偏离、行业暴露、最大回撤。
  - 验收：长期回放 summary 可用于灰度面板展示。

## 完成记录

| 任务 | 日期 | 提交 | 验证 |
| --- | --- | --- | --- |
| P5-T01 | 2026-05-03 | `17a2655c` | `uv run --with pytest pytest tests/test_tradingagents_batch_portfolio_feedback.py tests/test_tradingagents_replay.py tests/test_tradingagents_research.py tests/test_tradingagents_worker_adapter.py -v` |
| P5-T02 | 2026-05-03 | `17a2655c` | `uv run --with pytest pytest tests/test_tradingagents_batch_portfolio_feedback.py tests/test_tradingagents_replay.py tests/test_tradingagents_research.py tests/test_tradingagents_worker_adapter.py -v` |
| P5-T03 | 2026-05-03 | `17a2655c` | `uv run --with pytest pytest tests/test_tradingagents_batch_portfolio_feedback.py tests/test_tradingagents_replay.py tests/test_tradingagents_research.py tests/test_tradingagents_worker_adapter.py -v` |
| P5-T04 | 2026-05-03 | `17a2655c` | `uv run --with pytest pytest tests/test_tradingagents_batch_portfolio_feedback.py tests/test_tradingagents_replay.py tests/test_tradingagents_research.py tests/test_tradingagents_worker_adapter.py -v` |
| P5-T05 | 2026-05-03 | `17a2655c` | `uv run --with pytest pytest tests/test_tradingagents_batch_portfolio_feedback.py tests/test_tradingagents_replay.py tests/test_tradingagents_research.py tests/test_tradingagents_worker_adapter.py -v` |
| P5-T06 | 2026-05-03 | `17a2655c` | `uv run --with pytest pytest tests/test_tradingagents_batch_portfolio_feedback.py tests/test_tradingagents_replay.py tests/test_tradingagents_research.py tests/test_tradingagents_worker_adapter.py -v` |
