# P2 真实 TradingAgents Worker 任务

目标：把当前 Worker 协议和存储边界接到真实 TauricResearch TradingAgents / LangGraph 运行链路，同时保持它不能直接调用 vn.py 交易接口。

## 任务清单

- [x] **P2-T01: 增加 Worker 配置模型**
  - 创建：`vnpy_tradingagents/config.py`
  - 测试：`tests/test_tradingagents_worker_config.py`
  - 字段：LLM provider、API key 环境变量名、model、timeout、max retry、checkpoint 目录。
  - 验收：未配置 API key 时返回清晰错误，不启动真实 Worker。

- [ ] **P2-T02: 实现真实 TradingAgents Worker adapter**
  - 创建：`vnpy_tradingagents/worker_adapter.py`
  - 复用：`TradingAgentsWorkerRequest`、`TradingAgentsWorkerResponse`
  - 要求：只接收 `request.context`，不允许访问 yfinance、Alpha Vantage、AKShare、TuShare、QMT，不暴露 `MainEngine`、Gateway、send_order。
  - 验收：单股票单日期能返回结构化报告、评级和动作；超时返回可审计失败结果。

- [ ] **P2-T03: Prompt 模板注入 A 股规则**
  - 创建：`vnpy_tradingagents/prompts.py`
  - 内容：A 股交易时间、T+1、涨跌停、停牌、仓位上限和不得绕过风控。
  - 验收：prompt 中不出现美股 benchmark 默认假设。

- [ ] **P2-T04: Worker 进程边界**
  - 创建：`vnpy_tradingagents/worker_process.py`
  - 目标：支持 CLI 或子进程运行，支持 JSON 输入输出，支持超时、重试和失败状态。
  - 验收：主进程失败时 runtime 状态变为 degraded；失败不影响策略和风控继续运行。

- [ ] **P2-T05: Worker raw state 和模型信息落库**
  - 修改：`vnpy_tradingagents/storage.py`
  - 补充字段：`model_provider`、`model_name`、`prompt_version`、`snapshot_ids`、`error_message`
  - 验收：同一输入快照可复跑并对比输出差异。

- [ ] **P2-T06: SnapshotSourcePolicy**
  - 创建：`vnpy_tradingagents/source_policy.py`
  - 目标：定义 market/fundamentals/news/sentiment/benchmark/portfolio 是否必填，以及缺失时是否允许 degraded。
  - 验收：news/sentiment 缺失时可降级；market 缺失时阻止 Worker 运行。

## 完成记录

| 任务 | 日期 | 提交 | 验证 |
| --- | --- | --- | --- |
| P2-T01 | 2026-05-03 | `4fbf94d7` | `uv run --with pytest pytest tests/test_tradingagents_worker_config.py tests/test_tradingagents_toolkit.py tests/test_tradingagents_storage_service.py tests/test_tradingagents_intraday.py tests/test_tradingagents_research.py -v` |
