# P23 文档和依赖一致性清理任务

目标：清理当前分支中“文档说可选、代码已主依赖”或“历史验证结果保留旧配置名”的不一致，减少后续部署误解。

## 任务清单

- [x] **P23-T01: TradingAgents 依赖口径统一**
  - 目标：决定 `tradingagents` 是主依赖还是 optional extra，并同步 `pyproject.toml`、技术路线和安装文档。
  - 验收：文档不再同时出现“默认依赖”和“不放默认依赖”的矛盾。

- [x] **P23-T02: PostgreSQL 旧配置词清理**
  - 目标：历史验证结果可以保留，但正式文档不再推荐 `router.postgres.dsn`、`QUANT_DATABASE_URL`。
  - 验收：正式文档搜索仅在纠错计划、历史结果或负向测试中出现旧词。

- [x] **P23-T03: P16 状态同步**
  - 目标：把 Podman E2E、BigModel 线上 smoke 和本机 PostgreSQL schema 验证结果同步进 P16。
  - 验收：每个任务状态说明是 Completed、Blocked 还是 Smoke Passed。

- [x] **P23-T04: 生产可用性总览**
  - 目标：生成一页当前生产差距总览，供后续开发和上线前评审使用。
  - 验收：总览明确“已实现、smoke 通过、blocked、生产前必须补齐”。

## 完成记录

| 任务 | 日期 | 提交 | 验证 |
| --- | --- | --- | --- |
| P23-T01 | 2026-05-05 | 未提交 | `rg -n "TradingAgents 不放入本仓库默认依赖|不放入本仓库默认依赖" docs/community/info docs/community/ops docs/community/tasks/tradingagents_next_steps -S \| rg -v "23-docs-dependency-consistency"` |
| P23-T02 | 2026-05-05 | 未提交 | `rg -n "router\\.postgres\\.dsn|QUANT_DATABASE_URL|postgres_dsn" docs/community/info docs/community/ops docs/community/tasks/tradingagents_next_steps -S`；仅 P17 纠错计划、Podman 用例旧词说明和历史验证结果保留 |
| P23-T03 | 2026-05-05 | 未提交 | P16 状态同步 |
| P23-T04 | 2026-05-05 | 未提交 | `docs/community/ops/production_gap_overview.md` |
