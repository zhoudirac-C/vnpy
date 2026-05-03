# P6 回测、仿真和灰度发布任务

目标：把当前轻量 replay 边界升级为真实 vn.py 回测、PaperAccount 仿真和灰度发布流程。

## 任务清单

- [x] **P6-T01: 接入 vn.py BacktestingEngine**
  - 创建：`vnpy_tradingagents/backtesting_bridge.py`
  - 目标：在回测时间点读取 `RatingSignal`、`PortfolioIntent`、`IntradayAdvice`，复用 `SignalFusionService` 和 `PreOrderDecisionService`。
  - 验收：回测不会访问真实 Gateway；每笔 AI 影响过的决策有 audit。

- [x] **P6-T02: PaperAccount 仿真接入**
  - 创建：`vnpy_tradingagents/paper_bridge.py`
  - 目标：只在 `GatewayAccountMode.SIMULATION` 时启用 AI，记录模拟成交和持仓。
  - 验收：`GatewayAiPolicy` 控制 runtime；模拟成交可写入反馈表。

- [x] **P6-T03: 灰度运行状态持久化**
  - 修改：`vnpy_tradingagents/monitoring.py`
  - 新增：`PostgresReplayRunStatusStorage`、`replay_run_status` 表。
  - 验收：UI 或日志可按 run_id 查询最新状态。

- [x] **P6-T04: 决策审计导出**
  - 创建：`vnpy_tradingagents/audit_export.py`
  - 格式：JSONL、CSV。
  - 字段：rule signal、AI source run ids、risk result、order intent、simulated/live trade id。
  - 验收：每次灰度可导出完整审计。

- [x] **P6-T05: 一键暂停和手工接管**
  - 修改：`vnpy_tradingagents/runtime.py`、UI。
  - 行为：立即禁用 AI signal，已生成未使用信号标记 disabled 或 expired，风控、撤单、持仓查询不受影响。
  - 验收：暂停后 `can_use_signal(live=False)` 和 `can_use_signal(live=True)` 都为 false。

- [x] **P6-T06: PostgreSQL 迁移和初始化命令**
  - 创建：`vnpy_tradingagents/migrations/`、`vnpy_router/migrations/` 或统一 CLI 初始化脚本。
  - 目标：不再只依赖 SQL 字符串，支持 schema version 和索引初始化。
  - 验收：新环境一条命令创建全部表，重复执行幂等。

- [x] **P6-T07: 小资金实盘准入检查**
  - 创建：`vnpy_tradingagents/live_gate.py`
  - 条件：模拟盘连续稳定运行天数、最大回撤低于阈值、审计完整率 100%、live AI 显式开启。
  - 验收：条件不满足时拒绝进入 live_allowed。

## 完成记录

| 任务 | 日期 | 提交 | 验证 |
| --- | --- | --- | --- |
| P6-T01 | 2026-05-03 | `f0be558b` | `uv run --with pytest pytest tests/test_tradingagents*.py -v` |
| P6-T02 | 2026-05-03 | `f0be558b` | `uv run --with pytest pytest tests/test_tradingagents*.py -v` |
| P6-T03 | 2026-05-03 | `f0be558b` | `uv run --with pytest pytest tests/test_tradingagents*.py -v` |
| P6-T04 | 2026-05-03 | `f0be558b` | `uv run --with pytest pytest tests/test_tradingagents*.py -v` |
| P6-T05 | 2026-05-03 | `f0be558b` | `uv run --with pytest pytest tests/test_tradingagents*.py -v` |
| P6-T06 | 2026-05-03 | `f0be558b` | `uv run --with pytest pytest tests/test_tradingagents*.py -v` |
| P6-T07 | 2026-05-03 | `f0be558b` | `uv run --with pytest pytest tests/test_tradingagents*.py -v` |
