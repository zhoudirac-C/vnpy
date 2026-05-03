# P11 运维、观测和小资金上线任务

目标：补齐生产运行所需的观测、报警、备份、权限、审计完整率和小资金实盘准入流程。

## 任务清单

- [ ] **P11-T01: 运行健康状态表**
  - 创建：`vnpy_tradingagents/ops_storage.py`
  - 目标：记录 worker heartbeat、最近错误、数据源延迟、队列积压和降级状态。
  - 验收：异常可追溯，不只写日志。

- [ ] **P11-T02: 指标和日志导出**
  - 创建：`vnpy_tradingagents/metrics.py`
  - 目标：导出 run_count、failure_count、latency、degraded_sources、blocked_orders。
  - 验收：可以被日志或监控系统采集。

- [ ] **P11-T03: 数据备份和恢复演练**
  - 创建文档：`docs/community/ops/postgres_backup_restore.md`
  - 目标：明确 PostgreSQL 备份、恢复、回测数据锁定和审计保留周期。
  - 验收：有可执行命令和恢复验收步骤。

- [ ] **P11-T04: 权限和密钥治理**
  - 创建：`vnpy_tradingagents/secrets_policy.py`
  - 目标：检查 API key 不入库、不入日志、不进入 TradingAgents context。
  - 验收：敏感字段被 mask。

- [ ] **P11-T05: 小资金上线 Runbook**
  - 创建文档：`docs/community/ops/live_gray_runbook.md`
  - 目标：定义上线前检查、开关、回滚、手工接管和复盘流程。
  - 验收：不满足 LiveGate 时不能进入 `live_allowed`。

## 完成记录

| 任务 | 日期 | 提交 | 验证 |
| --- | --- | --- | --- |
