# 七轨布林线使用方法与 vn.py 接入方案

> 本文是技术分析与量化实现说明，不构成投资建议。七轨布林线只能提供“价格相对位置 + 波动率状态 + 趋势结构”的观察框架，不能单独作为买卖依据。

## 1. 资料调研结论

调研资料包括 John Bollinger 官方规则、Fidelity、StockCharts、Investopedia、MBA 智库和中文布林线用法资料。主流共识如下：

- 布林线的本质是动态波动通道，用标准差描述价格相对均线的高低位置。
- 触碰上轨或下轨不是独立买卖信号；John Bollinger 官方规则明确强调“触轨只是触轨，不是信号”。
- 强趋势中价格可以长期贴着上轨或下轨运行，不能简单认为“上轨必卖、下轨必买”。
- 收口代表波动率压缩，后续可能出现波动扩张，但收口本身不判断方向。
- 突破方向需要结合成交量、趋势、动量、资金、市场环境等非同源指标确认。
- `BandWidth` 用于衡量带宽，适合寻找 squeeze；`%B` 用于量化价格在布林带中的位置。

参考资料：

- [John Bollinger 官方规则](https://www.bollingerbands.com/bollinger-band-rules)
- [Fidelity: Bollinger Bands](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/bollinger-bands)
- [Fidelity: Percent B](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/percent-b)
- [BollingerBands.us: Screening Help](https://bollingerbands.us/help-screening.php)
- [StockCharts: Bollinger BandWidth](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/bollinger-bandwidth)
- [Investopedia: Bollinger Squeeze](https://www.investopedia.com/articles/technical/04/030304.asp)
- [MBA 智库百科：BOLL 指标](https://wiki.mbalib.com/wiki/BOLL)

## 2. 七轨布林线公式

用户给出的公式：

```text
N := 20
MID := MA(C, N)
STD0 := STD(C, N)
DEV := MA(STD0, 5)

顶轨 = MID + 3 * DEV
一轨 = MID + 2 * DEV
二轨 = MID + 1 * DEV
三轨 = MID
四轨 = MID - 1 * DEV
五轨 = MID - 2 * DEV
底轨 = MID - 3 * DEV
```

这里和标准布林线有两个差异：

- 标准布林线通常只画 `MID ± 2 * STD` 三条线。
- 七轨布林线把 `±1/±2/±3` 都画出来，并且 `DEV = MA(STD(C,N),5)`，相当于对标准差再做 5 日平滑，轨道会比直接用 `STD(C,N)` 更平滑。

## 3. 七条轨道的含义

| 轨道 | 公式 | 位置含义 | 交易理解 |
| --- | --- | --- | --- |
| 顶轨 | `MID + 3DEV` | 极端高位 | 情绪过热或强趋势极端延伸，优先观察风险 |
| 一轨 | `MID + 2DEV` | 中度高位 | 强势区上沿，震荡市偏止盈，趋势市偏持有 |
| 二轨 | `MID + 1DEV` | 轻度高位 | 强趋势回踩支撑、趋势持仓线 |
| 三轨/MID | `MID` | 趋势中枢 | 多空分水岭、均值回归目标 |
| 四轨 | `MID - 1DEV` | 轻度低位 | 弱势反弹压力或震荡低吸观察 |
| 五轨 | `MID - 2DEV` | 中度低位 | 震荡市分批低吸区，趋势弱时不能盲目抄底 |
| 底轨 | `MID - 3DEV` | 极端低位 | 恐慌/极弱区，必须等止跌确认 |

更量化的理解：

```text
Z7 = (Close - MID) / DEV
```

- `Z7 >= 3`：顶轨外，极端强势或冲高过热。
- `2 <= Z7 < 3`：一轨到顶轨，强势高位。
- `1 <= Z7 < 2`：二轨到一轨，趋势强势区。
- `0 <= Z7 < 1`：三轨到二轨，多头正常区。
- `-1 <= Z7 < 0`：四轨到三轨，空头正常区。
- `-2 <= Z7 < -1`：五轨到四轨，弱势低位。
- `Z7 < -3`：底轨外，极端弱势或恐慌。

## 4. 关键衍生指标

### 4.1 七轨带宽

```text
BandWidth7 = (顶轨 - 底轨) / MID
           = 6 * DEV / MID
```

用途：

- 判断波动率是否收缩。
- 做全市场扫描，寻找“窄幅整理后等待方向选择”的股票。
- 和历史分位数结合，避免用固定阈值误判不同行业。

推荐：

```text
bandwidth_percentile = 当前 BandWidth7 在过去 120 或 250 个交易日中的分位数
```

- `< 15%`：低波动压缩。
- `< 5%`：极端压缩，候选 squeeze。
- `> 85%`：波动过热，可能进入 bulge/扩张后期。

### 4.2 七轨位置值

```text
position_z = (Close - MID) / DEV
```

用途：

- 比单纯“价格在几轨”更好做策略和回测。
- 可以判断“强势回踩二轨”“跌破三轨”“触及底轨”等事件。

### 4.3 轨道斜率

```text
mid_slope = MID - REF(MID, k)
bandwidth_slope = BandWidth7 - REF(BandWidth7, k)
```

用途：

- `mid_slope > 0`：中期趋势向上。
- `bandwidth_slope > 0`：波动扩张。
- `bandwidth_slope < 0`：波动收缩。

## 5. 七轨布林线的主要用法

## 5.1 强趋势回踩二轨

适用场景：

- 股价处于强趋势。
- 中轨上行。
- 价格大多数时间运行在二轨和一轨之间。
- 回踩二轨时缩量或承接明显。

候选条件：

```text
MID 向上
Close 过去 10 日多数在 MID 上方
BandWidth7 不处于极端收缩
Close 从一轨/顶轨回落到二轨附近
二轨附近止跌，次日重新转强
```

入场观察：

- 盘中跌到二轨附近后收回。
- 收盘站回二轨。
- 分时承接稳定，未出现放量破位。
- 板块和市场环境不拖累。

退出条件：

- 有效跌破三轨/MID。
- 跌破二轨后无法快速收回。
- 顶轨附近放量滞涨或长上影。

风险：

- 如果中轨走平或下弯，二轨不再是强支撑。
- 如果放量跌破二轨，可能不是低吸，而是趋势结束。

## 5.2 收口突破

适用场景：

- 长时间横盘。
- 七轨带宽处于历史低位。
- 突破时成交量明显放大。

候选条件：

```text
BandWidth7 分位数 < 10%
过去一段时间 Close 围绕 MID 上下窄幅波动
Close 放量突破一轨或顶轨
MID 开始上行
BandWidth7 从低位拐头上升
```

确认方式：

- 首日突破后不快速跌回三轨。
- 第二天仍能维持在二轨上方。
- 成交额放大，且不是一字冲高回落。

风险：

- squeeze 不判断方向，可能向上也可能向下。
- 常见“假突破”：先向上冲出，再跌回区间。
- 必须设置止损，例如跌回三轨或跌破突破 K 线低点。

## 5.3 震荡区间高抛低吸

适用场景：

- 中轨走平。
- 带宽稳定或收缩。
- 价格在五轨到一轨之间反复波动。

低吸观察：

```text
Close 接近五轨或底轨
没有明显下跌趋势
出现缩量止跌、下影线、RSI 背离等确认
目标先看 MID，再看一轨
```

高抛观察：

```text
Close 接近一轨或顶轨
没有进入强趋势贴轨
放量滞涨或冲高回落
目标先看 MID
```

风险：

- 震荡策略最怕趋势突破。
- 一旦带宽突然扩张并跌破底轨，不能继续按震荡低吸处理。

## 5.4 极端超买/超卖反转观察

七轨的 `±3DEV` 适合做“极端情绪识别”，但不适合直接做反向交易。

顶轨反转观察：

```text
Close 突破或接近顶轨
成交额异常放大
次日无法继续站上顶轨
出现长上影、放量滞涨、MACD/RSI 背离
```

底轨反弹观察：

```text
Close 跌破或接近底轨
下跌速度开始放缓
缩量或恐慌量释放后不再创新低
次日重新站回五轨
```

风险：

- 强趋势中，顶轨可以继续贴轨上行。
- 主跌浪中，底轨可能连续被跌穿。
- 反转类信号必须比趋势类信号更严格。

## 5.5 趋势失败/破位退出

适用场景：

- 已持有趋势股。
- 用轨道管理持仓，而不是主观猜顶。

退出规则示例：

```text
强趋势持仓：Close >= 二轨，继续持有
趋势减弱：Close 跌破二轨，减仓观察
趋势破坏：Close 跌破三轨/MID，退出趋势仓
风险确认：MID 下弯，且 Close 跌破四轨，停止低吸
```

## 5.6 多周期共振（后续探索）

P31 第一阶段不实现多周期或分时扫描，只使用日线数据生成波段观察信号。下面内容仅作为后续人工执行或二期研究方向，不进入本阶段 vn.py scanner、scheduler、TradingAgents 联动和验证口径。

建议：

- 日线判断大趋势和主策略。
- 60 分钟或 30 分钟找具体介入位置。
- 5 分钟只看执行，不做大方向判断。

例子：

```text
日线：MID 上行，价格在二轨以上，趋势偏强
60 分钟：回踩四轨/五轨后重新站回 MID
5 分钟：放量站回二轨，分时承接稳定
```

## 6. 七轨布林线策略模板

## 6.1 趋势回踩策略

```text
过滤：
  MID slope > 0
  Close > MID
  过去 20 日涨跌幅强于指数

入场：
  Close 回踩到二轨附近
  Low <= 二轨 * 1.01
  Close >= 二轨
  Volume 没有异常放大杀跌

止损：
  Close < MID
  或跌破回踩日低点

止盈：
  到一轨/顶轨后出现放量滞涨
  或 Close 跌破二轨
```

## 6.2 收口突破策略

```text
过滤：
  BandWidth7 percentile < 10%
  MID 走平或微微上行
  最近 20 日无大幅破位

入场：
  Close > 一轨
  Volume > MA(Volume, 20) * 1.5
  BandWidth7 拐头向上

止损：
  Close 跌回 MID
  或跌破突破 K 线低点

止盈：
  顶轨附近冲高回落
  或 BandWidth7 到历史高位后价格跌破二轨
```

## 6.3 震荡均值回归策略

```text
过滤：
  abs(MID slope) 较小
  BandWidth7 不扩张
  大盘和板块无明显单边趋势

入场：
  Close 接近五轨或底轨
  RSI/MACD 出现背离或止跌确认

止损：
  Close 连续跌破底轨
  或 BandWidth7 向下破位后扩张

止盈：
  第一目标 MID
  第二目标 一轨
```

## 7. 常见误区

- 误区 1：顶轨一定卖，底轨一定买。
  - 正解：触轨只是相对位置，强趋势会贴轨运行。
- 误区 2：收口一定向上突破。
  - 正解：收口只表示波动率压缩，不判断方向。
- 误区 3：七条线越多越准。
  - 正解：七轨只是更细的位置刻度，核心仍是趋势和波动率。
- 误区 4：固定参数适合所有股票。
  - 正解：不同股票波动结构不同，参数需要回测。
- 误区 5：只看布林线，不看成交量和市场环境。
  - 正解：布林线最好与成交量、动量、资金、板块强度等非同源信息一起使用。

## 8. 后续接入 vn.py 的设计

## 8.1 指标对象

建议新增一个独立指标计算器：

```text
SevenBollingerIndicator
```

输入：

- `close`
- `high`
- `low`
- `volume`
- 参数：
  - `window = 20`
  - `std_ma_window = 5`
  - `squeeze_lookback = 120`
  - `pullback_tolerance = 0.01`

输出：

```text
mid
top_band
upper2_band   # 一轨
upper1_band   # 二轨
lower1_band   # 四轨
lower2_band   # 五轨
bottom_band
dev
zscore
bandwidth7
bandwidth_percentile
mid_slope
bandwidth_slope
rail_zone
regime
```

`rail_zone` 示例：

```text
above_top
top_to_upper2
upper2_to_upper1
upper1_to_mid
mid_to_lower1
lower1_to_lower2
lower2_to_bottom
below_bottom
```

`regime` 示例：

```text
trend_up
trend_down
range
squeeze
expansion_up
expansion_down
extreme_overbought
extreme_oversold
```

## 8.2 vn.py CTA 策略接入

可以新增策略：

```text
SevenBollTrendStrategy
SevenBollSqueezeBreakoutStrategy
SevenBollMeanReversionStrategy
```

第一版建议先做一个综合策略：

```text
SevenBollSignalStrategy
```

策略参数：

```text
window = 20
std_ma_window = 5
squeeze_lookback = 120
squeeze_percentile = 10
trend_slope_window = 5
pullback_tolerance = 0.01
fixed_size = 1
stop_loss_pct = 0.05
take_profit_mode = "rail"
```

## 8.3 信号定义

```text
signal_trend_pullback_long:
  regime == trend_up
  low <= upper1_band * (1 + tolerance)
  close >= upper1_band

signal_squeeze_breakout_long:
  bandwidth_percentile <= squeeze_percentile
  close > upper2_band
  volume > volume_ma20 * 1.5

signal_mean_reversion_long:
  regime == range
  close <= lower2_band
  close > previous_close

signal_trend_exit:
  close < mid

signal_overheat_reduce:
  close >= top_band
  close < open
  volume > volume_ma20 * 1.5
```

## 8.4 回测要求

至少分三类市场验证：

- 单边上涨阶段：验证二轨回踩是否有效。
- 横盘震荡阶段：验证五轨/一轨均值回归。
- 收口突破阶段：验证 squeeze 后突破收益和假突破损失。

回测指标：

- 胜率。
- 盈亏比。
- 最大回撤。
- 平均持仓天数。
- 假突破率。
- 跌破三轨后的止损效率。
- 不同行业/不同市值分组表现。

## 8.5 UI 接入建议

在 vn.py 中可以分三层展示：

1. K 线图叠加七轨布林线。
2. 策略参数面板支持开启/关闭：
   - 趋势回踩。
   - 收口突破。
   - 均值回归。
3. 每个信号生成时记录解释：
   - 当前轨道区间。
   - 当前带宽分位数。
   - 当前趋势状态。
   - 触发条件。
   - 止损条件。

## 8.6 与每日复盘/AI 模块结合

后续可以把七轨布林线作为 `MarketSignal` 的一部分：

```text
technical_signals:
  seven_boll:
    regime: trend_up
    rail_zone: upper2_to_upper1
    bandwidth_percentile: 35
    signal: trend_pullback_long
    risk: close_below_mid_exit
```

AI 复盘时可以使用这些字段生成自然语言：

```text
某股处于七轨布林线强趋势结构，日线中轨上行，价格回踩二轨后收回，
属于趋势回踩观察信号；若后续跌破三轨，则趋势结构失效。
```

## 9. 推荐第一阶段实现范围

第一阶段不要直接做自动交易，建议先实现：

- 指标计算。
- CTA/回测策略。
- 全市场日线扫描：
  - 七轨收口。
  - 强趋势二轨回踩。
  - 顶轨过热。
  - 底轨恐慌。
- 午盘预览和收盘正式定时触发。
- 扫描结果落库，只保存 scan run/result，不重复保存原始 K 线。
- TradingAgents 单点/批量分析联动，把七轨结果作为日线技术面证据。

第一阶段明确不做：

- 分时/分钟线扫描。
- 盘口异动和日内 T+0 建议。
- 自动实盘下单。
- 组合级资金分配。

第二阶段再考虑：

- 模拟盘验证。
- 风控接管。
- 分时执行辅助。
- 每日复盘 AI 的更深度联动。

## 10. 总结

七轨布林线比普通三轨布林线更适合做“位置分层”和“策略解释”：

- `±1DEV` 适合判断趋势强弱和回踩。
- `±2DEV` 适合判断强势边界和震荡区间。
- `±3DEV` 适合判断极端情绪。
- `BandWidth7` 适合寻找波动压缩和突破前夜。
- `Z7` 适合量化价格处在哪个轨道区间。

后续接入 vn.py 时，建议把它定位成“技术信号模块”，先服务扫描、回测和每日复盘，不直接作为单一自动买卖策略。
