# P12 vn.py 复用纠偏和多余代码清理任务

目标：把 P1-P11 的骨架实现收回到 vn.py 原生扩展点上，优先复用 Datafeed、Database、Gateway、App、EventEngine、OmsEngine、Backtesting 和 Risk 体系，并清理不再符合新路线的旁路实现。

## 任务清单

- [x] **P12-T01: 文档状态和任务规则纠偏**
  - 修改：`docs/community/info/custom_quant_architecture.md`、`docs/community/tasks/tradingagents_next_steps/README.md`
  - 目标：把 P1-P11 明确标为“骨架完成”，不能再写成生产完成；所有新任务完成后必须更新任务勾选、完成记录、提交号和验证命令。
  - 验收：文档中不再出现“QMT/XT 直接补成真实 provider”这类与新路线冲突的推荐。

- [x] **P12-T02: PostgreSQL 真实连接修复**
  - 修改：`vnpy_router/datafeed.py`、`vnpy_tradingagents/cli.py`、`vnpy_tradingagents/migrations.py`
  - 测试：新增或修改 `tests/test_tradingagents_production_readiness.py`、`tests/test_data_router.py`
  - 目标：早期先修复 PostgreSQL raw cursor 默认返回 tuple 导致 row 字典访问失败的问题。
  - 验收：真实 PostgreSQL 或容器化 PostgreSQL 下，schema init/status、bar snapshot 读写、migration status 都可运行。
  - P17 纠错：该任务只解决了当时的 dict row 问题，但技术路线仍偏离 `vnpy_postgresql`。P17 将把扩展表初始化从自建 SQL migration runner 改为 Peewee Model + `create_tables(..., safe=True)`，并删除独立 DSN 入口。

- [x] **P12-T03: QMT/XT provider 路线纠偏**
  - 修改：`vnpy_router/datafeed.py`、`vnpy_router/providers/qmt.py`、`vnpy_router/providers/xt.py`、`vnpy_router/providers/__init__.py`
  - 目标：废弃直接实现 `QmtProvider` / `XtProvider` 的路线，新增或规划 `VnpyDatafeedProvider`，优先包装 vn.py 已有 `vnpy_xt`、`vnpy_rqdata` 等数据服务。
  - 验收：未安装 QMT/XT 依赖时不再暴露“待实现 direct provider”的假能力；文档和代码诊断都提示复用 vn.py 插件。

- [x] **P12-T04: 标准行情数据回归 vn.py Database 边界**
  - 修改：`vnpy_router/router.py`、`vnpy_router/storage.py`、`docs/community/info/vnpy_reuse_extension_route.md`
  - 目标：明确 bar/tick 的标准存储优先走 vn.py Database；本 fork 的扩展表只保存 provider trace、quality、AI 研究快照和事件上下文。
  - 验收：代码注释、文档和测试都不再把 `market_bar_snapshot` 描述为唯一行情主库。

- [x] **P12-T05: 清理多余旁路代码**
  - 修改或删除：`vnpy_router/providers/qmt.py`、`vnpy_router/providers/xt.py`、生产路径中引用的 paper-only bridge、过时的 task 描述
  - 目标：删除或降级不再使用的 direct provider、生产化误导性 bridge、未接入的占位实现；保留 smoke/test helper 时必须在命名和文档中标明 smoke-only。
  - 验收：`rg "not configured yet|Placeholder for QMT|Placeholder for XT|真实实现"` 不再发现会误导生产路线的占位描述。

- [x] **P12-T06: 依赖分组和安装说明**
  - 修改：`pyproject.toml`、`docs/community/info/vnpy_reuse_extension_route.md`
  - 目标：把 Peewee PostgreSQL 扩展、`akshare`、`tushare` 等主进程依赖拆成可选 extras；TradingAgents 作为可选运行依赖安装并由 context-only factory 懒加载，避免未启用 AI 时污染 vn.py 主链路。
  - 验收：文档说明 `router-postgres`、`akshare`、`tushare`、`prod` 等安装组合，并明确 TradingAgents 可选安装；无对应 extra 时 readiness 能给出明确诊断。

## 完成记录

| 任务 | 日期 | 提交 | 验证 |
| --- | --- | --- | --- |
| P12-T01 | 2026-05-04 | 未提交 | `uv run --with pytest pytest tests -q --ignore=tests/test_alpha101.py` |
| P12-T02 | 2026-05-04 | 未提交 | `uv run --with pytest pytest tests/test_data_router.py tests/test_tradingagents_production_readiness.py -q` |
| P12-T03 | 2026-05-04 | 未提交 | `uv run --with pytest pytest tests/test_production_data_sources.py -q` |
| P12-T04 | 2026-05-04 | 未提交 | `uv run --with pytest pytest tests/test_data_router.py tests/test_tradingagents_toolkit.py -q` |
| P12-T05 | 2026-05-04 | 未提交 | `uv run --with ruff ruff check vnpy_router vnpy_tradingagents` |
| P12-T06 | 2026-05-04 | 未提交 | `uv run --with ruff ruff check pyproject.toml docs/community/info/vnpy_reuse_extension_route.md` |
