# P31 七轨布林线回测验证结果

验证对象：`SevenBollSignalStrategy`，通过 `vnpy_ctastrategy.BacktestingEngine` 消费日线 `BarData`。

> 本验证仅用于验证逻辑，不代表生产收益。

固定口径：`interval=d`，不包含分时/日内短线数据。

| 场景 | interval | K线数 | 交易次数 | 胜率 | 盈亏比 | 最大回撤 | 假突破率 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| trend_pullback | interval=d | 70 | 1 | 0.00% | 0.00 | -75.00 | 0.00% |
| squeeze_breakout | interval=d | 86 | 3 | 0.00% | 0.00 | 0.00 | 0.00% |
| mean_reversion | interval=d | 87 | 0 | 0.00% | 0.00 | 0.00 | 0.00% |

说明：

- `trend_pullback` 覆盖强趋势回踩二轨附近的波段观察逻辑。
- `squeeze_breakout` 覆盖带宽收口后向上突破的观察逻辑。
- `mean_reversion` 覆盖震荡区间低位均值回归观察逻辑。
- 假突破率在当前轻量验证中按亏损交易占比估算，仅用于回归测试跟踪。
- 全流程只使用日线 K 线，未请求或读取分钟线。
