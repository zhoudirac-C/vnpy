# P25 生产级新闻/公告数据源与实体过滤代码级验证

日期：2026-05-06

## 验证范围

本次验证覆盖 P25 的代码级能力：

- CNINFO/巨潮公告 Provider fixture 转换。
- 上交所公告 Provider fixture 转换。
- GDELT GlobalNews Provider fixture 转换。
- 股票实体目录、名称/简称/代码/别名识别和歧义别名阻断。
- 新闻分类、可信度评分、重复合并。
- `ExternalNewsIngestionJob` 生成多标的 `event_symbol_link`。
- `MarketDataToolkit` 过滤低可信、低相关或不允许类型的新闻。
- readiness 识别 P25 provider，并在官方公告开启但缺实体目录时给 warning。
- Peewee extension table 继续复用 vn.py `database.*` 初始化路径。

## 验证命令

```bash
uv run --with pytest pytest tests/test_news_entity_filtering.py tests/test_production_news_sources.py -q
```

结果：

```text
7 passed in 0.72s
```

```bash
uv run --with pytest pytest tests/test_news_ingestion_scheduler.py tests/test_event_pipeline.py tests/test_tradingagents_toolkit.py tests/test_production_data_sources.py::test_p9_event_source_quality_models_are_registered tests/test_tradingagents_production_readiness.py -q
```

结果：

```text
27 passed in 1.36s
```

```bash
uv run --with ruff ruff check vnpy_router/security_catalog.py vnpy_router/news_entity.py vnpy_router/news_classifier.py vnpy_router/news_quality.py vnpy_router/news_dedup.py vnpy_router/news_taxonomy.py vnpy_router/providers/news_external.py vnpy_router/event_storage.py vnpy_router/extension_models.py vnpy_tradingagents/news_ingestion.py vnpy_tradingagents/toolkit.py vnpy_tradingagents/readiness.py vnpy_tradingagents/__init__.py vnpy/trader/setting.py vnpy/trader/ui/widget.py tests/test_news_entity_filtering.py tests/test_production_news_sources.py
```

结果：

```text
All checks passed!
```

```bash
uv run python -m tools.plantuml.check_plantuml --jar /private/tmp/plantuml-java8.jar --output-dir /private/tmp/vnpy-p25-plantuml-check docs/community/tasks/tradingagents_next_steps/25-production-news-source-entity-filtering.md docs/community/tasks/tradingagents_next_steps/24-news-ingestion-scheduler.md
```

结果：

```text
Checked 3 PlantUML block(s).
```

```bash
uv run --with pytest pytest tests -q --ignore=tests/test_alpha101.py -p no:cacheprovider
```

结果：

```text
237 passed, 3 skipped in 2.59s
```

## 结论

P25 代码级闭环已具备：

- 官方公告、全球宏观新闻、AKShare 补充源可以进入统一 provider chain。
- 新闻先落 `news_raw`，再做实体识别、分类、评分、去重，最后生成 `news_event` 和 `event_symbol_link`。
- TradingAgents 上下文默认只保留高可信、高关联、事件类型允许、数量受控的摘要。
- 低可信 AKShare 新闻仍可入库留痕，但不会默认进入 TradingAgents context。

## 真实公网 Smoke

P25-T17 真实公网 smoke 已补充落档到：

- `docs/community/ops/validation_results/2026-05-06-production-news-v2-real-smoke.md`

真实结果摘要：

- CNINFO/巨潮：6 条，成功。
- AKShare：9 条，成功。
- 上交所公告：0 条，本窗口为空。
- GDELT：429 降级。
- PostgreSQL 入库：`raw_count=15`，`event_count=15`。

仍未覆盖连续 5 个交易日定时运行稳定性和实体识别误链率抽样。
