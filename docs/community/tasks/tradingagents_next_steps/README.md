# TradingAgents 后续任务索引

本文档夹跟踪 `custom_quant_architecture.md` 和 `vnpy_reuse_extension_route.md` 中尚未真正落地的功能。每次完成任务时，必须把对应任务从 `- [ ]` 改为 `- [x]`，并在对应阶段文档的完成记录中补充日期、提交号和验证命令。

## 状态规则

| 标记 | 含义 |
| --- | --- |
| `- [ ]` | 未开始或未完成 |
| `- [x]` | 当前阶段代码或文档已实现、已测试、已提交；不自动代表生产可用 |
| `Blocked` | 需要账号、数据源、外部权限或产品决策 |
| `Deferred` | 明确推迟，不影响当前阶段验收 |

P1-P11 是第一轮骨架阶段，已完成项代表接口、边界、单测或 smoke 能力完成。P12-P15 是按 vn.py 优先复用路线进行的生产化纠偏阶段，完成后才允许把对应能力描述为生产候选。P16 开始进入生产闭环验证，必须用落档结果区分“代码级闭环通过”和“真实生产环境已就绪”。P17 专门清理本 fork 中绕开 vn.py 原生配置体系的重复 PostgreSQL 配置入口，并把扩展表初始化纠正为复用 `vnpy_postgresql` 的 Peewee Model + `create_tables()` 模式。

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
- [x] 早期 PostgreSQL schema CLI 和 readiness checker 骨架；P17 将把自建 migration runner 纠正为 Peewee Model + `create_tables()`。
- [x] 真实 TradingAgents runner 边界、结构化输出校验、checkpoint 隔离和 runner smoke。
- [x] 生产 provider 能力矩阵、TuShare/QMT/XT 边界和社媒事件源生产规则。
- [x] vn.py 回测适配、PaperAccount 反馈、UI 手工接管和 paper smoke。
- [x] 运维 heartbeat、metrics、密钥治理、备份恢复和小资金上线 runbook。

## 生产化缺口

- [x] PostgreSQL 扩展表初始化需要复用 vn.py `database.*` 和 Peewee `create_tables()`，删除独立 DSN 和自建 migration runner 生产路径。
- [x] QMT/XT 不再直接实现 provider，需优先复用 vn.py datafeed/gateway 插件。
- [x] TradingAgents 需要真实 context-only runner，不能裸调默认美股数据工具。
- [x] 新闻、公告、社媒、情绪需要完整 normalized storage、reader 和 Toolkit 窗口上下文。
- [x] TradingAgentsApp 需要真正接入 vn.py EventEngine、worker lifecycle、状态持久化和 UI 控制。
- [x] 回测、Paper 和仿真需要接入 vn.py 真实链路，现有 bridge 只按 smoke 或过渡层处理。
- [x] 生产路径中的 direct provider、placeholder、fake runner、paper-only bridge 等多余代码需要删除或标记为 smoke-only。
- [x] 新闻增强第二版代码级链路已补官方公告主源、GDELT 宏观补充、股票实体识别、多标的 `event_symbol_link`、分类评分去重和 TradingAgents 高可信上下文过滤。
- [ ] P25 真实公网 smoke、连续运行和实体识别误链率抽样仍未完成，不能宣称新闻源生产 SLA。
- [x] TradingAgents 定位需要从“混入传统策略”调整为“手动分析页 + 独立 AI 策略 + 独立 AI 回测策略”；传统规则策略默认不消费 AI 信号。
- [ ] 完整财报信息还没有入库任务；`MarketDataToolkit` 已有 `fundamentals/valuation` 读取入口，但缺三大报表、财务指标、官方披露 PDF 元数据和点时防穿越校验。

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
| P16 | [16-production-closed-loop-validation.md](16-production-closed-loop-validation.md) | 生成生产闭环验证脚本、流程文档和当前验证结果落档 |
| P17 | [17-vnpy-native-config-cleanup.md](17-vnpy-native-config-cleanup.md) | 删除重复 PostgreSQL 配置入口，统一复用 vn.py `database.*` 和 Peewee `create_tables()`，补 LLM 环境变量说明 |
| P18 | [18-context-worker-ui-key.md](18-context-worker-ui-key.md) | 内置 context-only TradingAgents factory，并在 UI 中支持真实 LLM key 安全输入 |
| P19 | [19-backtest-closed-loop-validation.md](19-backtest-closed-loop-validation.md) | 跑通 vn.py BacktestingEngine + AI 信号 + 风控审计的可重复回测闭环 |
| P20 | [20-real-data-source-hardening.md](20-real-data-source-hardening.md) | 强化真实数据源能力边界、fallback 和质量校验 |
| P21 | [21-stock-gateway-simulation-validation.md](21-stock-gateway-simulation-validation.md) | 验证股票 Gateway、仿真和 live gate 接入边界 |
| P22 | [22-ui-usability-fixes.md](22-ui-usability-fixes.md) | 修复配置、交易面板和回测入口的 UI 可用性问题 |
| P23 | [23-docs-dependency-consistency.md](23-docs-dependency-consistency.md) | 清理文档、依赖和阶段状态之间的不一致 |
| P24 | [24-news-ingestion-scheduler.md](24-news-ingestion-scheduler.md) | 补外部新闻入库 provider、定时任务、readiness 和验证落档 |
| P25 | [25-production-news-source-entity-filtering.md](25-production-news-source-entity-filtering.md) | 接入官方公告/GDELT/AKShare 第二版数据源，补实体识别、多标的关联、分类、评分、去重和 TradingAgents 高可信上下文过滤 |
| P26 | [26-llm-message-classifier.md](26-llm-message-classifier.md) | 增加可选 LLM 消息语义分类器，让行业/板块/宏观消息自由提名股票并经过本地实体目录校验后入库 |
| P27 | [27-tradingagents-strategy-positioning.md](27-tradingagents-strategy-positioning.md) | 收敛 TradingAgents 为手动分析、独立 AI 策略和 AI 回测链路；传统策略默认不接 AI |
| P28 | [28-financial-report-ingestion.md](28-financial-report-ingestion.md) | 接入完整财报入库：三大报表、财务指标、官方披露文档、质量评分和 TradingAgents 财务上下文 |

## 下一步推荐

1. P28 先补完整财报入库，否则 TradingAgents 的基本面分析只能看到行情和新闻，无法稳定读取三大报表和财务指标。
2. P27 已完成代码级定位纠偏；随后回到 P19，用本地 fixture 和 vn.py BacktestingEngine 跑通 AI 回测闭环，并把验证结果落档。
3. 再完成 P20/P21，把真实数据源、股票 Gateway、仿真和 live gate 分别验证清楚。
4. 若要补新闻增强，P24/P25/P26 已完成代码级链路和一次真实公网/GLM smoke；下一步是连续运行和实体误链率抽样。
5. 同步处理 P22/P23，避免 UI 使用问题和文档口径不一致继续干扰生产联调。
6. 连续运行稳定并完成审计导出后，才考虑小资金实盘灰度。
