# P20 真实数据源增强任务

目标：把当前 local_file/AKShare 起步能力推进到可切换、可诊断、可交叉校验的数据源链路。生产设计继续复用 vn.py Datafeed/Database，不把 AKShare 写死。

## 任务清单

- [x] **P20-T01: AKShare 能力边界落库**
  - 目标：明确 AKShare 当前支持的 A 股日线/周线能力、缺失的分钟/tick/实时盘口能力，并在 readiness 和 provider metadata 中输出。
  - 验收：请求不支持的 interval 时返回结构化诊断，不被误判为 provider 故障。

- [x] **P20-T02: BaoStock/efinance 候选 provider 调研和接入计划**
  - 目标：形成公开数据源 fallback 的实现计划，优先覆盖 A 股日线和基础信息。
  - 验收：任务文档明确依赖、字段、限制、合规提醒和是否进入代码阶段。

- [x] **P20-T03: provider 抽样交叉校验**
  - 目标：同一标的同一日期从两个 provider 或 provider+本地快照对比 OHLCV，输出质量报告。
  - 验收：质量报告记录差异字段、容忍阈值、provider_name、provider_version。

- [x] **P20-T04: 分钟线生产来源决策**
  - 目标：明确日内 TradingAgents 分时建议依赖的分钟线来自 QMT/XT Gateway、付费 datafeed、AKShare 补充源还是本地导入。
  - 验收：没有稳定分钟线前，日内建议 readiness 只能 degraded。

- [x] **P20-T05: AKShare 内部多 endpoint 降级**
  - 目标：在 `AkshareProvider` 内部增加 A 股日线 endpoint 链式降级，避免单个公开网页源失败时直接返回空数据。
  - 验收：`stock_zh_a_hist` 失败时继续尝试 `stock_zh_a_hist_tx`，返回的 `BarData.extra["provider_endpoint"]` 记录真实命中的 endpoint。

## 完成记录

| 任务 | 日期 | 提交 | 验证 |
| --- | --- | --- | --- |
| P20-T01 | 2026-05-05 | 未提交 | `uv run --with pytest pytest tests/test_production_data_sources.py::test_akshare_provider_declares_research_only_boundaries -q` |
| P20-T02 | 2026-05-05 | 未提交 | 文档调研：BaoStock、efinance、`vnpy_baostock` |
| P20-T03 | 2026-05-05 | 未提交 | `uv run --with pytest pytest tests/test_data_router.py::test_provider_cross_check_reports_ohlcv_differences -q` |
| P20-T04 | 2026-05-05 | 未提交 | `uv run --with pytest pytest tests/test_production_data_sources.py::test_readiness_checker_reports_production_provider_diagnostics -q` |
| P20-T05 | 2026-05-06 | 未提交 | `uv run --with pytest pytest tests/test_production_data_sources.py::test_akshare_provider_falls_back_between_internal_endpoints tests/test_data_router.py::test_datafeed_passes_akshare_internal_endpoint_config -q` |

## P20-T02 调研结论和接入计划

### BaoStock

- 现有方案：PyPI 上已有 `vnpy-baostock`，说明是 vn.py 的 BaoStock datafeed，支持中国 A 股 SSE/SZSE K 线，并通过 vn.py 全局配置 `datafeed.name=baostock` 使用。
- 技术路线：本 fork 不直接重写 BaoStock SDK。需要使用时，优先安装 `vnpy_baostock`，再通过 `router.providers=[{"name":"vnpy","datafeed":"baostock"}]` 走 `VnpyDatafeedProvider` 包装。
- 定位：A 股日线/历史 K 线 fallback 候选。进入生产候选前必须跑 provider trace、字段映射、复权口径和交易日抽样校验。
- 风险：`vnpy-baostock` 发布较早，需在当前 Python/vn.py 版本下单独联调；若不兼容，才考虑实现最薄 BaoStock provider。

### efinance

- 现有方案：`efinance` 是个人维护的东方财富数据 Python 包，可取股票、基金、债券、期货等数据；项目说明强调仅供学习交流，不得用于商业用途。
- 技术路线：不进入默认依赖，不作为生产默认 provider。若后续需要补低门槛公开源，可新增 `EfinanceProvider`，只覆盖 A 股日线/基础行情，依赖放入 optional extra。
- 定位：AKShare 失效时的研究 fallback，不承担实盘、分钟线、tick、盘口、交易职责。
- 风险：公开网页源限流、接口变化、非商业声明。生产 readiness 只能 degraded，除非后续有明确授权和稳定性验证。

### 下一步实现顺序

1. P20-T03 先做 provider 抽样交叉校验，不新增 provider 也能用 AKShare/local_file 验证质量报告结构。
2. 如果需要 BaoStock，优先验证 `VnpyDatafeedProvider(datafeed_name="baostock")` 是否能包装现有 `vnpy_baostock`。
3. efinance 只有在 AKShare/BaoStock 都不能满足研究 fallback 时再写 provider，且必须在文档和 readiness 中标记非生产默认源。

## P20-T04 分钟线生产来源决策

当前决策：日内 TradingAgents 分时建议不能依赖 AKShare 日线 provider。生产分钟线只接受以下来源进入 ready：

- QMT/XT 对应 vn.py 插件可用，例如 `vnpy_xt`。
- 后续明确验证过的付费 vn.py datafeed 插件，且能稳定返回分钟 K 线。
- 人工导入或本地 fixture 只能用于回测/复盘，不作为生产日内 ready。

启用 `tradingagents.intraday.enabled=true` 时，readiness 新增 `intraday_minute_source`：

- 配置 `qmt`/`xt` 且 `vnpy_xt` 可导入时为 `ready`。
- 配置 `qmt`/`xt` 但插件不可导入时为 `warning`。
- 只有 AKShare、TuShare、local_file 或社媒/新闻源时为 `warning`，日内 AI 必须 degraded。
- 未启用日内 TradingAgents 时为 `ready`，不拖累长期研究、复盘或普通生产 readiness。

### 资料来源

- BaoStock vn.py datafeed：`https://pypi.org/project/vnpy-baostock/`
- efinance PyPI：`https://pypi.org/project/efinance/`
- efinance GitHub：`https://github.com/Micro-sheep/efinance`
