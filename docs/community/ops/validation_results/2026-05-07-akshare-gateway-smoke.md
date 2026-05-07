# 2026-05-07 AKShare Gateway 验证结果

## 验证目标

验证无 QMT/XT 账号阶段，`vnpy_akshare_gateway.AkshareGateway` 可以通过 vn.py Gateway UI 注册、加载 A 股合约、订阅快照 Tick，并在 AKShare 主接口失败时自动降级到备用接口。

## 代码级验证

| 项目 | 结果 | 命令 |
| --- | --- | --- |
| AKShare Gateway + UI 注册测试 | 通过，10 passed | `uv run --with pytest pytest tests/test_akshare_gateway.py tests/test_tradingagents_ui.py -q -p no:cacheprovider` |
| Ruff 检查 | 通过 | `uv run --with ruff ruff check vnpy_akshare_gateway tests/test_akshare_gateway.py tests/test_tradingagents_ui.py examples/veighna_trader/run.py` |

覆盖点：

- 连接时加载全市场合约。
- 连接时只订阅指定股票且不加载全市场合约。
- 手动订阅股票。
- `stock_zh_a_spot_em` 失败后 fallback 到 `stock_zh_a_spot`。
- `600519.SSE`、`600519.SH`、`SH600519`、`sz000001`、`bj920000` 这类代码格式归一到 vn.py 交易所。
- 下单、撤单保持只读拒绝。
- `examples/veighna_trader/run.py` 默认注册 AKShare Gateway。

## 真实 AKShare 冒烟

验证命令连接 `AKSHARE`，订阅 `600519.SSE`，配置 `快照接口顺序=stock_zh_a_spot_em,stock_zh_a_spot`。

结果：

| 项目 | 结果 |
| --- | --- |
| 主接口 `stock_zh_a_spot_em` | 失败，远端断开连接 |
| 备用接口 `stock_zh_a_spot` | 成功 |
| 合约数量 | 5512 |
| 订阅 Tick | `600519.SSE`，名称 `贵州茅台`，最新价 `1371.05`，买一 `1371.05`，卖一 `1371.26` |

结论：

- AKShare 多接口降级生效。
- 主界面可通过 AKShare Gateway 临时看到 A 股合约和快照行情。
- 备用接口需要抓取全市场公开网页数据，耗时明显更长；生产实盘仍应切换到 QMT/XT、XTP、TORA 等真实 Gateway。
