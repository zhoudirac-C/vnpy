# 2026-05-13 P32 概念板块、当日日 K 刷新与 UI 验证记录

## 代码级验证

- 概念板块领域模型、表模型、仓储：通过。
- provider 链：通过本地 catalog、注入式券商 XT fake、注入式 AKShare fake 单测；确认七轨 scanner 不直接依赖 AKShare。
- 概念入库服务：通过 broker 空返回后降级到 catalog，并写入 `security_concept_link` 与 `security_entity.concept_tags`。
- Router 当日 DAILY 强刷：通过 `refresh_bar_history()` 绕过 snapshot cache 并写回缓存。
- 七轨当日日 K 策略：通过今天日线 TTL=0 强刷、历史日期不强刷。
- UI：通过股票名称解析、七轨搜索、中文信号/regime、当前价/中轨/七轨位置/日 K 时间展示。

## 执行命令

```bash
uv run --with pytest python -m pytest tests/test_concept_board_domain.py tests/test_concept_board_storage.py tests/test_concept_board_providers.py tests/test_concept_board_ingestion.py -q
uv run --with pytest python -m pytest tests/test_data_router.py tests/test_seven_boll_scanner.py -q
uv run --with pytest python -m pytest tests/test_seven_boll_scanner.py tests/test_seven_boll_storage.py tests/test_seven_boll_ui.py tests/test_stock_display.py tests/test_tradingagents_ui.py -q
uv run --with pytest python -m pytest tests/test_concept_board_domain.py tests/test_concept_board_storage.py tests/test_concept_board_providers.py tests/test_concept_board_ingestion.py tests/test_data_router.py tests/test_seven_boll_scanner.py tests/test_seven_boll_storage.py tests/test_seven_boll_ui.py tests/test_stock_display.py tests/test_tradingagents_ui.py -q
uv run --with pytest python -m pytest tests/test_concept_board_ingestion.py tests/test_seven_boll_ui.py tests/test_tradingagents_ui.py -q
```

最后一条 P32 相关集合验证结果：`62 passed in 1.49s`。

P32-T12 前端手动触发概念入库补充验证：

- 局部 UI/引擎测试：`22 passed in 0.65s`
- P32 相关集合验证：`64 passed in 0.97s`

## 已知未通过项

- `uv run --with pytest python -m pytest tests -q` 在收集 `tests/test_alpha101.py` 时失败：当前环境缺少可选依赖 `polars`。该错误发生在测试收集阶段，与 P32 改动无关。

## 真实环境待验证

- 本机券商/QMT/XT SDK 可用性未在单测中声明为生产可用；当前只验证了注入式 fake 和降级行为。
- AKShare 兜底真实批量拉取可能受网络和限流影响，建议首次全量概念入库先设置 `concept.ingestion.max_boards_per_run` 做小批 smoke。
- 盘中当日日 K 属于 preview 语义，收盘后刷新结果才作为 official 口径使用。
