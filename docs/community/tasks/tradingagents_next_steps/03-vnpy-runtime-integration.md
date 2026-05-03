# P3 vn.py 运行态接入任务

目标：把当前可测试边界接入 vn.py 的 EventEngine、策略层和自定义 App UI，但保持 AI 不直接调用 Gateway。

## 任务清单

- [ ] **P3-T01: TradingAgentsWidget 前端开关**
  - 创建：`vnpy_tradingagents/ui/widget.py`
  - 修改：`vnpy_tradingagents/app.py`
  - UI 控件：全局启用/禁用、report_only / paper_only / live_allowed 模式、live AI 二次确认、runtime 状态展示。
  - 验收：前端关闭后策略读取 AI 状态为 disabled；live_allowed 必须显式确认。

- [ ] **P3-T02: EventEngine 定时触发日内 Job**
  - 创建：`vnpy_tradingagents/scheduler.py`
  - 接入：`EVENT_TIMER`、5/15 分钟节流、可选事件触发。
  - 验收：不逐 tick 调用 LLM；Worker 超时不阻塞事件线程。

- [ ] **P3-T03: Gateway 行情到 IntradaySnapshot**
  - 创建：`vnpy_tradingagents/intraday_collector.py`
  - 输入：tick 或分钟 bar、当前持仓、当日交易纪律。
  - 输出：`IntradaySnapshot`
  - 验收：真实事件生成快照；快照可写 PostgreSQL 并被回放复用。

- [ ] **P3-T04: 策略层 AI 信号读取 mixin**
  - 创建：`vnpy_tradingagents/strategy_mixin.py`
  - 目标：提供 `load_ai_intraday_advice()`、`load_ai_rating_signal()`、`fuse_ai_signal()`。
  - 验收：CTA/PortfolioStrategy 可用同一接口读取 AI 信号；关闭 AI 后只返回规则信号。

- [ ] **P3-T05: `OrderIntent -> OrderRequest` 受控转换**
  - 创建：`vnpy_tradingagents/order_bridge.py`
  - 目标：只有 `PreOrderDecisionResult.submit_allowed=True` 时才生成 `OrderRequest`；生成前必须保存 `DecisionAuditRecord`。
  - 验收：风控拒绝时不生成 `OrderRequest`；审计里能找到 source_run_id。

- [ ] **P3-T06: TradingAgents 状态面板**
  - 修改：`vnpy_tradingagents/ui/widget.py`
  - 展示：最新 AI 建议、策略是否采纳、风控拒绝原因、最新 replay/gray run status。
  - 验收：UI 展示来自 `ReplayRunStatus` 或 PostgreSQL 审计，不直接读 Worker 内部状态。

## 完成记录

| 任务 | 日期 | 提交 | 验证 |
| --- | --- | --- | --- |

