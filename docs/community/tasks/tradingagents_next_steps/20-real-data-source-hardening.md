# P20 真实数据源增强任务

目标：把当前 local_file/AKShare 起步能力推进到可切换、可诊断、可交叉校验的数据源链路。生产设计继续复用 vn.py Datafeed/Database，不把 AKShare 写死。

## 任务清单

- [x] **P20-T01: AKShare 能力边界落库**
  - 目标：明确 AKShare 当前支持的 A 股日线/周线能力、缺失的分钟/tick/实时盘口能力，并在 readiness 和 provider metadata 中输出。
  - 验收：请求不支持的 interval 时返回结构化诊断，不被误判为 provider 故障。

- [ ] **P20-T02: BaoStock/efinance 候选 provider 调研和接入计划**
  - 目标：形成公开数据源 fallback 的实现计划，优先覆盖 A 股日线和基础信息。
  - 验收：任务文档明确依赖、字段、限制、合规提醒和是否进入代码阶段。

- [ ] **P20-T03: provider 抽样交叉校验**
  - 目标：同一标的同一日期从两个 provider 或 provider+本地快照对比 OHLCV，输出质量报告。
  - 验收：质量报告记录差异字段、容忍阈值、provider_name、provider_version。

- [ ] **P20-T04: 分钟线生产来源决策**
  - 目标：明确日内 TradingAgents 分时建议依赖的分钟线来自 QMT/XT Gateway、付费 datafeed、AKShare 补充源还是本地导入。
  - 验收：没有稳定分钟线前，日内建议 readiness 只能 degraded。

## 完成记录

| 任务 | 日期 | 提交 | 验证 |
| --- | --- | --- | --- |
| P20-T01 | 2026-05-05 | 未提交 | `uv run --with pytest pytest tests/test_production_data_sources.py::test_akshare_provider_declares_research_only_boundaries -q` |
| P20-T02 | 未完成 | 未提交 | 未运行 |
| P20-T03 | 未完成 | 未提交 | 未运行 |
| P20-T04 | 未完成 | 未提交 | 未运行 |
