# TradingAgents 后续任务索引

本文档夹跟踪 `custom_quant_architecture.md` 中尚未真正落地的功能。每次完成任务时，必须把对应任务从 `- [ ]` 改为 `- [x]`，并在对应阶段文档的完成记录中补充日期、提交号和验证命令。

## 状态规则

| 标记 | 含义 |
| --- | --- |
| `- [ ]` | 未开始或未完成 |
| `- [x]` | 已实现、已测试、已提交 |
| `Blocked` | 需要账号、数据源、外部权限或产品决策 |
| `Deferred` | 明确推迟，不影响当前阶段验收 |

完成任务时需要同步更新：

1. 勾选对应任务。
2. 在阶段文档的“完成记录”写入提交号。
3. 若任务改变架构或阶段状态，同步更新 `docs/community/info/custom_quant_architecture.md`。
4. 运行对应测试；涉及 PlantUML 文档时运行 `tools.plantuml.check_plantuml`。

## 已完成基线

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

## 阶段文档

| 阶段 | 文档 | 目标 |
| --- | --- | --- |
| P1 | [01-data-snapshot-foundation.md](01-data-snapshot-foundation.md) | 补齐 PostgreSQL 快照读取、数据源配置、缓存和质量追踪 |
| P2 | [02-tradingagents-worker.md](02-tradingagents-worker.md) | 接入真实 TradingAgents Worker、LLM 配置、prompt 和进程边界 |
| P3 | [03-vnpy-runtime-integration.md](03-vnpy-runtime-integration.md) | 接入 EventEngine、策略层、TradingAgents UI 和受控下单前边界 |
| P4 | [04-event-news-sentiment.md](04-event-news-sentiment.md) | 补新闻、公告、事件和情绪快照管线 |
| P5 | [05-batch-portfolio-feedback.md](05-batch-portfolio-feedback.md) | 补长期批量调度、组合约束和绩效反馈 |
| P6 | [06-backtest-simulation-gray-release.md](06-backtest-simulation-gray-release.md) | 接入真实回测、仿真、灰度审计导出和部署迁移 |

## 下一步推荐

1. 用真实 PostgreSQL 实例跑 `initialize_postgres_schema()`，确认 schema 初始化和重复执行幂等。
2. 配置 `vnpy_router` 的 provider 顺序，先用本地文件/AKShare 验证数据快照，再接 TuShare/QMT/XT。
3. 把真实 TradingAgents runner 接到 `TradingAgentsWorkerAdapter`，继续保持 context-only 边界。
4. 进入 PaperAccount/回测联调，观察 `replay_run_status`、`decision_audit` 和 feedback 表。
