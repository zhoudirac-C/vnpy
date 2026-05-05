# P19 回测闭环验证任务

目标：用可重复、可审计的方式证明 “K 线数据 -> vn.py BacktestingEngine -> AI 信号读取 -> 信号融合 -> 风控审计 -> 回测结果落档” 能跑通。第一版只使用本地 fixture 和 vn.py 回测引擎，不连接真实 Gateway，不调用真实 LLM。

## 任务清单

- [x] **P19-T01: 回测闭环验证入口**
  - 创建：`tools/production/backtest_closed_loop_validation.py`
  - 目标：提供 CLI 和 Python API，读取本地 K 线 fixture，运行 vn.py `BacktestingEngine`，生成 Markdown/JSON 结果。
  - 验收：命令可输出 trade count、AI audit count、statistics、是否触碰 Gateway。

- [x] **P19-T02: AI 回测策略验证器**
  - 创建：`tests/test_backtest_closed_loop_validation.py`
  - 目标：测试策略在 `on_bar` 中调用 `BacktestingAppBridge`，并且只通过回测引擎撮合，不访问 `MainEngine/Gateway`。
  - 验收：至少一笔回测成交，至少一条 `DecisionAuditRecord`，`live_gateway_touched=false`。

- [x] **P19-T03: 验证结果落档**
  - 创建：`docs/community/ops/validation_results/YYYY-MM-DD-backtest-closed-loop.*`
  - 目标：把当前分支的一次 P19 验证过程和结果落档。
  - 验收：Markdown/JSON 同时存在，结果明确区分 fixture 回测和真实生产回测。

- [ ] **P19-T04: 真实 PostgreSQL/AKShare 回测扩展**
  - 前置：真实 PostgreSQL、AKShare 或其他 provider ready。
  - 目标：用 `vnpy_router.Datafeed` 或 vn.py Database 加载同一标的历史 K 线，再跑相同回测验证。
  - 验收：结果落档中包含 provider trace 和数据版本；若 provider 不可用，状态为 Blocked 而不是通过。

## 完成记录

| 任务 | 日期 | 提交 | 验证 |
| --- | --- | --- | --- |
| P19-T01 | 2026-05-05 | 未提交 | `uv run --with pytest pytest tests/test_backtest_closed_loop_validation.py -q` |
| P19-T02 | 2026-05-05 | 未提交 | `uv run --with pytest pytest tests/test_backtest_closed_loop_validation.py -q` |
| P19-T03 | 2026-05-05 | 未提交 | `uv run python -m tools.production.backtest_closed_loop_validation --output docs/community/ops/validation_results/2026-05-05-backtest-closed-loop.md --json-output docs/community/ops/validation_results/2026-05-05-backtest-closed-loop.json` |
| P19-T04 | Blocked | 未提交 | 等待真实 provider 回测数据 |
