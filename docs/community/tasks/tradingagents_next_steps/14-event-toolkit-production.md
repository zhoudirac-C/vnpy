# P14 事件管线和 MarketDataToolkit 生产化任务

目标：把新闻、公告、社媒、情绪、行业、benchmark、持仓和质量信息真正接入 TradingAgents 上下文。外部事件先入库、归一化、打来源标记，再由 `MarketDataToolkit` 按窗口读取，不能由 TradingAgents 临时抓取。

## 任务清单

- [x] **P14-T01: normalized event 存储读写**
  - 修改：`vnpy_router/event_storage.py`
  - 测试：`tests/test_event_pipeline.py`
  - 目标：补齐 `news_event`、`event_symbol_link`、`sentiment_snapshot`、`event_quality_report` 的 save/read 接口。
  - 验收：可以按 `vt_symbol/start/end/source/quality_status` 读取事件窗口。

- [x] **P14-T02: 新闻和公告 provider 入库闭环**
  - 修改：`vnpy_router/providers/news.py`、`vnpy_router/providers/announcement.py`、`vnpy_router/event_normalizer.py`
  - 目标：本地文件或后续实时来源先写 raw，再归一化为 event，保留 provider、hash、抓取时间和审核状态。
  - 验收：无来源、无 provider、重复 hash、低质量事件不会进入 TradingAgents context。

- [x] **P14-T03: 社媒情绪生产规则**
  - 修改：`vnpy_router/providers/social.py`、`vnpy_router/providers/sentiment.py`
  - 目标：社媒只作为上下文，不直接生成订单；人工标签优先，模型情绪必须带 scorer version 和置信度。
  - 验收：情绪缺失时 Toolkit 标记 degraded，不阻塞行情和财务上下文。

- [x] **P14-T04: MarketDataToolkit 上下文补齐**
  - 修改：`vnpy_tradingagents/toolkit.py`
  - 测试：`tests/test_tradingagents_toolkit.py`
  - 目标：补行情指标、估值、行业、benchmark、portfolio、新闻窗口、情绪窗口和数据质量摘要。
  - 验收：`build_context()` 输出能区分 `market/fundamentals/valuation/industry/news/sentiment/benchmark/portfolio` 的可用和 degraded 状态。

- [x] **P14-T05: A 股交易规则和日内压缩上下文**
  - 修改：`vnpy_tradingagents/intraday.py`、`vnpy_tradingagents/intraday_collector.py`
  - 目标：日内输入不是原始 tick 洪流，而是压缩后的价格位置、均线、成交量、盘口摘要、新闻事件、当前持仓和交易纪律。
  - 验收：日内 context 体积可控，且能在新闻/情绪缺失时正常降级。

- [x] **P14-T06: 清理未接入的事件占位代码**
  - 修改或删除：过时的 event provider helper、未被任何生产路径调用的 normalizer 占位函数
  - 目标：去掉“看起来已接入但实际只在单测中用”的事件代码，保留的 helper 必须有生产调用路径或 smoke-only 标记。
  - 验收：事件管线从 provider/raw storage/normalizer/snapshot reader/toolkit 的调用链完整可追踪。

## 完成记录

| 任务 | 日期 | 提交 | 验证 |
| --- | --- | --- | --- |
| P14-T01 | 2026-05-04 | 未提交 | `uv run --with pytest pytest tests/test_event_pipeline.py -q` |
| P14-T02 | 2026-05-04 | 未提交 | `uv run --with pytest pytest tests/test_event_pipeline.py tests/test_production_data_sources.py -q` |
| P14-T03 | 2026-05-04 | 未提交 | `uv run --with pytest pytest tests/test_event_pipeline.py tests/test_production_data_sources.py -q` |
| P14-T04 | 2026-05-04 | 未提交 | `uv run --with pytest pytest tests/test_tradingagents_toolkit.py tests/test_event_pipeline.py -q` |
| P14-T05 | 2026-05-04 | 未提交 | `uv run --with pytest pytest tests/test_tradingagents_intraday_collector.py tests/test_tradingagents_intraday.py -q` |
| P14-T06 | 2026-05-04 | 未提交 | `uv run --with ruff ruff check vnpy_router/event_storage.py vnpy_tradingagents/toolkit.py` |
