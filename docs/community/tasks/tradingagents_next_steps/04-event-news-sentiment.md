# P4 新闻、公告和情绪快照任务

目标：把新闻、公告、行业事件和社媒情绪做成独立数据管线，先入 PostgreSQL，再提供给 TradingAgents。

## 任务清单

- [x] **P4-T01: 新闻和事件表结构**
  - 创建或修改：`vnpy_router/event_storage.py`
  - 表：`news_raw`、`news_event`、`social_post_raw`、`sentiment_snapshot`、`event_symbol_link`
  - 要求：原文 hash 去重；source/url/pulled_at/provider_version 可追溯。

- [x] **P4-T02: AnnouncementProvider**
  - 创建：`vnpy_router/providers/announcement.py`
  - 第一版来源：AKShare 可用公告接口、本地 CSV/JSON 人工事件。
  - 验收：可以为指定股票生成 `news_event`。

- [x] **P4-T03: NewsProvider**
  - 创建：`vnpy_router/providers/news.py`
  - 第一版目标：个股新闻、行业新闻、财报事件。
  - 约束：不承诺全网覆盖，不直接生成订单信号。

- [x] **P4-T04: SentimentProvider**
  - 创建：`vnpy_router/providers/sentiment.py`
  - 第一版：支持人工标签或新闻事件打分；社媒为空时允许 degraded。
  - 后续：雪球、股吧、微博等来源必须先做去重、反垃圾和可信度评分。

- [x] **P4-T05: EventNormalizer**
  - 创建：`vnpy_router/event_normalizer.py`
  - 目标：把 raw news/social 转成窗口摘要，关联 symbol、sector、topic，输出 TradingAgents 可读事件上下文。
  - 验收：`MarketDataToolkit` 能读取 news/sentiment 快照。

- [x] **P4-T06: 事件管线降级策略**
  - 修改：`vnpy_tradingagents/toolkit.py`
  - 目标：新闻失败时继续使用行情、财务和持仓；`degraded_sources` 包含 news/sentiment。
  - 验收：news/sentiment 缺失不影响报告生成。

## 完成记录

| 任务 | 日期 | 提交 | 验证 |
| --- | --- | --- | --- |
| P4-T01 | 2026-05-03 | `2b140dbb` | `uv run --with pytest pytest tests/test_event_pipeline.py -v` |
| P4-T02 | 2026-05-03 | `2b140dbb` | `uv run --with pytest pytest tests/test_event_pipeline.py -v` |
| P4-T03 | 2026-05-03 | `2b140dbb` | `uv run --with pytest pytest tests/test_event_pipeline.py -v` |
| P4-T04 | 2026-05-03 | `2b140dbb` | `uv run --with pytest pytest tests/test_event_pipeline.py -v` |
| P4-T05 | 2026-05-03 | `2b140dbb` | `uv run --with pytest pytest tests/test_event_pipeline.py -v` |
| P4-T06 | 2026-05-03 | `2b140dbb` | `uv run --with pytest pytest tests/test_event_pipeline.py -v` |
