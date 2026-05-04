# P15 vn.py 真实运行链路和上线前验收任务

目标：把 TradingAgents 扩展真正接到 vn.py App、EventEngine、策略、风控、回测、仿真和 readiness 中。关闭 TradingAgents 后，vn.py 的数据、策略、风控、下单、撤单、持仓查询和手工交易必须继续正常运行。

## 任务清单

- [x] **P15-T01: TradingAgentsApp 生命周期接入**
  - 修改：`vnpy_tradingagents/app.py`、`vnpy_tradingagents/engine.py`、`vnpy_tradingagents/ui/widget.py`
  - 目标：App 管理 worker client、scheduler、runtime state、手工接管和状态刷新，不在 EventEngine 线程直接跑 LLM。
  - 验收：GUI 可启停 TradingAgents，状态可见，关闭后不影响 vn.py 主程序。

- [x] **P15-T02: Runtime state 持久化**
  - 修改：`vnpy_tradingagents/storage.py`、`vnpy_tradingagents/runtime.py`
  - 目标：实现 PostgreSQL `ai_runtime_state`，保存 enabled、mode、live_enabled、manual_takeover、signal_status、disabled_reason。
  - 验收：重启后能恢复 AI 开关状态；一键暂停会标记未过期 AI 信号不可用。

- [x] **P15-T03: EventEngine 日内事件接入**
  - 修改：`vnpy_tradingagents/intraday_collector.py`、`vnpy_tradingagents/scheduler.py`
  - 目标：监听 vn.py tick/bar/timer 事件，构建日内快照并异步提交 Worker。
  - 验收：Worker 慢或失败不会阻塞行情事件线程。

- [x] **P15-T04: 策略和风控读取 AI 信号**
  - 修改：`vnpy_tradingagents/signal_reader.py`、`vnpy_tradingagents/signal_fusion.py`、`vnpy_tradingagents/order_bridge.py`
  - 目标：策略读取有效 AI 信号并与规则/ML 信号融合；风控仍是发单前硬边界。
  - 验收：AI 关闭、信号过期、信号 degraded 时策略自动退回非 AI 逻辑。

- [x] **P15-T05: vn.py Backtesting/Paper 真实接入**
  - 修改：`vnpy_tradingagents/backtesting_bridge.py`、`vnpy_tradingagents/backtesting_app_bridge.py`、`vnpy_tradingagents/paper_bridge.py`
  - 目标：现有 bridge 不再被描述为生产接入；真实回测优先走 vn.py Backtesting，模拟盘优先走仿真 Gateway 或 vn.py paper 体系。
  - 验收：paper smoke 仍可跑，但生产文档明确 smoke-only；真实回测能读取同一套 AI 信号。

- [x] **P15-T06: 完整 readiness 和上线前 runbook**
  - 修改：`vnpy_tradingagents/readiness.py`、`docs/community/ops/live_gray_runbook.md`
  - 目标：readiness 覆盖 DB/schema/datafeed/provider/worker/secret/event/toolkit/paper smoke/backtest smoke。
  - 验收：进入小资金前必须有一条命令输出完整检查报告；任一关键项 failed 时禁止 live AI mode。

- [x] **P15-T07: 清理生产路径中的 smoke-only 依赖**
  - 修改：所有引用 smoke helper 的生产模块和文档
  - 目标：`TradingAgentsPaperSmoke`、fake runner、local-only event provider 等仅在 tests、docs 或 smoke 命令中出现。
  - 验收：`rg "PaperSmoke|Fake|smoke-only|runner_not_configured"` 的结果不再出现在生产运行路径中。

## 完成记录

| 任务 | 日期 | 提交 | 验证 |
| --- | --- | --- | --- |
| P15-T01 | 2026-05-04 | 未提交 | `uv run --with pytest pytest tests/test_tradingagents_runtime.py tests/test_tradingagents_ui.py -q` |
| P15-T02 | 2026-05-04 | 未提交 | `uv run --with pytest pytest tests/test_tradingagents_runtime.py -q` |
| P15-T03 | 2026-05-04 | 未提交 | `uv run --with pytest pytest tests/test_tradingagents_intraday_collector.py tests/test_tradingagents_scheduler.py -q` |
| P15-T04 | 2026-05-04 | 未提交 | `uv run --with pytest pytest tests/test_tradingagents_strategy_mixin.py tests/test_tradingagents_order_bridge.py -q` |
| P15-T05 | 2026-05-04 | 未提交 | `uv run --with pytest pytest tests/test_vnpy_paper_ops_integration.py tests/test_tradingagents_replay.py -q` |
| P15-T06 | 2026-05-04 | 未提交 | `uv run --with pytest pytest tests/test_tradingagents_production_readiness.py tests/test_vnpy_paper_ops_integration.py -q` |
| P15-T07 | 2026-05-04 | 未提交 | `uv run --with ruff ruff check vnpy_tradingagents/paper_smoke.py vnpy_tradingagents/worker_process.py` |
