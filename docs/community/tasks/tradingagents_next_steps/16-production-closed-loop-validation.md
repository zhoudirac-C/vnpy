# P16 生产闭环验证任务

目标：把 P12-P15 的生产候选能力转成可重复运行、可审计落档的闭环验证流程。验证必须区分“代码级闭环通过”和“真实生产外部依赖已就绪”，不能把缺少 PostgreSQL、Worker、API key 的本地结果误判为生产可用。

## 任务清单

- [x] **P16-T01: 生产闭环验证脚本**
  - 创建：`tools/production/closed_loop_validation.py`
  - 测试：`tests/test_production_closed_loop_validation.py`
  - 目标：提供 local/production 两种 profile，统一运行 lint、测试、alpha smoke、compileall、diff check、readiness 和外部环境门禁。
  - 验收：local profile 可以生成报告；production profile 在生产必需门禁未通过时返回非 ready。

- [x] **P16-T02: 验证流程文档**
  - 创建：`docs/community/ops/production_closed_loop_validation.md`
  - 目标：说明验证目标、命令入口、本地自动化检查、生产门禁、结果落档和下一步。
  - 验收：任何一次验证都有明确 Markdown/JSON 落档路径。

- [x] **P16-T03: 当前环境验证结果落档**
  - 创建：`docs/community/ops/validation_results/2026-05-04-production-closed-loop-local.md`
  - 创建：`docs/community/ops/validation_results/2026-05-04-production-closed-loop-local.json`
  - 目标：记录当前本机 local profile 的实际验证过程和结果。
  - 验收：结果明确显示代码级检查通过，但生产准入因真实 PostgreSQL、Worker、API key 和 readiness 阻塞而未通过。

- [ ] **P16-T04: 真实 PostgreSQL production profile 验证**
  - 前置：vn.py 全局 `database.name=postgresql` 和完整 `database.*`、schema init/status、备份恢复策略。
  - 目标：在真实 PostgreSQL 上跑 production profile 并落档。
  - 验收：PostgreSQL 扩展表 create_tables/status、snapshot 读写和 runtime state 均通过真实连接验证。

- [ ] **P16-T05: 真实 TradingAgents Worker production profile 验证**
  - 前置：当前 vn.py 环境安装上游 TradingAgents 依赖，保留默认 `tradingagents.worker_factory=vnpy_tradingagents.tradingagents_factory:build`，LLM API key，真实 PostgreSQL 快照。
  - 目标：用真实 Worker 跑一轮 runner smoke，不触发 Gateway/MainEngine。
  - 验收：报告、评级、交易意图入库；失败时不生成有效交易意图。

- [ ] **P16-T06: paper/simulation 连续运行验证**
  - 前置：P16-T04、P16-T05。
  - 目标：按 `live_gray_runbook.md` 进入 paper/simulation 连续运行。
  - 验收：连续运行记录、replay status、decision audit、feedback、ops heartbeat 全部可导出。

## 完成记录

| 任务 | 日期 | 提交 | 验证 |
| --- | --- | --- | --- |
| P16-T01 | 2026-05-04 | 未提交 | `uv run --with pytest pytest tests/test_production_closed_loop_validation.py -q` |
| P16-T02 | 2026-05-04 | 未提交 | 文档检查 |
| P16-T03 | 2026-05-04 | 未提交 | `uv run python -m tools.production.closed_loop_validation --profile local --repo-root . --output docs/community/ops/validation_results/2026-05-04-production-closed-loop-local.md --json-output docs/community/ops/validation_results/2026-05-04-production-closed-loop-local.json` |
| P16-T03A | 2026-05-05 | 未提交 | P17 纠错后重新落档：`uv run python -m tools.production.closed_loop_validation --profile local --repo-root . --output docs/community/ops/validation_results/2026-05-05-production-closed-loop-local.md --json-output docs/community/ops/validation_results/2026-05-05-production-closed-loop-local.json` |
| P16-T04 | Blocked | 未提交 | 等待真实 PostgreSQL |
| P16-T05 | Blocked | 未提交 | 代码侧已提供默认 context-only factory；仍等待当前 vn.py 环境安装上游 TradingAgents、真实 LLM key 和真实 PostgreSQL 快照 |
| P16-T06 | Blocked | 未提交 | 等待 P16-T04/P16-T05 |
