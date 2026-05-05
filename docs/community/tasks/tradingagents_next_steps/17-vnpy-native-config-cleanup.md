# vn.py Native Config Reuse Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 删除本 fork 中绕开 vn.py 原生配置体系的重复 PostgreSQL 配置入口，并在界面和文档中补齐 TradingAgents LLM 环境变量说明。

**Architecture:** PostgreSQL 只复用 vn.py 已有 `database.*` 全局配置；TradingAgents/router 新增表写入同一个 PostgreSQL 数据库，并按 `vnpy_postgresql` 的方式定义 Peewee Model 后调用 `create_tables(..., safe=True)` 初始化。LLM key 不进入 `vt_setting.json`，界面只配置环境变量名和 provider/model，真实 key 由操作系统环境变量或部署 Secret 注入。

**Tech Stack:** vn.py `SETTINGS`/全局配置界面、`vnpy_postgresql` 配置约定、Peewee `PostgresqlDatabase`/Model/`create_tables()`、TradingAgents Worker、pytest、ruff、PlantUML 文档。

---

## 背景原则

本阶段按以下原则纠偏：

1. 本项目是基于 vn.py fork 开发，数据库配置必须复用 vn.py 原有 `database.name`、`database.host`、`database.port`、`database.database`、`database.user`、`database.password`。
2. 不再新增或保留 `router.postgres.dsn`、`QUANT_DATABASE_URL` 这类平行 PostgreSQL 配置入口。
3. 新增 TradingAgents/router 扩展表可以和 vn.py 原有 PostgreSQL 数据库共用同一个库；隔离方式是表名或 schema，不是单独 DSN。
4. `vnpy_postgresql` 没有 Alembic 这类 migration 文件；它在 `Database.__init__()` 中连接 PostgreSQL 后调用 Peewee `create_tables([DbBarData, DbTickData, DbBarOverview, DbTickOverview])` 初始化表。
5. 扩展表初始化应复用这个模式：定义 TradingAgents/router Peewee Model，并在扩展初始化命令或启动检查里调用 `db.create_tables([...], safe=True)`。
6. LLM key 不写入 vn.py 明文配置文件；界面说明配置哪个环境变量，真实 key 由系统环境变量、容器 Secret 或云 Secret Manager 提供。

## 当前分支发现的问题

| 类别 | 当前位置 | 问题 | 处理结论 |
| --- | --- | --- | --- |
| 重复 DB 配置 | `vnpy/trader/setting.py` | 新增了 `router.postgres_cache.enabled`、`router.postgres.dsn` | 删除，不再作为配置项 |
| 重复 DB 入口 | `vnpy_router/datafeed.py` | `_connect_postgres()` 优先读取 `router.postgres.dsn`，再 fallback 到 `database.*` | 改成只读 `database.*` |
| 重复 DB 入口 | `vnpy_tradingagents/cli.py` | `schema init/status` 需要 `--dsn` 或 `router.postgres.dsn` | 删除 `--dsn`，只使用 vn.py 全局 PostgreSQL 配置 |
| readiness 命名错误 | `vnpy_tradingagents/readiness.py` | 检查项叫 `postgres_dsn`，逻辑围绕 router cache/DSN | 改成检查 `vnpy_postgres_config` |
| 表初始化路线偏差 | `vnpy_tradingagents/migrations.py`、`vnpy_tradingagents/schema_init.py` | 自建 SQL migration runner 和 `schema_migration` 偏离 `vnpy_postgresql` 的 Peewee `create_tables()` 模式 | 改为 Peewee Model + `create_tables(..., safe=True)` 初始化扩展表 |
| 生产验证重复入口 | `tools/production/closed_loop_validation.py` | 把 `QUANT_DATABASE_URL` 作为生产门禁 | 删除该门禁，数据库门禁交给 readiness 读取 `database.*` |
| 文档重复入口 | `docs/community/**` | 多处写 `--dsn "$QUANT_DATABASE_URL"` 或 “设置 QUANT_DATABASE_URL” | 改成 vn.py 全局配置和 `vnpy-tradingagents-schema schema init` |
| UI 说明不足 | `vnpy/trader/ui/widget.py` 和文档 | `tradingagents.api_key_env_var` 能编辑，但用户不知道不同系统怎么设置这个变量 | 增加界面说明和文档 |

## 保留但需要重新定位的能力

- `psycopg` 直连不再作为扩展表初始化的主路线；建表初始化优先使用 Peewee Model + `create_tables()`，与 `vnpy_postgresql` 保持一致。
- 现有 `vnpy_tradingagents/migrations.py`、`schema_migration` 只能作为过渡期技术债清理对象，不再作为生产目标路线。
- 如果未来确实需要 `ALTER TABLE` 级升级，优先在扩展模块中提供兼容升级函数，并在文档中说明它是扩展表升级脚本，不是新的数据库配置体系。
- `tradingagents.api_key_env_var` 可以保留：它保存的是环境变量名，不保存真实 key。

## Task P17-T01: 先补测试，锁定 vn.py 原生 PostgreSQL 配置行为

**Files:**
- Create: `tests/test_vnpy_native_postgres_config.py`
- Modify: `tests/test_tradingagents_production_readiness.py`
- Modify: `tests/test_production_closed_loop_validation.py`

- [x] **Step 1: 新增 PostgreSQL 配置 helper 测试**

测试目标：

```python
def test_vnpy_postgres_peewee_params_use_database_settings_only():
    settings = {
        "database.name": "postgresql",
        "database.host": "localhost",
        "database.port": 5432,
        "database.database": "vnpy",
        "database.user": "postgres",
        "database.password": "secret",
        "router.postgres.dsn": "postgresql://must-not-be-used",
    }

    params = vnpy_postgres_peewee_params(settings)

    assert params == {
        "database": "vnpy",
        "host": "localhost",
        "port": 5432,
        "user": "postgres",
        "password": "secret",
    }
```

- [x] **Step 2: 新增缺失配置测试**

测试目标：

```python
def test_vnpy_postgres_missing_fields_report_database_keys():
    settings = {
        "database.name": "sqlite",
        "database.database": "",
        "database.host": "",
        "database.port": 0,
        "database.user": "",
        "database.password": "",
    }

    missing = missing_vnpy_postgres_fields(settings)

    assert missing == [
        "database.name",
        "database.database",
        "database.host",
        "database.port",
        "database.user",
        "database.password",
    ]
```

- [x] **Step 3: 修改 readiness 测试**

把原来的 `postgres_dsn` 断言改成：

```python
assert report.by_name("vnpy_postgres_config").status == ReadinessStatus.FAILED
```

通过用例里的 settings 必须包含完整 `database.*`：

```python
settings={
    "database.name": "postgresql",
    "database.host": "localhost",
    "database.port": 5432,
    "database.database": "vnpy",
    "database.user": "postgres",
    "database.password": "secret",
    "router.providers": f"local_file:{data_path}",
    "tradingagents.api_key_env_var": "TRADINGAGENTS_API_KEY",
    "tradingagents.worker_factory": "worker_factory:build",
}
```

- [x] **Step 4: 修改生产闭环验证测试**

删除测试环境中的 `QUANT_DATABASE_URL`，生产通过条件只保留：

```python
environ={
    "TRADINGAGENTS_WORKER_FACTORY": "worker_factory:build",
    "OPENAI_API_KEY": "secret",
}
```

数据库是否可用由 `vnpy-tradingagents-schema readiness --json` 的返回结果负责。

- [x] **Step 5: 运行测试确认当前实现失败**

Run:

```bash
uv run --with pytest pytest tests/test_vnpy_native_postgres_config.py tests/test_tradingagents_production_readiness.py tests/test_production_closed_loop_validation.py -q
```

Expected: 至少有 `router.postgres.dsn`、`postgres_dsn` 或 `QUANT_DATABASE_URL` 相关失败。

## Task P17-T02: 删除重复 PostgreSQL 配置入口，改用 Peewee 连接模型

**Files:**
- Modify: `vnpy/trader/setting.py`
- Create: `vnpy_router/peewee.py`
- Modify: `vnpy_router/datafeed.py`
- Modify: `vnpy_tradingagents/cli.py`
- Modify: `vnpy_tradingagents/readiness.py`

- [x] **Step 1: 从默认配置删除重复项**

从 `SETTINGS` 删除：

```python
"router.postgres_cache.enabled": False,
"router.postgres.dsn": "",
```

- [x] **Step 2: 新增只读 vn.py database.* 的 Peewee helper**

`vnpy_router/peewee.py` 负责三件事：

```python
POSTGRES_DATABASE_NAMES = {"postgres", "postgresql"}
REQUIRED_POSTGRES_FIELDS = (
    "database.database",
    "database.host",
    "database.port",
    "database.user",
    "database.password",
)
```

提供：

```python
def is_vnpy_postgres(settings): ...
def missing_vnpy_postgres_fields(settings): ...
def vnpy_postgres_peewee_params(settings): ...
def create_vnpy_postgres_database(settings): ...
```

连接必须使用 Peewee，并复用 vn.py 原有字段：

```python
PeeweePostgresqlDatabase(
    database=SETTINGS["database.database"],
    user=SETTINGS["database.user"],
    password=SETTINGS["database.password"],
    host=SETTINGS["database.host"],
    port=SETTINGS["database.port"],
)
```

- [x] **Step 3: datafeed 快照缓存只跟随 vn.py PostgreSQL**

`vnpy_router/datafeed.py` 的 `_connect_postgres()` 不再读取 `router.postgres.dsn`。如果 `database.name != postgresql` 或配置不完整，返回 `None`，router 继续不带 PostgreSQL cache 运行。

- [x] **Step 4: schema CLI 删除 `--dsn`**

命令保持：

```bash
vnpy-tradingagents-schema schema init
vnpy-tradingagents-schema schema status
```

错误提示改成：

```text
vn.py PostgreSQL settings are incomplete: database.name, database.host, ...
```

- [x] **Step 5: readiness 改成 vn.py 配置检查**

readiness 项名改为：

```text
vnpy_postgres_config
```

含义：

- `ready`: `database.name=postgresql` 且所有 PostgreSQL 字段完整。
- `failed`: 未选择 PostgreSQL 或字段缺失。
- `peewee`: 检查 `peewee.PostgresqlDatabase` 可用。

- [x] **Step 6: 运行测试**

Run:

```bash
uv run --with pytest pytest tests/test_vnpy_native_postgres_config.py tests/test_data_router.py tests/test_tradingagents_production_readiness.py -q
```

Expected: 全部通过。

## Task P17-T03: 扩展表初始化改为 Peewee Model `create_tables()`

**Files:**
- Create: `vnpy_router/extension_models.py`
- Create or Modify: `vnpy_tradingagents/models.py`
- Modify: `vnpy_tradingagents/schema_init.py`
- Modify: `vnpy_tradingagents/cli.py`
- Modify: `tests/test_tradingagents_production_readiness.py`
- Modify: `tests/test_data_router.py`

- [x] **Step 1: 为 router 快照表定义 Peewee Model**

`vnpy_router/extension_models.py` 里定义扩展表 Model，表名保持现有 SQL 表名，例如：

```python
class MarketBarSnapshot(Model):
    class Meta:
        table_name = "market_bar_snapshot"
```

字段要覆盖当前 `MARKET_BAR_SNAPSHOT_SCHEMA` 已有字段；JSON/JSONB 字段使用 Peewee 的 `BinaryJSONField` 或 PostgreSQL JSON 字段能力，避免手写 `CREATE TABLE` 字符串作为主初始化路线。

- [x] **Step 2: 为 TradingAgents 表定义 Peewee Model**

`vnpy_tradingagents/models.py` 里定义：

```python
AgentRun
AgentReport
RatingSignal
IntradayAdvice
TradeIntent
DecisionAudit
RuntimeState
```

表名保持当前已落地 SQL 表名，避免破坏已有测试和历史数据。

- [x] **Step 3: schema init 改为 create_tables**

`initialize_postgres_schema()` 不再执行 `MigrationRunner.apply()`，而是：

```python
db = create_vnpy_postgres_database(SETTINGS)
db.connect(reuse_if_open=True)
db.create_tables(router_models + tradingagents_models, safe=True)
```

返回值从 migration 结果改成扩展表初始化结果，例如：

```python
SchemaInitResult(created_or_existing_tables=[...])
```

- [x] **Step 4: schema status 改为检查表存在**

`vnpy-tradingagents-schema schema status` 不再读取 `schema_migration`，而是基于 Peewee/database introspection 检查扩展表是否存在。

输出示例：

```json
{
  "tables": {
    "market_bar_snapshot": "ready",
    "agent_run": "ready"
  }
}
```

- [x] **Step 5: 测试 create_tables 被调用**

测试应使用 fake Peewee database，断言：

```python
assert fake_db.created_tables == expected_models
assert fake_db.safe is True
```

- [x] **Step 6: 删除或降级 migration runner 测试**

原 `MigrationRunner` 测试改成：

```text
历史 SQL migration runner 不再是生产初始化路径；如保留文件，只作为旧版本兼容工具，不进入 readiness 和 schema init/status。
```

## Task P17-T04: 对齐扩展表初始化文档与 vn.py 数据库文档

**Files:**
- Modify: `docs/community/info/database.md`
- Modify: `docs/community/info/custom_quant_architecture.md`
- Modify: `docs/community/info/vnpy_reuse_extension_route.md`
- Modify: `docs/community/tasks/tradingagents_next_steps/07-production-postgres-readiness.md`
- Modify: `docs/community/tasks/tradingagents_next_steps/12-vnpy-reuse-correction.md`

- [x] **Step 1: 在数据库文档 PostgreSQL 章节后增加扩展表说明**

新增内容必须表达：

```text
TradingAgents/router 扩展表复用同一个 vn.py PostgreSQL 数据库。
配置入口仍然是 database.*。
初始化扩展表运行 vnpy-tradingagents-schema schema init。
扩展表初始化方式复用 vnpy_postgresql 的 Peewee Model + create_tables(..., safe=True)。
查看扩展表存在状态运行 vnpy-tradingagents-schema schema status。
```

- [x] **Step 2: 把 “DSN/schema init --dsn” 改成原生命令**

替换：

```bash
vnpy-tradingagents-schema schema init --dsn "$QUANT_DATABASE_URL"
```

为：

```bash
vnpy-tradingagents-schema schema init
```

- [x] **Step 3: 明确 `schema_migration` 不再是目标路线**

文档中写清楚：

```text
schema_migration 是早期自建 SQL migration runner 的遗留设计；P17 后扩展表初始化复用 Peewee create_tables，不再把 schema_migration 作为生产 readiness 或 schema status 的依据。
```

- [x] **Step 4: 搜索确认无 DSN 文案残留**

Run:

```bash
rg -n "router\\.postgres\\.dsn|QUANT_DATABASE_URL|--dsn|PostgreSQL DSN|postgres_dsn" docs/community vnpy vnpy_router vnpy_tradingagents tools tests -S
```

Expected: 只允许历史验证结果 JSON/MD 中出现旧字段；当前方案文档、运行手册、代码和测试不再出现。

## Task P17-T05: 生产闭环验证改为复用 readiness

**Files:**
- Modify: `tools/production/closed_loop_validation.py`
- Modify: `tests/test_production_closed_loop_validation.py`
- Modify: `docs/community/ops/production_closed_loop_validation.md`
- Modify: `docs/community/ops/live_gray_runbook.md`

- [x] **Step 1: 删除 `postgres_dsn_env` gate**

删除：

```python
("postgres_dsn_env", "QUANT_DATABASE_URL", "real PostgreSQL DSN is configured")
```

保留：

```python
("tradingagents_worker_factory_env", "TRADINGAGENTS_WORKER_FACTORY", "context-only worker factory is configured")
("llm_api_key_env", "OPENAI_API_KEY", "LLM API key environment variable is configured")
```

- [x] **Step 2: 把数据库门禁写入 readiness 说明**

生产 validation 的数据库门禁来自：

```bash
uv run vnpy-tradingagents-schema readiness --json
```

该命令读取 vn.py `database.*`，不读取独立 DSN 环境变量。

- [x] **Step 3: 重新生成本地验证结果**

Run:

```bash
uv run python -m tools.production.closed_loop_validation \
  --profile local \
  --repo-root . \
  --output docs/community/ops/validation_results/2026-05-05-production-closed-loop-local.md \
  --json-output docs/community/ops/validation_results/2026-05-05-production-closed-loop-local.json
```

Expected: 结果里没有 `postgres_dsn_env`，数据库问题通过 `readiness_cli` 展示。

## Task P17-T06: 在界面和文档中说明 LLM 环境变量配置

**Files:**
- Modify: `vnpy/trader/ui/widget.py`
- Create: `docs/community/info/tradingagents_llm_env.md`
- Modify: `docs/community/info/index.rst`
- Modify: `docs/community/info/custom_quant_architecture.md`

- [x] **Step 1: 全局配置界面增加字段说明**

在 `GlobalDialog` 中为这些字段展示说明文字：

```python
SETTING_HELP_TEXT = {
    "tradingagents.api_key_env_var": "只填写环境变量名，例如 OPENAI_API_KEY；不要填写真实 API key。",
    "tradingagents.llm_provider": "LLM provider，例如 openai、anthropic、dashscope、deepseek。",
    "tradingagents.model": "TradingAgents Worker 使用的模型名；未配置 API key 时不会调用大模型。",
}
```

界面呈现方式：

- `field_name <type>` 保持不变。
- 对存在说明的字段，在输入框下方增加一行灰色说明。
- 不改变已有配置保存格式。

- [x] **Step 2: 新增 LLM 环境变量文档**

文档必须包含这些例子：

macOS/Linux 临时配置：

```bash
export OPENAI_API_KEY="sk-..."
```

macOS/Linux zsh 持久配置：

```bash
echo 'export OPENAI_API_KEY="sk-..."' >> ~/.zshrc
source ~/.zshrc
```

macOS GUI 程序环境变量：

```bash
launchctl setenv OPENAI_API_KEY "sk-..."
```

Windows PowerShell 临时配置：

```powershell
$env:OPENAI_API_KEY="sk-..."
```

Windows 用户级持久配置：

```powershell
[Environment]::SetEnvironmentVariable("OPENAI_API_KEY", "sk-...", "User")
```

容器/云服务：

```bash
docker run -e OPENAI_API_KEY="sk-..." ...
```

- [x] **Step 3: 写清楚无 LLM key 的降级行为**

文档明确：

```text
未配置 API key 时，TradingAgents Worker 不调用大模型，返回 configuration_error/unavailable；系统不生成 AI 评级和 AI 交易意图，vn.py 原有行情、策略、风控、下单链路继续运行。
```

- [x] **Step 4: 文档加入目录**

`docs/community/info/index.rst` 增加：

```rst
   tradingagents_llm_env.md
```

## Task P17-T07: 全局检查重复开发和旁路能力

**Files:**
- Modify: `docs/community/tasks/tradingagents_next_steps/17-vnpy-native-config-cleanup.md`
- Modify only if confirmed necessary: duplicated implementation files found by the scan

- [x] **Step 1: 搜索重复配置入口**

Run:

```bash
rg -n "router\\.postgres\\.dsn|router\\.postgres_cache|QUANT_DATABASE_URL|--dsn|postgres_dsn" . -S
```

Expected:

- 当前实现代码不出现。
- 当前任务文档可以出现，因为它记录清理计划。
- 历史验证结果可以保留旧字段，但必须标注为历史结果。

- [x] **Step 2: 搜索绕开 vn.py gateway/datafeed 的 provider**

Run:

```bash
rg -n "class .*QmtProvider|class .*XtProvider|send_order|MainEngine|gateway|vnpy_xt|vnpy_datafeed" vnpy_router vnpy_tradingagents tests docs/community -S
```

Expected:

- QMT/XT 只通过 vn.py 插件、gateway 或 datafeed 说明接入。
- TradingAgents Worker 不持有 `MainEngine`、`Gateway`、`send_order` 等实盘句柄。

- [x] **Step 3: 搜索真实 key 明文落盘风险**

Run:

```bash
rg -n "api_key|OPENAI_API_KEY|ANTHROPIC_API_KEY|DASHSCOPE_API_KEY|DEEPSEEK_API_KEY|sk-" vnpy vnpy_router vnpy_tradingagents docs/community tests -S
```

Expected:

- 代码只保存环境变量名。
- 测试中只能出现假 key，如 `secret`。
- 文档明确不要把真实 key 填入 vn.py 全局配置。

- [x] **Step 4: 把扫描结果写入本文件的完成记录**

完成时在“完成记录”中写入：

- 清理掉的重复入口。
- 保留的扩展能力和理由。
- 仍需用户提供的生产配置。

## Task P17-T08: 最终验证与提交

**Files:**
- Modify: `docs/community/tasks/tradingagents_next_steps/README.md`
- Modify: `docs/community/tasks/tradingagents_next_steps/17-vnpy-native-config-cleanup.md`

- [x] **Step 1: 运行核心测试**

Run:

```bash
uv run --with pytest pytest tests/test_vnpy_native_postgres_config.py tests/test_tradingagents_production_readiness.py tests/test_data_router.py tests/test_production_closed_loop_validation.py -q
```

Expected: 全部通过。

- [x] **Step 2: 运行全量非 alpha 测试**

Run:

```bash
uv run --with pytest pytest tests -q --ignore=tests/test_alpha101.py
```

Expected: 全部通过或仅出现已知 skip。

- [x] **Step 3: 运行 ruff**

Run:

```bash
uv run --with ruff ruff check vnpy/trader/setting.py vnpy/trader/ui/widget.py vnpy_router vnpy_tradingagents tools/production tests/test_vnpy_native_postgres_config.py tests/test_tradingagents_production_readiness.py tests/test_production_closed_loop_validation.py
```

Expected: 0 errors。

- [x] **Step 4: 运行文档残留检查**

Run:

```bash
rg -n "router\\.postgres\\.dsn|router\\.postgres_cache|QUANT_DATABASE_URL|--dsn|postgres_dsn" docs/community/info docs/community/ops docs/community/tasks vnpy vnpy_router vnpy_tradingagents tools tests -S
```

Expected: 除本 P17 计划文档和历史验证结果外无残留。

- [ ] **Step 5: 提交**

Commit message:

```bash
git commit -m "refactor: reuse vnpy postgres settings for extensions"
```

## 完成记录

| 任务 | 日期 | 提交 | 验证 |
| --- | --- | --- | --- |
| P17-T01 | 2026-05-05 | 未提交 | RED: `uv run --with pytest pytest tests/test_vnpy_native_postgres_config.py tests/test_tradingagents_production_readiness.py tests/test_production_closed_loop_validation.py tests/test_vnpy_paper_ops_integration.py::test_schema_initializer_includes_ops_heartbeat_model tests/test_production_data_sources.py::test_p9_event_source_quality_models_are_registered tests/test_tradingagents_gray_release.py::test_schema_initializer_creates_all_postgres_tables_idempotently -q` |
| P17-T02 | 2026-05-05 | 未提交 | `uv run --with pytest pytest tests/test_vnpy_native_postgres_config.py tests/test_tradingagents_production_readiness.py tests/test_data_router.py tests/test_production_closed_loop_validation.py tests/test_vnpy_paper_ops_integration.py::test_schema_initializer_includes_ops_heartbeat_model tests/test_production_data_sources.py::test_p9_event_source_quality_models_are_registered tests/test_tradingagents_gray_release.py::test_schema_initializer_creates_all_postgres_tables_idempotently -q` |
| P17-T03 | 2026-05-05 | 未提交 | `uv run --with pytest pytest tests/test_tradingagents_production_readiness.py tests/test_production_data_sources.py::test_p9_event_source_quality_models_are_registered tests/test_tradingagents_gray_release.py::test_schema_initializer_creates_all_postgres_tables_idempotently -q` |
| P17-T04 | 2026-05-05 | 未提交 | `rg -n "router\\.postgres\\.dsn|router\\.postgres_cache|QUANT_DATABASE_URL|--dsn|postgres_dsn" docs/community/info docs/community/ops docs/community/tasks vnpy vnpy_router vnpy_tradingagents tools tests -S`；当前仅 P17 计划、历史验证结果和负向测试保留旧词 |
| P17-T05 | 2026-05-05 | 未提交 | `uv run python -m tools.production.closed_loop_validation --profile local --repo-root . --output docs/community/ops/validation_results/2026-05-05-production-closed-loop-local.md --json-output docs/community/ops/validation_results/2026-05-05-production-closed-loop-local.json` |
| P17-T06 | 2026-05-05 | 未提交 | `uv run --with ruff ruff check vnpy/trader/ui/widget.py`；`docs/community/info/tradingagents_llm_env.md` 文档检查 |
| P17-T07 | 2026-05-05 | 未提交 | `rg -n "from \\.migrations|DEFAULT_MIGRATIONS|MigrationRunner|schema_migration|router\\.postgres\\.dsn|router\\.postgres_cache|QUANT_DATABASE_URL|postgres_dsn|--dsn" vnpy vnpy_router vnpy_tradingagents tools tests docs/community/info docs/community/ops docs/community/tasks/tradingagents_next_steps -S` |
| P17-T08 | 2026-05-05 | 未提交 | `uv run --with pytest pytest tests -q --ignore=tests/test_alpha101.py`；`uv run --with ruff ruff check vnpy/trader/setting.py vnpy/trader/ui/widget.py vnpy_router vnpy_tradingagents tools/production tests/test_vnpy_native_postgres_config.py tests/test_tradingagents_production_readiness.py tests/test_production_closed_loop_validation.py tests/test_production_data_sources.py tests/test_vnpy_paper_ops_integration.py tests/test_tradingagents_gray_release.py`；未提交 |
