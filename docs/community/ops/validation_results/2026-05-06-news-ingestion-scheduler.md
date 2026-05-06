# P24 外部新闻入库定时任务验证结果

日期：2026-05-06

## 验证目标

验证第一版外部新闻入库链路具备代码级可用性：

- AKShare 个股新闻 provider 可以把外部接口返回行转换为 `NewsRaw`。
- AKShare 缺依赖或接口失败时降级，不抛出到主链路。
- AKShare 全局财经新闻不强行关联到单个股票。
- provider chain 可以继续执行后续 provider，并按 `raw_hash/vt_symbol` 去重。
- `ExternalNewsIngestionJob` 可以写入 `news_raw` 和 `news_event`，并记录 heartbeat。
- `ExternalNewsIngestionScheduler` 可以复用 EventEngine timer 并在后台线程执行。
- readiness 和 UI help 能说明新闻入库配置和降级状态。

## 验证命令

```bash
uv run --with pytest pytest tests/test_news_ingestion_scheduler.py tests/test_event_pipeline.py tests/test_tradingagents_production_readiness.py tests/test_tradingagents_llm_secret_ui.py -q

uv run --with ruff ruff check vnpy_router/providers/news_external.py vnpy_tradingagents/news_ingestion.py vnpy_tradingagents/readiness.py vnpy/trader/setting.py vnpy/trader/ui/widget.py vnpy_tradingagents/__init__.py tests/test_news_ingestion_scheduler.py

uv run python -m tools.plantuml.check_plantuml --jar /private/tmp/plantuml-java8.jar --output-dir /private/tmp/vnpy-p24-plantuml-check docs/community/info/tradingagents_news_query_sequence.md docs/community/tasks/tradingagents_next_steps/24-news-ingestion-scheduler.md
```

## 验证结果

| 项目 | 结果 |
| --- | --- |
| P24 单测 | 通过，`10 passed` |
| 事件管线/readiness/UI 相关回归 | 通过，合计 `32 passed` |
| Ruff | 通过 |
| PlantUML | 通过，`Checked 3 PlantUML block(s).` |

## 说明

本次验证没有直接访问公网 AKShare 新闻接口；AKShare 成功路径通过 fake module 验证，缺依赖路径通过 monkeypatch 验证。

因此当前可以声明：

- 第一版“外部新闻 provider -> 入库 job -> PostgreSQL 事件表 -> TradingAgents context”代码级闭环已具备。
- 新闻入库默认关闭，公开源失败只 degraded。

当前不能声明：

- AKShare 新闻公网接口已完成连续稳定性验证。
- 新闻源已经达到生产 SLA。
- 社媒情绪抓取已经覆盖。

