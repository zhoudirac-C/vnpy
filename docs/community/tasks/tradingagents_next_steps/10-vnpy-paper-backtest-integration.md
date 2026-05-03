# P10 vn.py 回测、PaperAccount 和 UI 联调任务

目标：把当前可测试桥接层挂到真实 vn.py 运行路径，让回测、PaperAccount、状态面板和手工接管形成可操作流程。

## 任务清单

- [ ] **P10-T01: BacktestingEngine 接入适配**
  - 修改或创建：`vnpy_tradingagents/backtesting_app_bridge.py`
  - 目标：在 vn.py 回测时间点读取 AI 信号、执行融合和审计。
  - 验收：回测不访问真实 Gateway，每笔 AI 影响决策有 `decision_audit`。

- [ ] **P10-T02: PaperAccount 运行态接入**
  - 修改：`vnpy_tradingagents/paper_bridge.py`
  - 目标：接真实仿真成交、持仓、资金回报，写入 feedback。
  - 验收：只在 `GatewayAccountMode.SIMULATION` 启用 AI。

- [ ] **P10-T03: UI 手工接管按钮**
  - 修改：`vnpy_tradingagents/ui/widget.py`
  - 目标：新增一键暂停/手工接管按钮，调用 `pause_manual_takeover()`。
  - 验收：点击后 paper/live `can_use_signal()` 都为 false。

- [ ] **P10-T04: 灰度状态 UI 查询**
  - 修改：`vnpy_tradingagents/ui/widget.py`
  - 目标：从 `PostgresReplayRunStatusStorage` 读取最新 run status。
  - 验收：UI 可按 run_id 展示最新状态，而不是只接内存对象。

- [ ] **P10-T05: 端到端 Paper 演练脚本**
  - 创建：`vnpy_tradingagents/paper_smoke.py`
  - 目标：从 snapshot 到 worker 到 signal 到 paper fill 到 feedback 跑一遍。
  - 验收：不触发 live Gateway。

## 完成记录

| 任务 | 日期 | 提交 | 验证 |
| --- | --- | --- | --- |
