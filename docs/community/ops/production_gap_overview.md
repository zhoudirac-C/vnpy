# 生产可用性差距总览

日期：2026-05-05

## 已实现

- vn.py 原生 PostgreSQL 配置复用：扩展表初始化走 Peewee `create_tables()`，不再使用独立 DSN。
- `vnpy_router.Datafeed`：支持 local_file、AKShare、TuShare 边界、QMT/XT vn.py 插件 wrapper、provider capability 和 snapshot cache 降级。
- TradingAgents context-only Worker：默认 factory 内置，工具只能读取本地 context，不直接访问 yfinance、AKShare、TuShare、QMT、Gateway 或 MainEngine。
- LLM UI 配置：provider、model、base_url、thinking、超时和 API key 安全输入框已接入。
- 回测闭环：P19 已用 vn.py `BacktestingEngine` 跑通 K 线、AI 信号、风控审计和回测结果落档。
- Podman E2E：真实 PostgreSQL 容器、schema、readiness、paper smoke、持久化重启验证通过。

## Smoke 通过但仍需生产补强

- 真实 LLM：BigModel/GLM-4.7 单轮 TradingAgents smoke 通过，但还没有批量股票池、成本预算、失败重试和真实 PostgreSQL 快照入库连续验证。
- 日内 TradingAgents：已有限流、thinking/timeout 配置和 readiness 分钟源检查，但缺真实 QMT/XT 分钟线来源联调。
- Paper/Simulation：bridge、feedback、live gate 已实现，但还缺连续运行多日的稳定性落档。

## Blocked

- QMT/XT、XTP、TORA 等真实股票 Gateway 尚未接入账号环境。
- 真实新闻、公告、社媒情绪 API 暂缓，当前仅支持本地/manual 来源和降级。
- P20 中 BaoStock/efinance 仅完成调研；是否接入取决于后续公开数据源质量和合规判断。

## 生产前必须补齐

1. 用真实 provider 或可审计本地 provider 跑 P19-T04，落 provider trace、数据版本和质量报告。
2. 用真实 PostgreSQL 快照跑 TradingAgents 批量研究，验证报告、评级、交易意图和审计入库。
3. 连续运行 paper/simulation，导出 `decision_audit`、feedback、heartbeat、replay status。
4. 开通并联调股票 Gateway 后，先验证行情订阅和手工交易，再验证策略读取 AI 信号。
5. 小资金前必须通过 LiveGate：稳定天数、回撤、审计完整率、失败率、手工接管全部 ready。
