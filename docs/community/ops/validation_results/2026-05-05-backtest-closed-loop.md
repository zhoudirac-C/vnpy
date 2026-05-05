# P19 回测闭环验证结果

- 结果：`通过`
- 标的：`600519.SSE`
- 数据：`fixture:tests/fixtures/e2e/600519.SSE_d.csv`
- 引擎：`vnpy_ctastrategy.BacktestingEngine`
- K 线数量：`3`
- 回测成交数：`1`
- AI 审计数：`1`
- live_gateway_touched：`false`

## 关键统计

| 指标 | 值 |
| --- | --- |
| total_trade_count | `1` |
| total_return | `0.0014292999999998557` |
| max_drawdown | `0.0` |
| sharpe_ratio | `17.87727455774354` |

## 审计摘要

| decision_id | action | ai_used | risk_decision | source_run_ids |
| --- | --- | --- | --- | --- |
| p19-decision-1 | `buy` | `true` | `approved` | `p19-rating-fixture,p19-advice-fixture` |

## 备注

- fixture backtest; not a broker, QMT, XTP or TORA run
- 未触碰真实 Gateway/MainEngine
