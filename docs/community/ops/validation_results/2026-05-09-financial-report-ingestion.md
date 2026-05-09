# 财报入库链路验证

验证日期：2026-05-09

## 范围

- 财报扩展表注册和 PostgreSQL storage SQL。
- AKShare 三大报表、财务指标 Provider 的结构化转换。
- 巨潮/交易所官方报告 Provider 的公告 PDF 元数据转换。
- 财报质量评分、TradingAgents 摘要快照和 `MarketDataToolkit.financials` 上下文。
- TradingAgents 分析管理中的“财报数据”Tab、手动查询和手动回补入口。

## 已执行验证

| 命令 | 结果 |
| --- | --- |
| `uv run --with pytest pytest tests/test_financial_report_ingestion.py::test_official_financial_report_providers_convert_document_metadata tests/test_financial_report_ingestion.py::test_financial_quality_scorer_marks_primary_only_with_complete_sources tests/test_financial_report_ingestion.py::test_financial_snapshot_builder_includes_quality_report tests/test_financial_report_ingestion.py::test_engine_delegates_financial_reader_and_manual_trigger tests/test_tradingagents_ui.py::test_financial_context_tab_has_refresh_and_trigger_helpers -q` | 5 passed |
| `uv run --with pytest pytest tests/test_financial_report_ingestion.py::test_postgres_financial_storage_saves_and_loads_context_rows -q` | 1 passed |
| `uv run --with pytest pytest tests/test_financial_report_ingestion.py tests/test_tradingagents_ui.py tests/test_tradingagents_app_bootstrap.py -q` | 40 passed |
| `uv run --with pytest pytest tests/test_tradingagents_app_bootstrap.py::test_configure_tradingagents_services_starts_financial_scheduler_by_default -q` | 1 passed |
| `uv run --with ruff ruff check vnpy_router/providers/financial.py vnpy_router/financial_storage.py vnpy_tradingagents/financial_ingestion.py vnpy_tradingagents/engine.py vnpy_tradingagents/bootstrap.py vnpy_tradingagents/ui/widget.py vnpy/trader/setting.py vnpy/trader/ui/widget.py tests/test_financial_report_ingestion.py tests/test_tradingagents_ui.py tests/test_tradingagents_app_bootstrap.py tools/production/financial_ingestion_smoke.py` | All checks passed |
| `uv run --with pytest pytest -q --ignore=tests/test_alpha101.py` | 316 passed, 3 skipped, 2 warnings |
| `pg_isready -h localhost -p 5432` | `localhost:5432 - accepting connections` |
| `uv run python -m tools.production.financial_ingestion_smoke --symbols 600519.SSE,000001.SZSE,688008.SSE --lookback-years 2 --write-validation-doc` | 真实公网 Provider + PostgreSQL smoke 通过，生成 `docs/community/ops/validation_results/2026-05-09-210449-financial-ingestion-smoke.md` |
| `uv run python /private/tmp/p28_t10_point_in_time.py` | 点时校验通过：公告日前不读取未来一季报，公告日后读取 2026-03-31 |
| `uv run python /private/tmp/p28_t10_toolkit_context.py` | `MarketDataToolkit` 上下文包含 `financials`，且 `financials` 未进入 degraded_sources |

## P28-T10 真实 PostgreSQL + 公网 Provider 验证

验证时间：2026-05-09 21:03-21:04 Asia/Shanghai

本地 vn.py 数据库配置：

| 配置 | 值 |
| --- | --- |
| `database.name` | `postgresql` |
| `database.host` | `127.0.0.1` |
| `database.port` | `5432` |
| `database.database` | `vnpy` |
| `database.user` | `vnpy` |
| `database.password` | 已配置，未在文档落明文 |

真实 smoke 结果：

| 指标 | 值 |
| --- | ---: |
| `statement_count` | 360 |
| `indicator_count` | 60 |
| `document_count` | 22 |
| `payload_snapshot_count` | 6 |
| `degraded_sources` | 0 |
| `errors` | 0 |

本次入库后的 PostgreSQL 计数：

| 表 | 新写入/更新行数 | 股票数 |
| --- | ---: | ---: |
| `financial_statement_snapshot` | 360 | 3 |
| `financial_indicator_snapshot` | 60 | 3 |
| `financial_report_document` | 22 | 2 |
| `fundamental_snapshot` | 3 | 3 |
| `valuation_snapshot` | 3 | 3 |

三大报表覆盖：

| 股票 | 报表类型 | 行数 | 最早报告期 | 最新报告期 | 最新公告日 |
| --- | --- | ---: | --- | --- | --- |
| `000001.SZSE` | `balance_sheet` | 40 | 2021-06-30 | 2026-03-31 | 2026-04-25 |
| `000001.SZSE` | `cash_flow` | 40 | 2021-06-30 | 2026-03-31 | 2026-04-25 |
| `000001.SZSE` | `income_statement` | 40 | 2021-06-30 | 2026-03-31 | 2026-04-25 |
| `600519.SSE` | `balance_sheet` | 40 | 2021-06-30 | 2026-03-31 | 2026-04-25 |
| `600519.SSE` | `cash_flow` | 40 | 2021-06-30 | 2026-03-31 | 2026-04-25 |
| `600519.SSE` | `income_statement` | 40 | 2021-06-30 | 2026-03-31 | 2026-04-25 |
| `688008.SSE` | `balance_sheet` | 40 | 2021-06-30 | 2026-03-31 | 2026-04-28 |
| `688008.SSE` | `cash_flow` | 40 | 2021-06-30 | 2026-03-31 | 2026-04-28 |
| `688008.SSE` | `income_statement` | 40 | 2021-06-30 | 2026-03-31 | 2026-04-28 |

官方报告元数据：

| 股票 | 文档数 | 来源 | 说明 |
| --- | ---: | --- | --- |
| `600519.SSE` | 12 | `cninfo` | 年报、半年报、一季报等公告元数据已入库 |
| `688008.SSE` | 10 | `cninfo` | 年报、半年报、一季报等公告元数据已入库 |
| `000001.SZSE` | 0 | - | 本次 CNINFO 查询窗口未返回匹配报告文档；三大报表、财务指标和摘要快照已入库 |

样例字段验证：

| 表 | 股票/报告期 | 字段 | 结果 |
| --- | --- | --- | --- |
| `financial_statement_snapshot` | `600519.SSE` / `2026-03-31` | `TOTAL_ASSETS` | 资产负债表存在 |
| `financial_statement_snapshot` | `600519.SSE` / `2026-03-31` | `OPERATE_INCOME` | 利润表存在 |
| `financial_statement_snapshot` | `600519.SSE` / `2026-03-31` | `NETCASH_OPERATE` | 现金流量表存在 |
| `financial_indicator_snapshot` | `600519.SSE` / `2026-03-31` | `ROEJQ`、`ZCFZL`、`XSMLL` | 财务指标存在 |

点时过滤验证：

| 股票 | 查询时间 | 读取到的最新报表期 | 说明 |
| --- | --- | --- | --- |
| `600519.SSE` | 2026-04-24 23:59:59 | 2025-12-31 | 2026 一季报公告日为 2026-04-25，公告前不可见 |
| `600519.SSE` | 2026-04-26 00:00:00 | 2026-03-31 | 公告后可见 |
| `688008.SSE` | 2026-04-27 23:59:59 | 2025-12-31 | 2026 一季报公告日为 2026-04-28，公告前不可见 |
| `688008.SSE` | 2026-04-29 00:00:00 | 2026-03-31 | 公告后可见 |

TradingAgents 上下文验证：

`MarketDataToolkit` 对 `600519.SSE`、窗口 `2026-01-01` 到 `2026-04-26` 构造上下文时：

- `financials.quality_status=primary`
- `financials.statements` 包含 `balance_sheet`、`income_statement`、`cash_flow`
- `financials.indicators` 数量为 4
- `financials.documents` 数量为 4
- `degraded_sources` 不包含 `financials`

## 修复记录

真实 smoke 暴露两个问题，已在本次验证前修复并补充单测：

- AKShare/东方财富三大报表的 `报告日`、`公告日期` 会以 `YYYYMMDD` 字符串返回，原解析会误按 Unix timestamp 处理。现在优先按 8 位日期解析，并把 `报告日` 加入报告期候选字段。
- `stock_financial_analysis_indicator()` 在当前环境对样例股票返回空数据。现在 `AkshareFinancialIndicatorProvider` 会先尝试旧接口，空结果时降级到 `stock_financial_analysis_indicator_em(symbol=600519.SH, indicator=按报告期)`。

## 结论

- P28-T10 已完成真实端到端验证：公网 Provider → PostgreSQL 表 → `fundamental_snapshot`/`valuation_snapshot` → `MarketDataToolkit.financials` → 点时过滤。
- 代码级财报链路已经闭合：Provider → `financial_*` 表 → TradingAgents snapshot/context → UI 查询。
- 官方报告元数据已经进入统一 Provider 链，默认 Provider 顺序为 `akshare_sina,akshare_eastmoney,akshare_indicator,cninfo_report,exchange_report`。
- `financial.ingestion.enabled=true` 时，vn.py 启动会注册财报定时任务；任务等待盘后/早晨调度或 UI 手动触发，不会在启动瞬间全市场拉取。

## 剩余风险

- 真实公开接口可能限流、返回字段漂移或临时不可用；生产前仍建议定期跑 `tools.production.financial_ingestion_smoke` 并检查样例字段。
- 交易所 Provider 目前先接上交所入口，深交所/北交所官方入口后续可在 `exchange_report` 同一 Provider 名称下扩展。
- CNINFO/公开接口对不同股票的官方报告匹配覆盖不完全，本次 `000001.SZSE` 没有返回官方文档，但结构化三大报表和指标已入库。
- `tests/test_alpha101.py` 未纳入本次全量回归，原因是 alpha extra 依赖 `polars/alphalens` 在当前环境仍是可选依赖边界。
