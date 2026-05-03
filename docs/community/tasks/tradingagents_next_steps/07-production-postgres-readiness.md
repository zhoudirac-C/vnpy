# P7 生产级 PostgreSQL 迁移和健康检查任务

目标：把 P6 的“一次性建表函数”升级为可追踪、可重复、可诊断的生产初始化能力，确保真实 PostgreSQL 联调前可以明确知道数据库、依赖和关键配置是否就绪。

## 任务清单

- [x] **P7-T01: SchemaMigrationRunner**
  - 创建：`vnpy_tradingagents/migrations.py`
  - 目标：用迁移编号记录已应用 SQL，支持 pending/applied 状态查询。
  - 验收：重复执行不会重复应用已记录 migration。

- [x] **P7-T02: 初始化命令改用 migration runner**
  - 修改：`vnpy_tradingagents/schema_init.py`
  - 目标：`initialize_postgres_schema()` 不再只执行一段 SQL 字符串，而是走迁移列表并记录版本。
  - 验收：新环境一条命令创建全部表，重复执行幂等。

- [x] **P7-T03: CLI 初始化入口**
  - 创建：`vnpy_tradingagents/cli.py`
  - 修改：`pyproject.toml`
  - 目标：提供 `vnpy-tradingagents-schema init/status`，后续可直接在真实环境执行。
  - 验收：CLI 能解析参数；无 DSN 时给出明确错误，不静默成功。

- [x] **P7-T04: ProductionReadinessChecker**
  - 创建：`vnpy_tradingagents/readiness.py`
  - 目标：检查 PostgreSQL DSN、`psycopg`、TradingAgents API key、provider 配置和本地文件路径。
  - 验收：返回结构化检查结果，能区分 `ready/warning/failed`。

- [x] **P7-T05: 生产联调文档同步**
  - 修改：`README.md` 和总技术方案。
  - 目标：说明 PostgreSQL 支持与本项目业务表迁移的关系。
  - 验收：文档不再让人误解“PostgreSQL 不支持”。

## 完成记录

| 任务 | 日期 | 提交 | 验证 |
| --- | --- | --- | --- |
| P7-T01 | 2026-05-03 | `2507825c` | `uv run --with pytest pytest tests/test_tradingagents_production_readiness.py tests/test_tradingagents_gray_release.py tests/test_data_router.py tests/test_event_pipeline.py -v` |
| P7-T02 | 2026-05-03 | `2507825c` | `uv run --with pytest pytest tests/test_tradingagents_production_readiness.py tests/test_tradingagents_gray_release.py tests/test_data_router.py tests/test_event_pipeline.py -v` |
| P7-T03 | 2026-05-03 | `2507825c` | `uv run --with pytest pytest tests/test_tradingagents_production_readiness.py tests/test_tradingagents_gray_release.py tests/test_data_router.py tests/test_event_pipeline.py -v` |
| P7-T04 | 2026-05-03 | `2507825c` | `uv run --with pytest pytest tests/test_tradingagents_production_readiness.py tests/test_tradingagents_gray_release.py tests/test_data_router.py tests/test_event_pipeline.py -v` |
| P7-T05 | 2026-05-03 | `2507825c` | `uv run --with ruff ruff check vnpy_tradingagents/migrations.py vnpy_tradingagents/schema_init.py vnpy_tradingagents/readiness.py vnpy_tradingagents/cli.py vnpy_tradingagents/__init__.py tests/test_tradingagents_production_readiness.py pyproject.toml` |
