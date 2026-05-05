# PostgreSQL 备份和恢复演练

本文档用于 TradingAgents + vn.py 自定义架构的 PostgreSQL 运维。目标是让 market snapshot、agent report、signal、decision audit、feedback、replay status 和 ops heartbeat 都可恢复、可验收。

## 备份范围

必须备份：

- `market_bar_snapshot` 和各类 research snapshot。
- `news_raw`、`news_event`、`social_post_raw`、`sentiment_snapshot`、`event_quality_report`。
- `agent_run`、`agent_report`、`rating_signal`、`trade_intent`、`intraday_advice`。
- `decision_audit`、`agent_trade_feedback`、`agent_performance_feedback`。
- `replay_run_status`、`ops_heartbeat`。

## 备份命令

```bash
export PGDATABASE=quant
export PGHOST=127.0.0.1
export PGUSER=quant

pg_dump \
  --format=custom \
  --file=backup/quant_$(date +%Y%m%d_%H%M%S).dump \
  --dbname="$PGDATABASE"
```

建议：

- 盘后做一次完整备份。
- 实盘或仿真关键窗口前做一次手动备份。
- 至少保留 30 个自然日的日备份和 12 个自然月的月备份。
- 回测基准数据锁定后，记录备份文件 hash，避免复盘时数据悄悄变化。

## 恢复演练

恢复到临时库，不直接覆盖生产库：

```bash
createdb quant_restore_check

pg_restore \
  --clean \
  --if-exists \
  --dbname=quant_restore_check \
  backup/quant_YYYYMMDD_HHMMSS.dump
```

## 恢复验收

```bash
vnpy-tradingagents-schema schema status
psql quant_restore_check -c "select count(*) from decision_audit;"
psql quant_restore_check -c "select count(*) from replay_run_status;"
psql quant_restore_check -c "select count(*) from ops_heartbeat;"
```

验收标准：

- `vnpy-tradingagents-schema schema status` 显示当前发布要求的扩展表均为 ready。
- 最近一个回测或 paper smoke 的 `decision_audit` 可查。
- 最近一个 `replay_run_status` 可查并能被 UI 状态面板读取。
- `ops_heartbeat` 能显示 worker、provider 或 scheduler 的最近状态。
- 抽样一只股票能查到 market snapshot、AI report、rating signal 和 feedback。

## 审计保留

- `decision_audit`、`agent_report`、`trade_intent` 和 feedback 至少保留 3 年。
- 原始新闻和社媒原文按来源合规要求处理；至少保留 hash、source、provider、抓取时间、清洗版本和质量状态。
- 若要清理大体积原文，先导出 `event_quality_report` 和 `raw_hash` 映射。
