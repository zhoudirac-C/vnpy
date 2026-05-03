# P1 数据快照和可切换数据源任务

目标：把当前 provider 和写入接口扩展成可用于 Worker、回放和策略的 PostgreSQL 快照底座。

## 任务清单

- [x] **P1-T01: 实现 `PostgresSnapshotReader`**
  - 创建或扩展：`vnpy_router/storage.py`
  - 测试：`tests/test_data_router.py`
  - 能力：读取 `market_bar_snapshot`，支持 `vt_symbol/start/end/interval/provider_name` 过滤，返回 `MarketDataToolkit.load_bar_snapshots()` 需要的字典列表。
  - 验收命令：`uv run --with pytest pytest tests/test_data_router.py tests/test_tradingagents_toolkit.py -v`

- [x] **P1-T02: 补研究快照表结构**
  - 修改：`vnpy_router/storage.py`
  - 新增表建议：`fundamental_snapshot`、`valuation_snapshot`、`industry_snapshot`、`benchmark_snapshot`、`portfolio_snapshot`
  - 要求：每张表保留 `provider_name`、`provider_version`、`pulled_at`、`quality_status`，JSONB 保存 provider 原始扩展字段。
  - 验收命令：`uv run --with pytest pytest tests/test_data_router.py tests/test_tradingagents_toolkit.py -v`

- [ ] **P1-T03: 实现 `PostgresSnapshotReader.load_latest_snapshot()`**
  - 修改：`vnpy_router/storage.py` 或新增 `vnpy_router/snapshots.py`
  - 对接：`fundamentals`、`news`、`sentiment`、`benchmark`、`portfolio`
  - 缺失快照时返回 `None`，让 `MarketDataToolkit` 标记 `degraded_sources`。
  - 验收命令：`uv run --with pytest pytest tests/test_tradingagents_toolkit.py -v`

- [ ] **P1-T04: 数据源配置从硬编码扩展为 provider 配置**
  - 修改：`vnpy_router/datafeed.py`
  - 目标：从 `SETTINGS["router.providers"]` 或 JSON 配置读取 provider 顺序；保留当前 `router.local_path` 兼容；明确 AKShare 只是默认 provider 之一。
  - 验收：配置只启用 local_file 时不初始化 AKShare；配置 provider 顺序时按顺序 fallback。

- [ ] **P1-T05: PostgreSQL 缓存命中**
  - 修改：`vnpy_router/datafeed.py`、`vnpy_router/router.py`
  - 目标：`query_bar_history()` 先查 PostgreSQL 缓存，缓存缺失时再调用 provider，provider 返回后写入 `market_bar_snapshot`。
  - 验收：同一请求第二次不调用 provider；输出保留 provider trace。

- [ ] **P1-T06: 数据质量报告增强**
  - 修改：`vnpy_router/quality.py`
  - 补充检查：缺日期、重复 bar、负成交量、复权版本缺失。
  - 验收命令：`uv run --with pytest pytest tests/test_data_router.py -v`

## 完成记录

| 任务 | 日期 | 提交 | 验证 |
| --- | --- | --- | --- |
| P1-T01 | 2026-05-03 | `8a3b1d38` | `uv run --with pytest pytest tests/test_data_router.py tests/test_tradingagents_toolkit.py -v` |
| P1-T02 | 2026-05-03 | `aa6a91a9` | `uv run --with pytest pytest tests/test_data_router.py tests/test_tradingagents_toolkit.py -v` |
