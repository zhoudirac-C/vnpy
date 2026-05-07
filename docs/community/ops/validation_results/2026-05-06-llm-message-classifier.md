# P26 LLM 消息分类器代码级验证

日期：2026-05-06

## 验证范围

- LLM 消息分类器 runtime policy：
  - 日内/分时：`thinking=disabled`
  - 定时新闻入库：`thinking=disabled`
  - 长期研究/复盘/批量行业映射：`thinking=enabled`
- LLM 自由提名股票后，必须经过本地 `SecurityEntityCatalog` 校验。
- 无法通过本地校验的股票进入 `dropped_symbols`，不写入 `event_symbol_link`。
- `ExternalNewsIngestionJob` 在行业/宏观消息无明确个股时，可调用可选 `LlmMessageClassifier` 生成股票 link。
- UI 全局配置和 readiness 能说明/检查 `news.llm_classifier.*`。

## 验证命令

```bash
uv run --with pytest pytest tests/test_llm_message_classifier.py -q
```

结果：

```text
5 passed in 0.85s
```

```bash
uv run --with ruff ruff check vnpy_router/news_llm_classifier.py vnpy_router/news_entity.py vnpy_tradingagents/news_ingestion.py vnpy_tradingagents/readiness.py vnpy/trader/setting.py vnpy/trader/ui/widget.py tests/test_llm_message_classifier.py
```

结果：

```text
All checks passed!
```

```bash
uv run python -m tools.plantuml.check_plantuml --jar /private/tmp/plantuml-java8.jar --output-dir /private/tmp/vnpy-p26-plantuml-check docs/community/tasks/tradingagents_next_steps/26-llm-message-classifier.md docs/community/tasks/tradingagents_next_steps/25-production-news-source-entity-filtering.md
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
241 passed, 3 skipped in 2.63s
```

## 说明

本文件记录代码级验证，真实 GLM-4.7 smoke 已补充落档到：

- `docs/community/ops/validation_results/2026-05-06-llm-message-classifier-real-smoke.md`

真实结果摘要：

- `scheduled_ingestion` / `thinking=disabled`：68.61 秒，1,276 tokens。
- `batch_industry_mapping` / `thinking=enabled`：247.27 秒，3,192 tokens，其中 reasoning tokens 1,868。
