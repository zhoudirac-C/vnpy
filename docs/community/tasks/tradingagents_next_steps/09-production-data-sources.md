# P9 生产数据源和事件源接入任务

目标：把当前 local_file/AKShare 起步能力扩展为真实可切换数据源链路，并补齐新闻、公告、社媒情绪的生产化入库规则。

## 任务清单

- [x] **P9-T01: Provider 能力矩阵**
  - 创建：`vnpy_router/providers/capability.py`
  - 目标：声明每个 provider 支持的频率、字段、复权、tick、实时能力和成本等级。
  - 验收：router 可按能力过滤 provider，而不只是按名字顺序尝试。

- [x] **P9-T02: TuShareProvider**
  - 创建：`vnpy_router/providers/tushare.py`
  - 目标：支持 token 配置、日线/复权/指数/基础财务。
  - 验收：无 token 时明确 degraded；有 token 时能写 provider metadata。

- [x] **P9-T03: QMT/XT 历史数据适配接口**
  - 创建：`vnpy_router/providers/qmt.py`、`vnpy_router/providers/xt.py`
  - 目标：定义开通后接入点，区分历史数据和实时 Gateway。
  - 验收：未安装依赖时可诊断，不影响其他 provider。

- [x] **P9-T04: 事件源生产规则**
  - 修改：`vnpy_router/event_storage.py`
  - 目标：补 source quality、可信度、反垃圾、去重窗口和人工审核状态。
  - 验收：新闻/社媒不能无来源进入 TradingAgents context。

- [x] **P9-T05: 新闻/社媒 provider 插件**
  - 创建：`vnpy_router/providers/social.py`
  - 目标：先支持本地导入和人工标签，后续再接雪球/股吧/微博。
  - 验收：社媒缺失只降级，不阻塞 market/fundamental context。

## 完成记录

| 任务 | 日期 | 提交 | 验证 |
| --- | --- | --- | --- |
| P9-T01 | 2026-05-04 | `3987baac` | `uv run --with pytest pytest tests/test_production_data_sources.py tests/test_data_router.py tests/test_event_pipeline.py tests/test_tradingagents_production_readiness.py tests/test_tradingagents_toolkit.py tests/test_tradingagents_source_policy.py -v` |
| P9-T02 | 2026-05-04 | `3987baac` | `uv run --with pytest pytest tests/test_production_data_sources.py tests/test_data_router.py tests/test_event_pipeline.py tests/test_tradingagents_production_readiness.py tests/test_tradingagents_toolkit.py tests/test_tradingagents_source_policy.py -v` |
| P9-T03 | 2026-05-04 | `3987baac` | `uv run --with pytest pytest tests/test_production_data_sources.py tests/test_data_router.py tests/test_event_pipeline.py tests/test_tradingagents_production_readiness.py tests/test_tradingagents_toolkit.py tests/test_tradingagents_source_policy.py -v` |
| P9-T04 | 2026-05-04 | `3987baac` | `uv run --with pytest pytest tests/test_production_data_sources.py tests/test_data_router.py tests/test_event_pipeline.py tests/test_tradingagents_production_readiness.py tests/test_tradingagents_toolkit.py tests/test_tradingagents_source_policy.py -v` |
| P9-T05 | 2026-05-04 | `3987baac` | `uv run --with ruff ruff check vnpy_router/providers/capability.py vnpy_router/providers/tushare.py vnpy_router/providers/qmt.py vnpy_router/providers/xt.py vnpy_router/providers/social.py vnpy_router/router.py vnpy_router/datafeed.py vnpy_router/event_storage.py vnpy_router/event_normalizer.py vnpy_router/providers/akshare.py vnpy_router/providers/local_file.py vnpy_router/providers/event_file.py vnpy_router/providers/__init__.py vnpy_tradingagents/readiness.py vnpy_tradingagents/schema_init.py tests/test_production_data_sources.py` |
