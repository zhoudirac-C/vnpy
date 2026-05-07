# P25-T17 生产新闻二版真实公网 Smoke

## 结论

- 验证时间：2026-05-06，Asia/Shanghai。
- 环境：本机 PostgreSQL + vn.py 全局 `database.*` 配置。
- 结果：通过，带降级记录。
- 说明：CNINFO/巨潮和 AKShare 成功拉取并写入 PostgreSQL；GDELT 公共接口返回 429；上交所公告本次窗口为空。降级没有影响主流程。

## 环境

| 项 | 值 |
| --- | --- |
| `database.name` | `postgresql` |
| `database.host` | `127.0.0.1` |
| `database.port` | `5432` |
| `database.database` | `vnpy` |
| `database.user` | `vnpy` |
| 股票池 | `600519.SSE`, `600406.SSE`, `000400.SZSE` |
| 时间窗口 | 最近 90 天 |
| 实体目录 | `/private/tmp/vnpy_p25_p26_security_catalog.csv` |

## 验证步骤

1. `pg_isready -h 127.0.0.1 -p 5432`
2. `uv run python -c "from vnpy_tradingagents.schema_init import initialize_postgres_schema; initialize_postgres_schema()"`
3. 分别调用 `CninfoAnnouncementProvider`、`SseAnnouncementProvider`、`GdeltGlobalNewsProvider`、`AkshareStockNewsProvider`。
4. 使用 `ExternalNewsIngestionJob` 接入 `NewsProviderChain`，执行 `resolve -> classify -> score -> dedup -> save event -> save event_symbol_link -> quality report`。
5. 通过 `PostgresEventStorage.load_news_events()` 回读各股票事件。

## Provider 结果

| Provider | 拉取条数 | 降级 | 错误 |
| --- | ---: | --- | --- |
| `cninfo_announcement` | 6 | 否 | 无 |
| `sse_announcement` | 0 | 否 | 无 |
| `gdelt_global_news` | 0 | 是 | `HTTP Error 429: Too Many Requests` |
| `akshare_stock_news` | 9 | 否 | 无 |

## 入库结果

| 指标 | 结果 |
| --- | ---: |
| `raw_count` | 15 |
| `event_count` | 15 |
| 降级来源 | `gdelt_global_news` |
| `news_event` 中 CNINFO 事件 | 6 |
| `news_event` 中 AKShare 事件 | 9 |
| `600519.SSE` 回读事件 | 5 |
| `600406.SSE` 回读事件 | 5 |
| `000400.SZSE` 回读事件 | 3 |

示例回读：

```text
600519.SSE akshare_stock_news holding_change 2026-05-06 10:07:00 pending
600406.SSE akshare_stock_news earnings 2026-04-30 10:43:30 pending
000400.SZSE akshare_stock_news industry 2026-04-28 17:20:00 pending
```

## 验证中修复的问题

- CNINFO 真实接口不能稳定使用 `stock=code` 查询，已改为按股票逐个 `searchkey=code` 查询。
- CNINFO `announcementTime` 为毫秒时间戳，已按 `Asia/Shanghai` 解析成 vn.py 本地时间。
- 本地已有 PostgreSQL 扩展表时，Peewee `create_tables(safe=True)` 不会补新增列，已在 `initialize_postgres_schema()` 后追加幂等 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`。

## 剩余风险

- GDELT 免费公共接口可能限流，不能作为生产主源。
- 上交所公告入口本次窗口返回空，需要后续用更多沪市样本抽样确认。
- 还没有完成连续 5 个交易日定时任务稳定性验证。
