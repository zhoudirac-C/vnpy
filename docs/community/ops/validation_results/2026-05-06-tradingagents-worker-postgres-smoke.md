# P16-T05 TradingAgents Worker + PostgreSQL 验证结果

日期：2026-05-06

## 测试目标

验证 vn.py 进程内懒加载的真实 TradingAgents Worker 可以：

- 读取本地 PostgreSQL 中由 `vnpy_router.Datafeed` 缓存的 A 股 K 线快照。
- 使用 UI/配置中的 LLM provider、model、API key env var 调用真实 TradingAgents/BigModel 链路。
- 不触碰 `MainEngine/Gateway`。
- 将报告、评级、交易意图写回本地 PostgreSQL。

本次验证不输出、不记录 API key。

## 测试环境

- 分支：`feature/akshare-tradingagents-architecture`
- PostgreSQL：`127.0.0.1:5432/vnpy`
- vn.py 数据源：`datafeed.name=router`
- provider：`router.providers=akshare`
- LLM provider：`zhipu`，运行时规范化为 `glm`
- 模型：`glm-4.7`
- Worker factory：`vnpy_tradingagents.tradingagents_factory:build`
- Worker 形态：vn.py 进程内懒加载
- 请求模式：`intraday_advice`
- Thinking：按日内配置关闭
- 超时上限：日内 360 秒
- 测试标的：`600519.SSE`
- K 线窗口：`2024-01-02` 到 `2024-01-10`
- run_id：`p16-t05-local-postgres-20260506`

## 验证命令

```bash
pg_isready -h 127.0.0.1 -p 5432
psql -h 127.0.0.1 -p 5432 -U vnpy -d vnpy -c "select current_database(), current_user;"
uv run vnpy-tradingagents-schema schema status
uv run vnpy-tradingagents-schema readiness --json
uv run python -c "<TradingAgentsRunnerSmoke with PostgresSnapshotReader + PostgresAgentStorage>"
```

## 验证结果

| 项目 | 结果 |
| --- | --- |
| PostgreSQL 连接 | 通过 |
| 扩展表 schema status | 25 张表 ready |
| readiness | ready |
| Worker 真实运行 | 通过 |
| Worker 返回 action/rating | `hold` / `Hold` |
| Worker confidence | `0.0` |
| Worker 耗时 | 约 113 秒 |
| Gateway/MainEngine | 未触碰 |

## PostgreSQL 入库证据

`agent_run`：

| run_id | vt_symbol | trade_date | mode |
| --- | --- | --- | --- |
| `p16-t05-local-postgres-20260506` | `600519.SSE` | `2024-01-10` | `intraday_advice` |

`agent_report`：

| run_id | report_chars | error_message |
| --- | ---: | --- |
| `p16-t05-local-postgres-20260506` | `515` | 空 |

`rating_signal`：

| run_id | vt_symbol | rating | confidence |
| --- | --- | --- | ---: |
| `p16-t05-local-postgres-20260506` | `600519.SSE` | `Hold` | `0` |

`trade_intent`：

| run_id | vt_symbol | action |
| --- | --- | --- |
| `p16-t05-local-postgres-20260506` | `600519.SSE` | `hold` |

## 结论

P16-T05 从“线上 smoke 已通过但未验证 PostgreSQL 入库”更新为“本地 PostgreSQL + 真实 TradingAgents Worker + 入库闭环已通过”。

仍需单独验证 P16-T06 的 paper/simulation 连续运行。该项不是单次 Worker 调用，而是多轮运行、状态导出、feedback、heartbeat 的稳定性验证。
