# 生产闭环验证结果

- 生成时间：`2026-05-05T11:30:37+08:00`
- profile：`local`
- branch：`feature/akshare-tradingagents-architecture`
- commit：`b2cc4cc7`
- worktree_clean：`false`
- production_ready：`false`
- 结果计数：`{"blocked": 3, "passed": 6}`

## 命令和门禁结果

| 检查项 | 状态 | 生产必需 | 命令/门禁 | 说明 |
| --- | --- | --- | --- | --- |
| ruff_core | passed | yes | `uv run --with ruff ruff check vnpy/alpha vnpy_router vnpy_tradingagents tests/test_alpha_optional_imports.py tests/test_data_router.py tests/test_tradingagents_toolkit.py` | command passed |
| pytest_non_alpha | passed | yes | `uv run --with pytest pytest tests -q --ignore=tests/test_alpha101.py` | command passed |
| alpha_optional_imports | passed | yes | `uv run --with polars[rtcompat] --with pytest pytest tests/test_alpha_optional_imports.py -q` | command passed |
| alpha101_smoke | passed | yes | `uv run --with polars[rtcompat] --with scipy --with pytest pytest tests/test_alpha101.py::TestAlpha101::test_alpha1 -q` | command passed |
| compileall_core | passed | yes | `uv run python -m compileall vnpy/alpha vnpy_router vnpy_tradingagents -q` | command passed |
| diff_check | passed | yes | `git diff --check` | command passed |
| readiness_cli | blocked | yes | `uv run vnpy-tradingagents-schema readiness --json` | command failed in local validation; treated as production gate not satisfied |
| tradingagents_worker_factory_env | blocked | yes | `env:TRADINGAGENTS_WORKER_FACTORY` | TRADINGAGENTS_WORKER_FACTORY is not configured in this validation environment |
| llm_api_key_env | blocked | yes | `env:OPENAI_API_KEY` | OPENAI_API_KEY is not configured in this validation environment |

## 工作区状态

本次验证运行时工作区存在未提交变更：

- ` M docs/community/info/custom_quant_architecture.md`
- ` M docs/community/info/database.md`
- ` M docs/community/info/index.rst`
- ` M docs/community/info/vnpy_reuse_extension_route.md`
- ` M docs/community/ops/live_gray_runbook.md`
- ` M docs/community/ops/postgres_backup_restore.md`
- ` M docs/community/tasks/tradingagents_next_steps/07-production-postgres-readiness.md`
- ` M docs/community/tasks/tradingagents_next_steps/12-vnpy-reuse-correction.md`
- ` M docs/community/tasks/tradingagents_next_steps/README.md`
- ` M pyproject.toml`
- ` M tests/test_production_data_sources.py`
- ` M tests/test_tradingagents_gray_release.py`
- ` M tests/test_tradingagents_production_readiness.py`
- ` M tests/test_tradingagents_worker_process.py`
- ` M tests/test_vnpy_paper_ops_integration.py`
- ` M vnpy/trader/setting.py`
- ` M vnpy/trader/ui/widget.py`
- ` M vnpy_router/datafeed.py`
- ` M vnpy_tradingagents/__init__.py`
- ` M vnpy_tradingagents/cli.py`
- ` M vnpy_tradingagents/config.py`
- ` D vnpy_tradingagents/migrations.py`
- ` M vnpy_tradingagents/readiness.py`
- ` M vnpy_tradingagents/schema_init.py`
- `?? docs/community/info/tradingagents_llm_env.md`
- `?? docs/community/ops/production_closed_loop_validation.md`
- `?? docs/community/ops/validation_results/`
- `?? docs/community/tasks/tradingagents_next_steps/16-production-closed-loop-validation.md`
- `?? docs/community/tasks/tradingagents_next_steps/17-vnpy-native-config-cleanup.md`
- `?? docs/community/tasks/tradingagents_next_steps/18-context-worker-ui-key.md`
- `?? tests/test_production_closed_loop_validation.py`
- `?? tests/test_tradingagents_context_factory.py`
- `?? tests/test_tradingagents_llm_secret_ui.py`
- `?? tests/test_vnpy_native_postgres_config.py`
- `?? tools/production/`
- `?? vnpy_router/extension_models.py`
- `?? vnpy_router/peewee.py`
- `?? vnpy_tradingagents/llm_secret.py`
- `?? vnpy_tradingagents/models.py`
- `?? vnpy_tradingagents/tradingagents_factory.py`

## 结论

本次验证未达到生产可用准入；未通过或阻塞的生产门禁：readiness_cli, tradingagents_worker_factory_env, llm_api_key_env, worktree_clean

## 备注

- 本地 profile 的目标是证明代码级闭环、smoke、依赖边界和降级路径可重复验证。
- production profile 必须接入真实 PostgreSQL、真实 context-only TradingAgents Worker、真实 API key 和真实 provider 配置后再运行。
- 新闻/社媒实时 provider 本轮不纳入验证范围；缺失时应保持 degraded，不阻塞主交易链路。
