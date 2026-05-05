# P18 context-only Worker 和 UI Key 配置任务

目标：把 `TRADINGAGENTS_WORKER_FACTORY` 从“用户必须自备 factory”推进到仓库内置默认 factory，并允许用户在 vn.py UI 中填写真实 LLM API key，但不把明文 key 保存到 `vt_setting.json`。

## 任务清单

- [x] **P18-T01: 默认 context-only TradingAgents factory**
  - 创建：`vnpy_tradingagents/tradingagents_factory.py`
  - 目标：提供 `vnpy_tradingagents.tradingagents_factory:build`，返回 `AShareContextOnlyRunner`。
  - 验收：`TRADINGAGENTS_WORKER_FACTORY=vnpy_tradingagents.tradingagents_factory:build` 可被 `worker_process.load_configured_worker()` 加载。

- [x] **P18-T02: 上游 TradingAgents 工具替换为 context 工具**
  - 创建：`TradingAgentsContextOnlyGraphRunner`
  - 目标：market/news/social/fundamental 工具只读取 `native_input["context"]`，不走 yfinance、Alpha Vantage、AKShare、TuShare、QMT、Gateway 或 MainEngine。
  - 验收：无 active context 时工具 fail closed；有 context 时 fake graph 只能读取上下文快照。

- [x] **P18-T03: LLM API key 安全存储抽象**
  - 创建：`vnpy_tradingagents/llm_secret.py`
  - 修改：`vnpy_tradingagents/config.py`
  - 目标：API key 优先从进程环境变量读取；UI 可写入当前进程环境变量；安装可选 `keyring` 时可写入系统钥匙串。
  - 验收：保存结果不返回明文 key；`TradingAgentsWorkerConfig.resolve_api_key()` 可从 keyring store 读取。

- [x] **P18-T04: vn.py 全局配置界面真实 key 输入**
  - 修改：`vnpy/trader/ui/widget.py`
  - 目标：在 `tradingagents.api_key_env_var` 下方增加 `tradingagents.api_key <secret>` 密码输入框和 keyring 选项；在全局配置中展示 `tradingagents.worker_factory` 默认值和说明。
  - 验收：`tradingagents.api_key` 是伪字段，不进入 `vt_setting.json` 保存内容；`tradingagents.worker_factory` 默认等于 `vnpy_tradingagents.tradingagents_factory:build`。

- [x] **P18-T05: 文档更新**
  - 修改：`docs/community/info/tradingagents_llm_env.md`
  - 修改：`docs/community/info/custom_quant_architecture.md`
  - 目标：说明默认 factory、UI key 配置方式、keyring 可选依赖和生产 Secret 注入建议。

## 完成记录

| 任务 | 日期 | 提交 | 验证 |
| --- | --- | --- | --- |
| P18-T01 | 2026-05-05 | 未提交 | `uv run --with pytest pytest tests/test_tradingagents_worker_process.py::test_worker_process_loads_default_context_only_factory -q` |
| P18-T02 | 2026-05-05 | 未提交 | `uv run --with pytest pytest tests/test_tradingagents_context_factory.py -q` |
| P18-T03 | 2026-05-05 | 未提交 | `uv run --with pytest pytest tests/test_tradingagents_llm_secret_ui.py -q` |
| P18-T04 | 2026-05-05 | 未提交 | `uv run --with pytest pytest tests/test_tradingagents_llm_secret_ui.py::test_global_setting_coercion_excludes_plaintext_llm_api_key -q` |
| P18-T05 | 2026-05-05 | 未提交 | 文档检查；`uv run --with ruff ruff check vnpy_tradingagents/llm_secret.py vnpy_tradingagents/tradingagents_factory.py vnpy_tradingagents/config.py vnpy/trader/ui/widget.py tests/test_tradingagents_context_factory.py tests/test_tradingagents_llm_secret_ui.py tests/test_tradingagents_worker_process.py` |
