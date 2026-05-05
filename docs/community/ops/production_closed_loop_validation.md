# 生产闭环验证流程

本文档定义本 fork 从“代码可运行”进入“生产候选”的闭环验证流程。新闻、社媒和实时资讯 provider 暂不纳入本轮验证范围；缺失时必须 degraded，不能阻塞 vn.py 主交易链路。

## 1. 验证目标

生产闭环验证要回答三个问题：

1. 当前代码是否可以重复通过核心单测、lint、编译和 Alpha 可选依赖 smoke。
2. PostgreSQL、同进程 context-only TradingAgents Worker、API key、provider 配置等生产外部依赖是否明确就绪。
3. 如果外部依赖缺失，系统是否能给出明确阻塞项，而不是误报生产可用。

只有 `production_ready=true` 且所有生产必需检查均为 `passed`，才能进入真实 PostgreSQL 联调、模拟盘连续运行和小资金灰度。

## 2. 验证入口

本地闭环验证：

```bash
uv run python -m tools.production.closed_loop_validation \
  --profile local \
  --repo-root . \
  --output docs/community/ops/validation_results/$(date +%F)-production-closed-loop-local.md \
  --json-output docs/community/ops/validation_results/$(date +%F)-production-closed-loop-local.json
```

生产环境闭环验证：

```bash
uv run python -m tools.production.closed_loop_validation \
  --profile production \
  --repo-root . \
  --output docs/community/ops/validation_results/$(date +%F)-production-closed-loop-production.md \
  --json-output docs/community/ops/validation_results/$(date +%F)-production-closed-loop-production.json
```

## 3. 本地自动化检查

| 检查项 | 目的 | 生产准入含义 |
| --- | --- | --- |
| `ruff_core` | 检查核心包和新增验证脚本静态问题 | 代码风格和明显错误不过关时不能上线 |
| `pytest_non_alpha` | 跑非 Alpha101 全量测试 | 验证 TradingAgents、router、event、runtime、paper smoke 等主链路 |
| `alpha_optional_imports` | 验证 `vnpy.alpha` 可选依赖边界 | 未启用 alpha 时不能拖垮主系统 |
| `alpha101_smoke` | 验证 `polars[rtcompat] + scipy` 下 Alpha101 最小计算 | 因子研究入口不再受 Mac CPU runtime 问题阻塞 |
| `compileall_core` | 编译核心 Python 模块 | 防止语法级错误进入生产包 |
| `diff_check` | 检查 whitespace/error marker | 防止不可见格式问题混入提交 |

## 4. 生产门禁

| 门禁 | 必需条件 | 未满足时状态 |
| --- | --- | --- |
| `readiness_cli` | `vnpy-tradingagents-schema readiness --json` 返回非 failed | `blocked` 或 `failed` |
| `tradingagents_worker_factory_env` | `TRADINGAGENTS_WORKER_FACTORY=vnpy_tradingagents.tradingagents_factory:build` 或等价 context-only runner | `blocked` |
| `llm_api_key_env` | `OPENAI_API_KEY`、UI 安全输入框写入的运行时环境变量，或 readiness 配置中的等价变量存在 | `blocked` |

这些门禁是生产必需项。本地 profile 下，外部依赖缺失会记录为 `blocked`，命令退出码仍允许为 0，方便在开发环境生成验证报告。production profile 下，任一生产必需门禁不是 `passed`，整体 `production_ready=false` 且命令退出码非 0。

生产闭环脚本会忽略自身生成的 `docs/community/ops/validation_results/` 证据文件，避免“刚生成验证报告就导致工作区不干净”的自阻塞；其它源码、配置和文档改动仍必须提交后才能通过 `worktree_clean` 门禁。

## 5. 结果落档

每次验证必须落两份文件：

- Markdown：给人审阅，记录命令、状态和结论。
- JSON：给后续脚本、CI、监控或审计系统读取。

推荐路径：

```text
docs/community/ops/validation_results/YYYY-MM-DD-production-closed-loop-<profile>.md
docs/community/ops/validation_results/YYYY-MM-DD-production-closed-loop-<profile>.json
```

结果解读：

| 状态 | 含义 |
| --- | --- |
| `passed` | 该检查通过 |
| `blocked` | 代码可验证，但缺少生产外部依赖或配置 |
| `failed` | 命令或生产检查失败，需要修复 |

## 6. TradingAgents 生产配置含义

“真实 TradingAgents 上游依赖和成本/超时/审计配置”不是要独立部署 worker 服务，而是指同进程 context-only Worker 在生产运行前必须明确这些运行参数：

| 类别 | 大白话解释 | 需要落地的配置 |
| --- | --- | --- |
| 上游依赖 | 当前环境里真的装了 TradingAgents 及其运行所需库，而不是只用 fallback stub | TradingAgents、LangGraph、LLM provider SDK、pandas/stockstats 等可选运行依赖 |
| 成本 | 每次让大模型分析都会花 token 或调用额度，需要限预算 | `tradingagents.llm_provider`、`tradingagents.model`、单次/单日最大 token、最大分析标的数、手工开关 |
| 超时 | 不能让 LLM 卡住 vn.py 主进程或策略线程 | `tradingagents.timeout_seconds`、`tradingagents.max_retries`、并发上限、失败降级为 `hold/watch` |
| 审计 | 以后要能回答“这笔建议为什么产生、用了哪些数据、有没有影响订单” | `AgentRun`、`RatingSignal`、`TradeIntent`、`DecisionAudit`、snapshot id、prompt version、model、耗时、错误类型和订单 `reference` |

生产准入要求是：这些配置存在、能被 readiness/closed-loop 验证读取，并且失败时不影响 vn.py 主交易链路。

## 7. 当前结论

截至 `2026-05-05` 的本地验证结果见：

- `docs/community/ops/validation_results/2026-05-05-production-closed-loop-local.md`
- `docs/community/ops/validation_results/2026-05-05-production-closed-loop-local.json`

当前结论：代码级闭环、Alpha 可选依赖边界和 smoke 验证通过；P18 后代码侧已提供默认同进程 context-only TradingAgents factory 和 UI 安全 key 输入。生产准入仍需要 vn.py PostgreSQL 全局配置、上游 TradingAgents 依赖、真实 LLM API key、真实 provider/readiness 全部通过。因此当前项目不是生产可用状态，只能作为生产候选代码继续联调。

## 8. 下一步

1. 在 vn.py 全局配置中设置 `database.name=postgresql` 和对应 `database.*` 字段，执行 schema init/status。
2. 在当前 vn.py 运行环境安装上游 TradingAgents 依赖，并保留默认 `tradingagents.worker_factory=vnpy_tradingagents.tradingagents_factory:build`。
3. 在 vn.py UI 安全输入框或系统 Secret 中配置 LLM API key，并确认 secret policy 不会把 key 写入 context、日志或 DB payload。
4. 配置至少一个真实 provider 或可审计本地 provider，跑 readiness 到非 failed。
5. 用 production profile 重新生成验证结果，结果落档后再进入 paper/simulation 连续运行。
