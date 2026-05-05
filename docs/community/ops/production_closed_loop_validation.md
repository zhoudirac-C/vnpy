# 生产闭环验证流程

本文档定义本 fork 从“代码可运行”进入“生产候选”的闭环验证流程。新闻、社媒和实时资讯 provider 暂不纳入本轮验证范围；缺失时必须 degraded，不能阻塞 vn.py 主交易链路。

## 1. 验证目标

生产闭环验证要回答三个问题：

1. 当前代码是否可以重复通过核心单测、lint、编译和 Alpha 可选依赖 smoke。
2. PostgreSQL、TradingAgents Worker、API key、provider 配置等生产外部依赖是否明确就绪。
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

## 6. 当前结论

截至 `2026-05-05` 的本地验证结果见：

- `docs/community/ops/validation_results/2026-05-05-production-closed-loop-local.md`
- `docs/community/ops/validation_results/2026-05-05-production-closed-loop-local.json`

当前结论：代码级闭环、Alpha 可选依赖边界和 smoke 验证通过；P18 后代码侧已提供默认 context-only TradingAgents factory 和 UI 安全 key 输入。生产准入仍被 vn.py PostgreSQL 全局配置、独立 Worker 环境中的上游 TradingAgents 安装、真实 LLM API key、真实 provider/readiness 阻塞。因此当前项目不是生产可用状态，只能作为生产候选代码继续联调。

## 7. 下一步

1. 在 vn.py 全局配置中设置 `database.name=postgresql` 和对应 `database.*` 字段，执行 schema init/status。
2. 独立 Worker 环境安装上游 TradingAgents，并配置 `TRADINGAGENTS_WORKER_FACTORY=vnpy_tradingagents.tradingagents_factory:build`。
3. 在 vn.py UI 安全输入框或系统 Secret 中配置 LLM API key，并确认 secret policy 不会把 key 写入 context、日志或 DB payload。
4. 配置至少一个真实 provider 或可审计本地 provider，跑 readiness 到非 failed。
5. 用 production profile 重新生成验证结果，结果落档后再进入 paper/simulation 连续运行。
