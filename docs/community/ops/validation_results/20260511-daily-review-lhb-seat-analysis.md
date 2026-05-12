# 2026-05-11 每日复盘龙虎榜席位分析验证

## 验证目标

验证 P30 每日复盘龙虎榜增强链路：

- AKShare 龙虎榜总表、机构买卖、活跃营业部、个股席位明细可以独立拉取并降级。
- 机构/营业部/上榜原因/集中度可以进入 `LhbSeatAnalysisSignal`。
- `EvidencePack` 可以生成 `lhb_*` 证据，并提供给 AI 编排提示词。
- UI 观察计划和市场信号页可以展示 `capital_type`、`lhb_summary` 和龙虎榜摘要。

## 静态与单元验证

| 命令 | 结果 |
| --- | --- |
| `uv run --with pytest python -m pytest tests/test_daily_market_review_lhb_seat_analysis.py tests/test_daily_market_review_vnpy_app.py -q` | 通过，19 passed |
| `uv run --with ruff ruff check vnpy_daily_review tests/test_daily_market_review_lhb_seat_analysis.py` | 通过，All checks passed |
| `uv run python -m compileall vnpy_daily_review tests/test_daily_market_review_lhb_seat_analysis.py` | 通过 |

说明：本地环境没有裸 `pytest`/`ruff` 可执行文件，因此使用 `uv run --with pytest` 和 `uv run --with ruff` 临时注入测试工具。

## 真实 AKShare Smoke

验证日期：`2026-05-11`

执行方式：使用空 `FakeMainEngine`，由 `VnpyAkshareDailyReviewProvider` 回落到 AKShare，调用 `DailyReviewService.run_preview(run_llm=False)`。

结果：

- `status=completed`
- `message=completed`
- `watch_items=10`
- `lhb_* evidence=4+`，其中包含：
  - `lhb_capital_flow`
  - `lhb_seat_analysis`
  - `lhb_symbol_seat_analysis`
- 观察计划中已有标的带出 `capital_type=institution_net_buy` 和 `lhb_summary`。

样例输出：

```text
completed completed
watch_items 10
lhb_evidence [
  ('lhb_capital_flow', '龙虎榜资金合计净买=0，净买前列=，净卖前列='),
  ('lhb_seat_analysis', '龙虎榜席位拆解：机构净买前列=002179.SZSE,...'),
  ('lhb_symbol_seat_analysis', '300616.SZSE 龙虎榜：reason=unknown，capital=institution_net_sell...')
]
watch_lhb [
  ('600748.SSE', 'institution_net_buy', 'reason=price_deviation; capital=institution_net_buy; ...')
]
```

## 质量与降级观察

- AKShare 当天可以返回机构统计、活跃营业部和部分个股席位明细。
- `stock_lhb_detail_em` 在真实 smoke 中存在阶段性为空或失败的情况，因此代码已支持用机构统计/个股席位明细降级生成股票维度 `symbol_payloads`。
- `lhb_capital_flow` 依赖龙虎榜总表；当总表为空时净买合计可能为 `0`，但 `lhb_seat_analysis` 仍可从机构统计提供证据。
- 免费接口没有 SLA，真实生产前仍需要连续多日跑批记录失败率、耗时和字段漂移。

## 结论

P30 第一版可用：龙虎榜机构/活跃席位/个股席位明细已经进入每日复盘证据链和 AI 输入，且任一 AKShare 子接口失败不会阻塞报告生成。

后续建议：

- 继续观察 `stock_lhb_detail_em` 稳定性，必要时增加备用接口或缓存前一轮成功快照。
- 对 `lhb_stock_seat_snapshot` 增加配置化 Top N，避免复盘时间随龙虎榜股票数增长。
- 若要做生产级席位成功率，应补充长期席位统计缓存，不把单日文本里的“成功率”当作强结论。
