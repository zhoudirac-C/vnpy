# 小资金实盘灰度 Runbook

本文档定义 TradingAgents 信号从 paper/simulation 进入小资金实盘前的检查、开关、回滚、手工接管和复盘流程。TradingAgents 只能影响信号和交易意图，不能绕过 Strategy、Risk、MainEngine 和 Gateway。

## 上线前检查

0. 运行生产闭环验证，结果必须落档：

```bash
uv run python -m tools.production.closed_loop_validation \
  --profile production \
  --repo-root . \
  --output docs/community/ops/validation_results/$(date +%F)-production-closed-loop-production.md \
  --json-output docs/community/ops/validation_results/$(date +%F)-production-closed-loop-production.json
```

`production_ready` 必须为 `true`，否则不能进入小资金实盘灰度。

1. 初始化扩展表：

```bash
vnpy-tradingagents-schema schema init
```

2. 运行 readiness：

```bash
vnpy-tradingagents-schema readiness --json
```

readiness 必须覆盖并通过以下关键项：

- vn.py `database.*` PostgreSQL 配置、Peewee 扩展表存在状态。
- `datafeed.name=router` 和 provider 配置。
- TradingAgents context-only worker factory，推荐 `TRADINGAGENTS_WORKER_FACTORY=vnpy_tradingagents.tradingagents_factory:build`，不能使用裸 `propagate(symbol, date)`。
- LLM API key 通过 vn.py UI 安全输入框、系统环境变量或 Secret Manager 注入，不能保存到 `vt_setting.json`。
- API key/token/password 不进入 context、日志或 DB payload。
- event/news/sentiment snapshot 缺失时必须 degraded，不得阻塞手工交易。

3. 检查最近状态：

```sql
select * from ops_heartbeat order by updated_at desc limit 20;
select payload from replay_run_status order by generated_at desc limit 5;
select count(*) from decision_audit where created_at::date = current_date;
```

4. 确认 LiveGate 指标：

- simulation stable days 达到配置下限。
- max drawdown 小于配置上限。
- audit completeness 达到配置下限。
- TradingAgents 前端开关已启用，live 二次确认已勾选。

## 开关顺序

1. `tradingagents.enabled=true`。
2. `tradingagents.mode=paper_only`。
3. 运行至少一轮 paper smoke。
4. 检查 `decision_audit`、`agent_trade_feedback`、`replay_run_status`。
5. 通过 LiveGate 后，手工切到 `live_allowed`。
6. 限制小资金账户、单票上限、单笔金额、行业集中度和日内成交额。

## 禁止条件

以下任一条件出现时，不允许进入 `live_allowed`：

- `LiveGate.evaluate()` 返回非 ready。
- `ops_heartbeat.status` 为 failed 或 degraded 且未处理。
- 最新 `replay_run_status.health` 为 blocked。
- `decision_audit` 缺失或审计完整率不足。
- Worker context、日志或 raw state 中出现 API key/token/password。
- 数据源 fallback 失败，market snapshot 缺失。

## 手工接管

一键暂停流程：

1. 点击 TradingAgents UI 的“手工接管”按钮。
2. 系统调用 `pause_manual_takeover()`。
3. paper/live `can_use_signal()` 都必须变为 false。
4. 策略停止读取 `RatingSignal`、`TradeIntent`、`IntradayAdvice`。
5. 保留手工撤单、手工风控、持仓查询和账户查询。

## 回滚

```sql
update replay_run_status
set health = 'manual_paused'
where run_id = '<latest-run-id>';
```

运行侧：

- 将前端模式切回 `paper_only` 或关闭 TradingAgents。
- 停止 worker/scheduler。
- 导出最近一轮 `decision_audit` 和 `agent_report`。
- 用人工策略或原规则策略继续管理仓位。

## 盘后复盘

必须复盘：

- 每一笔 AI 影响过的 `decision_audit`。
- 风控拒绝原因和是否符合预期。
- `agent_trade_feedback` 的滑点、成交价、PnL。
- 数据源延迟、缺失、降级来源。
- Worker 超时、LLM 错误、输出降级。

复盘结果写入 feedback，作为下一轮 TradingAgents 反思输入。
