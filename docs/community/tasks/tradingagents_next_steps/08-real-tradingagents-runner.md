# P8 真实 TradingAgents Runner 接入任务

目标：把当前 context-only adapter 接到真实 TauricResearch TradingAgents 运行器，同时保持“不直连数据源、不直连交易接口、不绕过风控”的边界。

## 任务清单

- [ ] **P8-T01: TradingAgentsRunnerAdapter**
  - 创建：`vnpy_tradingagents/real_runner.py`
  - 目标：封装真实 TradingAgents graph/CLI 调用，把 `TradingAgentsContextPayload` 转为原生输入。
  - 验收：没有真实依赖时返回清晰的 dependency error；有注入 runner 时可生成结构化响应。

- [ ] **P8-T02: 输出结构校验**
  - 创建：`vnpy_tradingagents/output_validation.py`
  - 目标：校验 rating、action、confidence、risk_notes，不合规时降级为 `hold/unavailable`。
  - 验收：非法 action 不能进入 `trade_intent`。

- [ ] **P8-T03: Checkpoint 和 memory 隔离**
  - 修改：`vnpy_tradingagents/config.py`
  - 目标：按 run_id/trade_date/symbol 隔离 checkpoint，避免不同标的串状态。
  - 验收：同一 runner 多标的运行不会复用错误记忆。

- [ ] **P8-T04: Runner smoke test 脚本**
  - 创建：`vnpy_tradingagents/runner_smoke.py`
  - 目标：用 PostgreSQL 快照构造一次真实 request，输出报告和信号但不写订单。
  - 验收：失败原因可诊断，成功时写入 `agent_run/agent_report/rating_signal/trade_intent`。

- [ ] **P8-T05: Worker 部署文档**
  - 修改：`docs/community/info/custom_quant_architecture.md`
  - 目标：说明独立环境、依赖安装、API key、超时和降级策略。

## 完成记录

| 任务 | 日期 | 提交 | 验证 |
| --- | --- | --- | --- |
