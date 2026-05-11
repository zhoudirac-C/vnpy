# 每日市场复盘 AKShare 重试和降级验证

日期：2026-05-11

## 问题

每日市场复盘在 `2026-05-11` 运行时显示 `no_data`。provider 记录显示：

- vn.py 当前 tick 为空。
- AKShare `stock_zh_a_spot_em` 远端断开。
- AKShare 涨停池有 95 条，说明不是 AKShare 完全不可用。

## 根因

每日复盘 provider 只调用 `stock_zh_a_spot_em()`，没有像 AKShare Gateway 一样做全市场快照接口降级。

## 修复

新增自动重试和接口降级：

1. `stock_zh_a_spot_em`
2. `stock_zh_a_spot`

每个接口最多尝试 2 次，失败写入 provider record；备用接口成功后继续生成复盘。

## 验证结果

真实 AKShare provider smoke：

```text
trade_date 2026-05-11
stocks 5504
stock_zh_a_spot_em attempt=1 failed
stock_zh_a_spot_em attempt=2 failed
stock_zh_a_spot attempt=1 success row_count=5504
limit_up_snapshot success row_count=95
```

自动化测试：

```bash
uv run --with pytest python -m pytest tests/test_daily_market_review_vnpy_app.py -q
uv run --with ruff ruff check vnpy_daily_review tests/test_daily_market_review_vnpy_app.py
```

结果：

```text
12 passed
All checks passed!
```
