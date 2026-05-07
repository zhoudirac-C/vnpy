# P26-T07 GLM-4.7 消息分类真实 Smoke

## 结论

- 验证时间：2026-05-06，Asia/Shanghai。
- 模型：`glm-4.7`。
- API key：通过 `ZHIPU_API_KEY` 解析，未写入文档。
- 结果：通过。
- 说明：不开 Thinking 和开 Thinking 两种模式都能把行业/板块消息映射到本地股票主数据中的候选股票；未命中本地实体目录的股票进入 `dropped_symbols`，不会写入 link。

## 配置

| 配置项 | 值 |
| --- | --- |
| `news.llm_classifier.model` | `glm-4.7` |
| `news.llm_classifier.scheduled_thinking_type` | `disabled` |
| `news.llm_classifier.batch_thinking_type` | `enabled` |
| `news.llm_classifier.fast_timeout_seconds` | `360` |
| `news.llm_classifier.deep_timeout_seconds` | `2700` |
| `news.llm_classifier.min_confidence` | `0.65` |
| 实体目录 | `/private/tmp/vnpy_p25_p26_security_catalog.csv` |

## 测试消息

```text
标题：新型电力系统建设提速，特高压、电网智能化和储能调节能力受关注
摘要：国家能源主管部门提出加快新型电力系统建设，提升新能源消纳、电网数字化、
特高压输电和储能调峰能力。市场关注电网自动化设备、继电保护、换流阀、
储能PCS和光伏逆变器等环节的订单弹性。
```

## 结果

| 模式 | Thinking | 超时 | 实际耗时 | Tokens | 结论 |
| --- | --- | ---: | ---: | ---: | --- |
| `scheduled_ingestion` | `disabled` | 360s | 68.61s | 1,276 | 通过 |
| `batch_industry_mapping` | `enabled` | 2700s | 247.27s | 3,192 | 通过 |

Token 明细：

| 模式 | prompt | completion | reasoning | total |
| --- | ---: | ---: | ---: | ---: |
| `scheduled_ingestion` | 341 | 935 | 0 | 1,276 |
| `batch_industry_mapping` | 341 | 2,851 | 1,868 | 3,192 |

## 命中股票

| 模式 | 本地校验通过股票 |
| --- | --- |
| `scheduled_ingestion` | `600406.SSE` 国电南瑞、`000400.SZSE` 许继电气、`601179.SSE` 中国西电、`300274.SZSE` 阳光电源 |
| `batch_industry_mapping` | `600406.SSE` 国电南瑞、`000400.SZSE` 许继电气、`300274.SZSE` 阳光电源、`601179.SSE` 中国西电 |

被丢弃候选示例：

```text
600517.SSE, 601126.SSE, 600312.SSE, 688390.SSE, 688676.SSE, 002028.SZSE
600089.SSE, 601126.SSE, 300827.SZSE, 600312.SSE, 600268.SSE, 002090.SZSE
```

丢弃原因：这些候选未命中本次本地 `SecurityEntityCatalog`，因此只进入 `dropped_symbols`，不会写入 `event_symbol_link`。

## 验证中修复的问题

- `ZhipuGlmChatClient` 已记录响应 `usage`，便于 smoke 和审计落档。
- `news.llm_classifier.fast_timeout_seconds` 按前序要求从 120s 改为 360s。
- `news.llm_classifier.deep_timeout_seconds` 按前序要求从 1800s 改为 2700s，即 45 分钟。

## 生产含义

- 日内/定时新闻入库默认不开 Thinking，成本和耗时更低，但真实线上响应仍可能接近 1 分钟以上，不适合逐 tick 同步阻塞。
- 盘后复盘、长期研究、批量行业映射可开 Thinking，本次 reasoning tokens 明显增加，适合异步运行。
- LLM 输出只做“候选关联”，最终仍由本地股票主数据校验，避免幻觉股票直接进入 TradingAgents context。
