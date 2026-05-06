# P16-T06 Paper/Simulation 连续运行验证结果

- 结果：`通过`
- run_id：`p16-t06-local-20260506`
- 标的：`600519.SSE`
- 周期数：`3`
- worker runs：`3`
- replay status：`True`
- decision audit：`3`
- trade feedback：`2`
- performance feedback：`3`
- ops heartbeat：`True`
- live_gateway_touched：`False`

## PostgreSQL 证据

| 表 | 记录数 |
| --- | ---: |
| agent_run | `3` |
| agent_report | `3` |
| rating_signal | `3` |
| trade_intent | `3` |
| decision_audit | `3` |
| agent_trade_feedback | `2` |
| agent_performance_feedback | `3` |
| replay_run_status | `1` |
| ops_heartbeat | `1` |

## 备注

- accelerated paper/simulation validation
- deterministic worker avoids repeated LLM token cost; P16-T05 covers real LLM worker connectivity
- long-running multi-day soak remains a separate operational validation window
