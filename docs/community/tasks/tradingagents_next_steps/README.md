# TradingAgents 后续任务索引

本文档夹跟踪 `custom_quant_architecture.md` 和 `vnpy_reuse_extension_route.md` 中尚未真正落地的功能。每次完成任务时，必须把对应任务从 `- [ ]` 改为 `- [x]`，并在对应阶段文档的完成记录中补充日期、提交号和验证命令。

## 状态规则

| 标记 | 含义 |
| --- | --- |
| `- [ ]` | 未开始或未完成 |
| `- [x]` | 当前阶段代码或文档已实现、已测试、已提交；不自动代表生产可用 |
| `Blocked` | 需要账号、数据源、外部权限或产品决策 |
| `Deferred` | 明确推迟，不影响当前阶段验收 |

P1-P11 是第一轮骨架阶段，已完成项代表接口、边界、单测或 smoke 能力完成。P12-P15 是按 vn.py 优先复用路线进行的生产化纠偏阶段，完成后才允许把对应能力描述为生产候选。

完成任务时需要同步更新：

1. 勾选对应任务。
2. 在阶段文档的“完成记录”写入提交号。
3. 若任务改变架构或阶段状态，同步更新 `docs/community/info/custom_quant_architecture.md`。
4. 运行对应测试；涉及 PlantUML 文档时运行 `tools.plantuml.check_plantuml`。

## 已完成骨架基线

- [x] `vnpy_router.Datafeed` 骨架、本地文件 provider、AKShare 日线 provider。
- [x] PostgreSQL bar snapshot 写入接口。
- [x] TradingAgents runtime 开关、App metadata、Engine metadata。
- [x] `MarketDataToolkit` 的只读快照边界。
- [x] Worker request/response、报告/评级/交易意图入库。
- [x] `IntradaySnapshotBuilder`、`IntradayAgentJob`。
- [x] `ResearchSnapshotBuilder`、`LongHorizonAgentJob`。
- [x] `PostgresSignalReader`。
- [x] `SignalFusionService`、`AiSignalPolicy`。
- [x] `RiskRuleSet`、`PreOrderDecisionService`、`DecisionAuditRecord`。
- [x] `IntradayReplayEngine`、`PortfolioReplayEngine`。
- [x] `ReplayRunStatusBuilder`、`ReplayRunStatusLog`。
- [x] `GatewayAiPolicy`。
- [x] 事件/新闻/公告/情绪快照管线与降级策略。
- [x] 股票池批量长期任务、长期调度器、组合约束和绩效反馈。
- [x] 回测桥接、PaperAccount 仿真桥接、灰度状态持久化、审计导出、schema 初始化和 live gate。
- [x] 生产级 PostgreSQL migration runner、schema CLI 和 readiness checker。
- [x] 真实 TradingAgents runner 边界、结构化输出校验、checkpoint 隔离和 runner smoke。
- [x] 生产 provider 能力矩阵、TuShare/QMT/XT 边界和社媒事件源生产规则。
- [x] vn.py 回测适配、PaperAccount 反馈、UI 手工接管和 paper smoke。
- [x] 运维 heartbeat、metrics、密钥治理、备份恢复和小资金上线 runbook。

## 生产化缺口

- [x] 真实 PostgreSQL 连接需要统一使用 dict row，并用真实 PostgreSQL 验证 schema、migration 和 snapshot 读写。
- [x] QMT/XT 不再直接实现 provider，需优先复用 vn.py datafeed/gateway 插件。
- [x] TradingAgents 需要真实 context-only runner，不能裸调默认美股数据工具。
- [x] 新闻、公告、社媒、情绪需要完整 normalized storage、reader 和 Toolkit 窗口上下文。
- [x] TradingAgentsApp 需要真正接入 vn.py EventEngine、worker lifecycle、状态持久化和 UI 控制。
- [x] 回测、Paper 和仿真需要接入 vn.py 真实链路，现有 bridge 只按 smoke 或过渡层处理。
- [x] 生产路径中的 direct provider、placeholder、fake runner、paper-only bridge 等多余代码需要删除或标记为 smoke-only。

## 阶段文档

| 阶段 | 文档 | 目标 |
| --- | --- | --- |
| P1 | [01-data-snapshot-foundation.md](01-data-snapshot-foundation.md) | 补齐 PostgreSQL 快照读取、数据源配置、缓存和质量追踪 |
| P2 | [02-tradingagents-worker.md](02-tradingagents-worker.md) | 接入真实 TradingAgents Worker、LLM 配置、prompt 和进程边界 |
| P3 | [03-vnpy-runtime-integration.md](03-vnpy-runtime-integration.md) | 接入 EventEngine、策略层、TradingAgents UI 和受控下单前边界 |
| P4 | [04-event-news-sentiment.md](04-event-news-sentiment.md) | 补新闻、公告、事件和情绪快照管线 |
| P5 | [05-batch-portfolio-feedback.md](05-batch-portfolio-feedback.md) | 补长期批量调度、组合约束和绩效反馈 |
| P6 | [06-backtest-simulation-gray-release.md](06-backtest-simulation-gray-release.md) | 接入真实回测、仿真、灰度审计导出和部署迁移 |
| P7 | [07-production-postgres-readiness.md](07-production-postgres-readiness.md) | 补生产级 PostgreSQL 迁移、CLI 初始化和健康检查 |
| P8 | [08-real-tradingagents-runner.md](08-real-tradingagents-runner.md) | 接入真实 TradingAgents runner 和输出校验 |
| P9 | [09-production-data-sources.md](09-production-data-sources.md) | 补生产数据源骨架和新闻社媒来源规则 |
| P10 | [10-vnpy-paper-backtest-integration.md](10-vnpy-paper-backtest-integration.md) | 把桥接层挂到真实 vn.py 回测、PaperAccount 和 UI |
| P11 | [11-operations-live-readiness.md](11-operations-live-readiness.md) | 补运维观测、备份、密钥治理和小资金上线 Runbook |
| P12 | [12-vnpy-reuse-correction.md](12-vnpy-reuse-correction.md) | 按 vn.py 复用路线纠偏，修 PostgreSQL 连接，清理多余旁路代码 |
| P13 | [13-tradingagents-context-worker.md](13-tradingagents-context-worker.md) | 接入真实 context-only TradingAgents Worker，禁止默认外部数据工具 |
| P14 | [14-event-toolkit-production.md](14-event-toolkit-production.md) | 补事件管线、情绪快照和 MarketDataToolkit 生产上下文 |
| P15 | [15-vnpy-runtime-production.md](15-vnpy-runtime-production.md) | 接入 vn.py 真实运行链路、回测/Paper、状态持久化和完整 readiness |

## 下一步推荐

1. 先完成 P12：修真实 PostgreSQL dict row、移除 QMT/XT direct provider 路线、把多余占位代码清理或标记为 smoke-only。
2. 再完成 P13：TradingAgents 只能走 context-only runner，不能让默认外部数据工具进入生产路径。
3. 然后完成 P14：把新闻、公告、社媒、情绪和数据质量真正接到 `MarketDataToolkit`。
4. 最后完成 P15：接 vn.py 真实 EventEngine、Backtesting、Paper、UI 状态持久化和完整 readiness，再考虑小资金演练。
